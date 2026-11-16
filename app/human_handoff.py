"""Synthetic local human handoff. No external notification or Getnet integration."""
import hashlib
import json
import re
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from app.demo_tickets import TicketError, TOPICS
from app.privacy import clean_message
from app.public_information import suspicious

HandoffError = TicketError
REASONS = frozenset({'customer_request','billing_review','unresolved','evidence_gap','tool_unavailable'})

class HandoffStore:
    def __init__(self, tickets, realm):
        if not isinstance(realm,str) or not re.fullmatch(r'[a-f0-9]{32}',realm):
            raise TicketError('permission')
        self.tickets, self.realm = tickets, realm
        if tickets.enabled:
            with self._db(write=True) as db:
                db.execute('CREATE TABLE IF NOT EXISTS human_handoffs(proposal_id TEXT PRIMARY KEY REFERENCES demo_proposals(id),realm TEXT NOT NULL,reason TEXT NOT NULL,summary TEXT NOT NULL,state TEXT NOT NULL,version INTEGER NOT NULL)')
                db.execute('CREATE TABLE IF NOT EXISTS human_events(id TEXT PRIMARY KEY,proposal_id TEXT NOT NULL REFERENCES human_handoffs(proposal_id),realm TEXT NOT NULL,tenant TEXT NOT NULL,operator TEXT NOT NULL,request_id TEXT NOT NULL,fingerprint TEXT NOT NULL,kind TEXT NOT NULL,text TEXT NOT NULL,version INTEGER NOT NULL,created REAL NOT NULL,acked INTEGER NOT NULL DEFAULT 0, UNIQUE(realm,tenant,operator,request_id))')

    @contextmanager
    def _db(self,write=False):
        if not self.tickets.enabled: raise TicketError('disabled')
        db=None; committing=False
        try:
            db=sqlite3.connect(Path(self.tickets.path).resolve().as_uri()+'?mode=rw',uri=True,timeout=.25,isolation_level=None)
            db.row_factory=sqlite3.Row
            db.execute('PRAGMA foreign_keys=ON')
            if write: db.execute('BEGIN IMMEDIATE')
            yield db
            if write:
                committing=True
                self.tickets._commit(db)
        except TicketError:
            if db is not None and db.in_transaction: db.rollback()
            raise
        except Exception:
            if db is not None and db.in_transaction: db.rollback()
            raise TicketError('unconfirmed' if committing else 'unavailable') from None
        finally:
            if db is not None: db.close()

    def _principal(self,p,scope):
        from app.support import Principal
        if not self.tickets.enabled: raise TicketError('disabled')
        if not isinstance(p,Principal) or scope not in p.scopes or any(not isinstance(v,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',v) for v in (p.subject,p.tenant)):
            raise TicketError('permission')
        if scope.startswith('handoff:') and p.subject in {'demo_A','demo_B','cliente1988'}: raise TicketError('permission')
        return p

    def _client(self,p,session,write=False):
        self._principal(p,'demo_ticket:write' if write else 'demo_ticket:read')
        if not isinstance(session,str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,80}',session): raise TicketError('permission')
        return p.subject,p.tenant,session

    @staticmethod
    def _text(text):
        if not isinstance(text,str) or not 1<=len(text.strip())<=600: raise TicketError('conflict')
        text=text.strip()
        safe,redacted=clean_message(text)
        # Bounded plain text only. This is a guard, not a universal PII classifier.
        if redacted or safe!=text or suspicious(text) or re.search(r'[<>\x00-\x08\x0b-\x1f]|https?://|\b\S+@\S+\b|\d{7,}|(?:sk-|tvly-|Bearer\s)[A-Za-z0-9_-]{8,}',text,re.I): raise TicketError('conflict')
        return text

    def _row(self,db,pid):
        self.tickets._id(pid)
        row=db.execute('SELECT p.*,t.protocol,t.created AS confirmed_at,h.realm,h.reason,h.summary,h.state,h.version FROM human_handoffs h JOIN demo_proposals p ON p.id=h.proposal_id LEFT JOIN demo_tickets t ON t.proposal_id=p.id WHERE h.proposal_id=? AND h.realm=?',(pid,self.realm)).fetchone()
        if row is None: raise TicketError('permission')
        if bool(row['consumed'])!=bool(row['protocol']): raise TicketError('conflict')
        if row['state']!='awaiting_confirmation' and not row['protocol']: raise TicketError('conflict')
        return row

    def _bound(self,db,p,session,pid):
        row=self._row(db,pid)
        if (row['owner'],row['tenant'],row['session'])!=(p.subject,p.tenant,session): raise TicketError('permission')
        return row

    @staticmethod
    def _view(row):
        return {'proposal_id':row['id'],'protocol':row['protocol'],'topic':row['topic'],'reason':row['reason'],'summary':row['summary'],'state':row['state'],'version':row['version'],'expires_at':row['expires'],'prepared_at':row['created'],'prepared_by':row['owner'],'confirmed_at':row['confirmed_at'],'confirmed_by':row['owner'] if row['protocol'] else None,'personal_identity_verified':False,'synthetic_only':True,'destination':'local_demo','getnet_identity_verified':False,'resolved':False,'message':'Fila humana demonstrativa local; nenhum envio a Getnet ou aviso externo. Encerramento nao confirma resolucao.'}

    def prepare(self,principal,session,topic,reason,summary):
        binding=self._client(principal,session,True)
        topic=self.tickets._topic(topic)
        if not isinstance(reason,str) or reason not in REASONS: raise TicketError('conflict')
        summary=self._text(summary); now=self.tickets._now()
        with self._db(True) as db:
            row=db.execute('SELECT p.id FROM human_handoffs h JOIN demo_proposals p ON p.id=h.proposal_id WHERE h.realm=? AND p.owner=? AND p.tenant=? AND p.session=? AND p.topic=? AND h.reason=? AND h.summary=? AND p.consumed=0 AND p.expires>?',(self.realm,*binding,topic,reason,summary,now)).fetchone()
            if row: return self._view(self._row(db,row['id']))
            if db.execute('SELECT COUNT(*) FROM demo_proposals').fetchone()[0]>=1000 or db.execute('SELECT COUNT(*) FROM demo_proposals WHERE owner=? AND tenant=? AND session=?',binding).fetchone()[0]>=20: raise TicketError('conflict')
            pid=secrets.token_urlsafe(24)
            db.execute('INSERT INTO demo_proposals(id,owner,tenant,session,topic,created,expires) VALUES(?,?,?,?,?,?,?)',(pid,*binding,topic,now,now+self.tickets.ttl_seconds))
            db.execute('INSERT INTO human_handoffs VALUES(?,?,?,?,?,0)',(pid,self.realm,reason,summary,'awaiting_confirmation'))
            result=self._view(self._row(db,pid))
        return result

    def confirm(self,principal,session,proposal_id,*,confirmed=False):
        self._client(principal,session,True)
        if confirmed is not True: raise TicketError('permission')
        with self._db(True) as db:
            row=self._bound(db,principal,session,proposal_id)
            if row['state']=='awaiting_confirmation':
                if row['expires']<=self.tickets._now(): raise TicketError('expired')
                # A legacy confirm cannot enqueue: reconcile its protocol, never create another.
                if not row['protocol']:
                    db.execute('INSERT INTO demo_tickets VALUES(?,?,?)',(proposal_id,'DEMO-'+secrets.token_hex(12).upper(),self.tickets._now()))
                    db.execute('UPDATE demo_proposals SET consumed=1 WHERE id=?',(proposal_id,))
                db.execute("UPDATE human_handoffs SET state='awaiting_operator',version=1 WHERE proposal_id=?",(proposal_id,))
            result=self._view(self._row(db,proposal_id))
        return result

    def status(self,principal,session,proposal_id):
        self._client(principal,session)
        with self._db() as db:
            row=self._bound(db,principal,session,proposal_id)
            return {**self._view(row),'events':self._history(db,proposal_id)}

    def latest(self,principal,session):
        self._client(principal,session)
        with self._db() as db:
            row=db.execute('SELECT h.proposal_id FROM human_handoffs h JOIN demo_proposals p ON p.id=h.proposal_id JOIN demo_tickets t ON t.proposal_id=p.id WHERE h.realm=? AND p.owner=? AND p.tenant=? AND p.session=? AND p.consumed=1 AND h.state IN (\'awaiting_operator\',\'responded\',\'closed\') ORDER BY t.created DESC,t.rowid DESC LIMIT 1',(self.realm,principal.subject,principal.tenant,session)).fetchone()
            if row is None: return None
            bound=self._bound(db,principal,session,row['proposal_id'])
            return {**self._view(bound),'events':self._history(db,bound['id'])}

    def _history(self,db,proposal_id):
        return [self._event(row) for row in db.execute('SELECT * FROM human_events WHERE proposal_id=? AND realm=? ORDER BY version',(proposal_id,self.realm)).fetchall()]

    def inspect(self,operator,proposal_id):
        self._principal(operator,'handoff:read')
        with self._db() as db:
            row=self._row(db,proposal_id)
            if row['tenant']!=operator.tenant: raise TicketError('permission')
            return {**self._view(row),'events':self._history(db,proposal_id)}

    def queue(self,operator):
        self._principal(operator,'handoff:read')
        with self._db() as db:
            ids=db.execute("SELECT h.proposal_id FROM human_handoffs h JOIN demo_proposals p ON p.id=h.proposal_id WHERE h.realm=? AND p.tenant=? AND h.state IN ('awaiting_operator','responded') ORDER BY p.created LIMIT 1000",(self.realm,operator.tenant)).fetchall()
            return [self._view(self._row(db,r[0])) for r in ids]

    @staticmethod
    def _event(row):
        return {'id':row['id'],'event_id':row['id'],'proposal_id':row['proposal_id'],'kind':row['kind'],'text':row['text'],'version':row['version'],'created':row['created'],'origin':'local_operator','operator_id':row['operator'],'personal_identity_verified':False,'request_id':row['request_id'],'historical_only':True,'authority':False,'synthetic_only':True}

    def _action(self,operator,pid,expected_version,request_id,text,kind):
        self._principal(operator,'handoff:respond')
        self.tickets._id(pid)
        if type(expected_version) is not int or expected_version<1 or not isinstance(request_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,80}',request_id): raise TicketError('conflict')
        text=self._text(text) if kind=='response' else ''
        fingerprint=hashlib.sha256(json.dumps([pid,expected_version,text,kind]).encode()).hexdigest()
        with self._db(True) as db:
            row=self._row(db,pid)
            if row['tenant']!=operator.tenant or row['owner']==operator.subject: raise TicketError('permission')
            old=db.execute('SELECT * FROM human_events WHERE realm=? AND tenant=? AND operator=? AND request_id=?',(self.realm,operator.tenant,operator.subject,request_id)).fetchone()
            if old:
                if old['fingerprint']!=fingerprint: raise TicketError('conflict')
                return self._event(old)
            if kind=='closed' and row['state']!='responded': raise TicketError('conflict')
            if row['state'] not in ('awaiting_operator','responded') or row['version']!=expected_version: raise TicketError('conflict')
            if db.execute('SELECT COUNT(*) FROM human_events WHERE proposal_id=?',(pid,)).fetchone()[0]>=(19 if kind=='response' else 20) or db.execute('SELECT COUNT(*) FROM human_events').fetchone()[0]>=(9000 if kind=='response' else 10000): raise TicketError('conflict')
            event_id=secrets.token_urlsafe(24); version=expected_version+1
            db.execute('INSERT INTO human_events(id,proposal_id,realm,tenant,operator,request_id,fingerprint,kind,text,version,created) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(event_id,pid,self.realm,operator.tenant,operator.subject,request_id,fingerprint,kind,text,version,self.tickets._now()))
            db.execute('UPDATE human_handoffs SET state=?,version=? WHERE proposal_id=?',('responded' if kind=='response' else 'closed',version,pid))
            result=self._event(db.execute('SELECT * FROM human_events WHERE id=?',(event_id,)).fetchone())
        return result

    def respond(self,operator,proposal_id,expected_version,request_id,text):
        return self._action(operator,proposal_id,expected_version,request_id,text,'response')

    def close(self,operator,proposal_id,expected_version,request_id):
        return self._action(operator,proposal_id,expected_version,request_id,'','closed')

    def updates(self,principal,session):
        self._client(principal,session)
        with self._db() as db:
            rows=db.execute('SELECT e.* FROM human_events e JOIN demo_proposals p ON p.id=e.proposal_id WHERE e.realm=? AND p.owner=? AND p.tenant=? AND p.session=? AND e.acked=0 ORDER BY e.created,e.rowid LIMIT 400',(self.realm,principal.subject,principal.tenant,session)).fetchall()
            return [self._event(r) for r in rows]

    def acknowledge(self,principal,session,event_id):
        self._client(principal,session,True); self.tickets._id(event_id)
        with self._db(True) as db:
            row=db.execute('SELECT * FROM human_events WHERE id=? AND realm=?',(event_id,self.realm)).fetchone()
            if row is None: raise TicketError('permission')
            self._bound(db,principal,session,row['proposal_id'])
            db.execute('UPDATE human_events SET acked=1 WHERE id=?',(event_id,))
        return {'event_id':event_id,'acknowledged':True}




