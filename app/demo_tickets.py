"""Local synthetic support requests; no Getnet or human-service integration.

The caller supplies a SERVER demo principal and an already validated session.
Binding is isolation within a demonstration, not authentication of real clients.
Confirmation runs synchronously, outside the read-tool timeout worker.
"""
from contextlib import contextmanager, closing
from datetime import datetime, timezone
import math
from pathlib import Path
import re
import secrets
import sqlite3
import time
from typing import Literal

TicketTopic = Literal['conectividade', 'recebiveis', 'terminal']
TOPICS = frozenset(('conectividade', 'recebiveis', 'terminal'))
_MESSAGES = {
    'disabled': 'Solicitacoes demonstrativas estao desativadas.',
    'permission': 'Solicitacao demonstrativa indisponivel para este contexto.',
    'expired': 'A proposta expirou; prepare e confirme uma nova proposta.',
    'conflict': 'Proposta divergente, consumida de forma inconsistente ou limite local atingido.',
    'unavailable': 'Registro local indisponivel. Nenhum resultado foi confirmado.',
    'unconfirmed': 'Resultado local nao confirmado. Consulte a proposta antes de qualquer nova tentativa.',
}
class TicketError(RuntimeError):
    def __init__(self, code):
        if code not in _MESSAGES:
            raise ValueError('Unknown ticket error')
        self.code = code
        super().__init__(_MESSAGES[code])

class TicketStore:
    """Bounded SQLite demo store. No raw message, personal data or model output."""
    def __init__(self, path, *, enabled=False, clock=time.time, ttl_seconds=600):
        if type(enabled) is not bool or type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 3600:
            raise ValueError('Invalid demo ticket configuration')
        self.path = Path(path)
        self.enabled = enabled
        self.clock = clock
        self.ttl_seconds = ttl_seconds
        if enabled:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with closing(sqlite3.connect(str(self.path), timeout=.25)) as db, db:
                    db.executescript('''
                        PRAGMA foreign_keys=ON;
                        CREATE TABLE IF NOT EXISTS demo_proposals(
                            id TEXT PRIMARY KEY, owner TEXT NOT NULL, tenant TEXT NOT NULL,
                            session TEXT NOT NULL, topic TEXT NOT NULL
                                CHECK(topic IN ('conectividade','recebiveis','terminal')),
                            created REAL NOT NULL, expires REAL NOT NULL,
                            consumed INTEGER NOT NULL DEFAULT 0 CHECK(consumed IN (0,1)));
                        CREATE TABLE IF NOT EXISTS demo_tickets(
                            proposal_id TEXT PRIMARY KEY REFERENCES demo_proposals(id),
                            protocol TEXT NOT NULL UNIQUE, created REAL NOT NULL);
                    ''')
            except Exception:
                raise TicketError('unavailable') from None

    def _authorize(self, principal, session, *, write=False):
        if not self.enabled:
            raise TicketError('disabled')
        from app.support import Principal
        scope = 'demo_ticket:write' if write else 'demo_ticket:read'
        fixtures = {'demo_A':'loja_ficticia_A', 'cliente1988':'loja_ficticia_A', 'demo_B':'loja_ficticia_B'}
        if (not isinstance(principal, Principal) or scope not in principal.scopes or
            fixtures.get(principal.subject) != principal.tenant or
            type(session) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{20,80}', session)):
            raise TicketError('permission')
        return (principal.subject, principal.tenant, session)

    @staticmethod
    def _topic(topic):
        if type(topic) is not str or topic not in TOPICS:
            raise TicketError('conflict')
        return topic

    @staticmethod
    def _id(proposal_id):
        if type(proposal_id) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{32}', proposal_id):
            raise TicketError('permission')
        return proposal_id

    def _now(self):
        try:
            now = float(self.clock())
            if not math.isfinite(now) or not 0 <= now <= 253402296000:
                raise ValueError()
            return now
        except Exception:
            raise TicketError('unavailable') from None

    def _commit(self, db):
        db.commit()

    @contextmanager
    def _connection(self, *, write=False):
        db = None
        committing = False
        try:
            # Missing state is never silently recreated as an empty ledger.
            if not self.path.is_file():
                raise TicketError('unavailable')
            db = sqlite3.connect(str(self.path), timeout=.25, isolation_level=None)
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA foreign_keys=ON')
            if write:
                db.execute('BEGIN IMMEDIATE')
            yield db
            if write:
                committing = True
                self._commit(db)
        except TicketError:
            if db is not None and db.in_transaction:
                db.rollback()
            raise
        except Exception:
            if db is not None and db.in_transaction:
                db.rollback()
            raise TicketError('unconfirmed' if committing else 'unavailable') from None
        finally:
            if db is not None:
                db.close()

    @staticmethod
    def _proposal(row):
        return {'proposal_id':row['id'], 'topic':row['topic'],
                'expires_at':datetime.fromtimestamp(row['expires'], timezone.utc).isoformat(),
                'state':'awaiting_confirmation', 'synthetic_only':True, 'authenticated':False,
                'destination':'local_demo',
                'message':'Proposta local de demonstracao: ainda nao ha protocolo registrado. Confirme explicitamente na interface. Nao sera enviada a Getnet nem notificara atendente.'}

    @staticmethod
    def _receipt(row):
        return {'proposal_id':row['id'], 'topic':row['topic'], 'protocol':row['protocol'],
                'state':'registered_local', 'synthetic_only':True, 'authenticated':False,
                'destination':'local_demo',
                'message':'Solicitacao de demonstracao registrada somente neste prototipo local. Nao foi enviada a Getnet e nenhum atendente foi notificado.'}

    @staticmethod
    def _bound(db, binding, proposal_id):
        row = db.execute('''SELECT p.*, t.protocol FROM demo_proposals p
            LEFT JOIN demo_tickets t ON t.proposal_id=p.id
            WHERE p.owner=? AND p.tenant=? AND p.session=? AND p.id=?''', (*binding,proposal_id)).fetchone()
        if row is None:
            raise TicketError('permission')
        if bool(row['consumed']) != bool(row['protocol']):
            raise TicketError('conflict')
        return row

    def offer(self, principal, session, topic):
        binding = self._authorize(principal, session, write=True)
        topic = self._topic(topic)
        now = self._now()
        with self._connection(write=True) as db:
            row = db.execute('''SELECT * FROM demo_proposals WHERE owner=? AND tenant=?
                AND session=? AND topic=? AND consumed=0 AND expires>? ORDER BY created DESC LIMIT 1''',
                (*binding,topic,now)).fetchone()
            if row is None:
                count = db.execute('SELECT COUNT(*) FROM demo_proposals').fetchone()[0]
                per_session = db.execute('SELECT COUNT(*) FROM demo_proposals WHERE owner=? AND tenant=? AND session=?',binding).fetchone()[0]
                if count >= 1000 or per_session >= 20:
                    raise TicketError('conflict')
                proposal_id = secrets.token_urlsafe(24)
                db.execute('INSERT INTO demo_proposals(id,owner,tenant,session,topic,created,expires) VALUES(?,?,?,?,?,?,?)',
                    (proposal_id,*binding,topic,now,now+self.ttl_seconds))
                row = db.execute('SELECT * FROM demo_proposals WHERE id=?',(proposal_id,)).fetchone()
            result = self._proposal(row)
        return result

    def confirm(self, principal, session, proposal_id, topic, *, confirmed=False):
        binding = self._authorize(principal, session, write=True)
        if confirmed is not True:
            raise TicketError('permission')
        topic = self._topic(topic)
        proposal_id = self._id(proposal_id)
        now = self._now()
        with self._connection(write=True) as db:
            row = self._bound(db,binding,proposal_id)
            if row['topic'] != topic:
                raise TicketError('conflict')
            if not row['protocol']:
                if row['expires'] <= now:
                    raise TicketError('expired')
                db.execute('UPDATE demo_proposals SET consumed=1 WHERE id=?',(proposal_id,))
                db.execute('INSERT INTO demo_tickets(proposal_id,protocol,created) VALUES(?,?,?)',
                    (proposal_id,'DEMO-'+secrets.token_hex(12).upper(),now))
                row = self._bound(db,binding,proposal_id)
            result = self._receipt(row)
        return result

    def lookup(self, principal, session, proposal_id):
        binding = self._authorize(principal, session)
        proposal_id = self._id(proposal_id)
        with self._connection() as db:
            row = self._bound(db,binding,proposal_id)
            if row['protocol']:
                return self._receipt(row)
            if row['expires'] <= self._now():
                raise TicketError('expired')
            return self._proposal(row)

    def latest(self, principal, session):
        binding = self._authorize(principal, session)
        with self._connection() as db:
            row = db.execute('''SELECT p.*,t.protocol FROM demo_proposals p
                JOIN demo_tickets t ON t.proposal_id=p.id
                WHERE p.owner=? AND p.tenant=? AND p.session=? AND p.consumed=1
                ORDER BY t.created DESC,t.rowid DESC LIMIT 1''',binding).fetchone()
            return self._receipt(row) if row is not None else None
