"""Local opaque access credentials and SQLite quotas, not Getnet identity.

Administration is an explicit in-process operation. Never expose issue/revoke as
unauthenticated HTTP routes. Only token digests are stored; raw tokens are returned
once by issue and must not be logged. Grants remain internal to the server.
"""
from contextlib import closing, contextmanager
from dataclasses import dataclass, field
import hashlib
import json
import math
from pathlib import Path
import re
import secrets
import sqlite3
import time
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.support import Principal

_MESSAGES = {
    'invalid': 'Credencial ausente, invalida, expirada ou revogada.',
    'forbidden': 'Operacao nao permitida neste contexto.',
    'limited': 'Limite temporario de requisicoes atingido.',
    'unavailable': 'Controle de acesso temporariamente indisponivel.',
}
_STATUS = {'invalid':401, 'forbidden':403, 'limited':429, 'unavailable':503}
ALLOWED_SCOPES = frozenset({'chat:use','context:reset','recebiveis:read','terminal:read',
                            'demo_ticket:read','demo_ticket:write','configuration:read','handoff:read','handoff:respond'})

class AccessError(RuntimeError):
    def __init__(self, code):
        if code not in _MESSAGES:
            raise ValueError('Unknown access error')
        self.code = code
        self.status_code = _STATUS[code]
        self.retry_after = 60 if code == 'limited' else None
        super().__init__(_MESSAGES[code])

@dataclass(frozen=True)
class AccessGrant:
    principal: 'Principal'
    credential_id: str = field(repr=False)

class AccessStore:
    """Shared rolling-window quotas; all validation fails closed on store errors."""
    WINDOW_SECONDS = 60
    SESSION_PER_MINUTE = 5
    MAX_CREDENTIALS = 4096

    def __init__(self, path, *, clock=time.time, initialize=False, per_minute=30, global_per_minute=180):
        if (type(initialize) is not bool or type(per_minute) is not int or
            type(global_per_minute) is not int or not 1 <= per_minute <= 1000 or
            not per_minute <= global_per_minute <= 10000):
            raise ValueError('Invalid access configuration')
        self.path = Path(path)
        self.clock = clock
        self.per_minute = per_minute
        self.global_per_minute = global_per_minute
        self._realm = None
        if initialize:
            self._initialize()
        with self._db() as db:
            self._config(db)

    @property
    def realm(self):
        """Persistent registry identity, not a bearer credential."""
        return self._realm

    def _initialize(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(str(self.path), timeout=.5, isolation_level=None)) as db:
                db.execute('BEGIN IMMEDIATE')
                try:
                    db.execute('''CREATE TABLE IF NOT EXISTS access_config(
                        singleton INTEGER PRIMARY KEY CHECK(singleton=1), version INTEGER NOT NULL,
                        principal_limit INTEGER NOT NULL, global_limit INTEGER NOT NULL, last_seen REAL NOT NULL,
                        realm TEXT NOT NULL)''')
                    db.execute('CREATE TABLE IF NOT EXISTS access_principals(subject TEXT PRIMARY KEY, tenant TEXT NOT NULL)')
                    db.execute('''CREATE TABLE IF NOT EXISTS access_credentials(
                        credential_id TEXT PRIMARY KEY, digest TEXT NOT NULL UNIQUE,
                        subject TEXT NOT NULL, tenant TEXT NOT NULL, scopes TEXT NOT NULL,
                        expires REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0 CHECK(revoked IN (0,1)))''')
                    db.execute('''CREATE TABLE IF NOT EXISTS access_events(
                        bucket TEXT NOT NULL CHECK(bucket IN ('request','session','ingress')),
                        owner TEXT NOT NULL, at REAL NOT NULL)''')
                    db.execute('CREATE INDEX IF NOT EXISTS access_events_window ON access_events(bucket,at,owner)')
                    db.execute('INSERT OR IGNORE INTO access_config VALUES(1,2,?,?,?,?)',
                               (self.per_minute,self.global_per_minute,self._now(),secrets.token_hex(16)))
                    self._config(db)
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
        except AccessError:
            raise
        except Exception:
            raise AccessError('unavailable') from None

    @contextmanager
    def _db(self):
        db = None
        try:
            # mode=rw prevents silently replacing a deleted database in a race.
            uri = self.path.resolve().as_uri() + '?mode=rw'
            db = sqlite3.connect(uri, uri=True, timeout=.5, isolation_level=None)
            db.row_factory = sqlite3.Row
            db.execute('BEGIN IMMEDIATE')
            self._config(db)
            yield db
            db.commit()
        except AccessError:
            if db is not None:
                try: db.rollback()
                except Exception: pass
            raise
        except Exception:
            if db is not None:
                try: db.rollback()
                except Exception: pass
            raise AccessError('unavailable') from None
        finally:
            if db is not None:
                try: db.close()
                except Exception: pass

    def _config(self, db):
        # Check the expected schema too; initialize=False never creates tables.
        db.execute('SELECT subject,tenant FROM access_principals LIMIT 0')
        db.execute('SELECT credential_id,digest,subject,tenant,scopes,expires,revoked FROM access_credentials LIMIT 0')
        db.execute('SELECT bucket,owner,at FROM access_events LIMIT 0')
        rows = db.execute('SELECT version,principal_limit,global_limit,realm FROM access_config').fetchall()
        if len(rows) != 1 or tuple(rows[0])[:3] != (2,self.per_minute,self.global_per_minute):
            raise AccessError('unavailable')
        realm = rows[0][3]
        if type(realm) is not str or not re.fullmatch(r'[a-f0-9]{32}',realm):
            raise AccessError('unavailable')
        if self._realm is not None and self._realm != realm:
            # A replacement registry cannot silently inherit this process's state.
            raise AccessError('unavailable')
        self._realm = realm

    def _now(self):
        try:
            value = self.clock()
            if type(value) not in (int,float) or not math.isfinite(value) or not 0 <= value <= 253402200000:
                raise ValueError()
            return float(value)
        except Exception:
            raise AccessError('unavailable') from None

    def _checked_now(self, db):
        now = self._now()
        previous = db.execute('SELECT last_seen FROM access_config WHERE singleton=1').fetchone()[0]
        if not math.isfinite(previous) or now < previous:
            raise AccessError('unavailable')
        db.execute('UPDATE access_config SET last_seen=? WHERE singleton=1',(now,))
        return now

    @staticmethod
    def _digest(rawtoken):
        if type(rawtoken) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{43}', rawtoken):
            raise AccessError('invalid')
        return hashlib.sha256(rawtoken.encode('ascii')).hexdigest()

    @staticmethod
    def _identity(subject, tenant, scopes):
        if (type(subject) is not str or type(tenant) is not str or
            not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',subject) or
            not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',tenant) or
            not isinstance(scopes,(set,frozenset,list,tuple)) or len(scopes)>32 or
            any(type(s) is not str or s not in ALLOWED_SCOPES for s in scopes)):
            raise AccessError('forbidden')
        return json.dumps(sorted(set(scopes)),separators=(',',':'))

    def issue(self, subject, tenant, scopes, ttl_seconds=3600):
        """Administrative only. Return the raw credential once; never log it."""
        encoded = self._identity(subject,tenant,scopes)
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 86400:
            raise AccessError('forbidden')
        with self._db() as db:
            now = self._checked_now(db)
            if db.execute('SELECT COUNT(*) FROM access_credentials').fetchone()[0] >= self.MAX_CREDENTIALS:
                raise AccessError('unavailable')
            bound = db.execute('SELECT tenant FROM access_principals WHERE subject=?',(subject,)).fetchone()
            if bound is not None and bound[0] != tenant:
                raise AccessError('forbidden')
            db.execute('INSERT OR IGNORE INTO access_principals(subject,tenant) VALUES(?,?)',(subject,tenant))
            token = secrets.token_urlsafe(32)
            db.execute('INSERT INTO access_credentials VALUES(?,?,?,?,?,?,0)',
                       (secrets.token_hex(16),self._digest(token),subject,tenant,encoded,now+ttl_seconds))
        return token

    def revoke(self, rawtoken):
        digest = self._digest(rawtoken)
        with self._db() as db:
            self._checked_now(db)
            changed = db.execute('UPDATE access_credentials SET revoked=1 WHERE digest=?',(digest,)).rowcount
            if changed != 1:
                raise AccessError('invalid')

    def _grant(self, row, now):
        if row is None:
            raise AccessError('invalid')
        if type(row['expires']) not in (int,float) or not math.isfinite(row['expires']) or row['revoked'] not in (0,1):
            raise AccessError('unavailable')
        if row['revoked'] or row['expires'] <= now:
            raise AccessError('invalid')
        try:
            from app.support import Principal
            scopes = json.loads(row['scopes'])
            if not isinstance(scopes,list):
                raise ValueError()
            encoded = self._identity(row['subject'],row['tenant'],scopes)
            if encoded != row['scopes'] or not re.fullmatch(r'[a-f0-9]{32}',row['credential_id']):
                raise ValueError()
            return AccessGrant(Principal(row['subject'],row['tenant'],frozenset(scopes)),row['credential_id'])
        except Exception:
            raise AccessError('unavailable') from None

    def authenticate(self, rawtoken):
        digest = self._digest(rawtoken)
        with self._db() as db:
            now = self._checked_now(db)
            row = db.execute('SELECT * FROM access_credentials WHERE digest=?',(digest,)).fetchone()
            result = self._grant(row,now)
        return result

    def _revalidate(self, db, grant, now):
        if type(grant) is not AccessGrant or type(grant.credential_id) is not str or not re.fullmatch(r'[a-f0-9]{32}',grant.credential_id):
            raise AccessError('forbidden')
        row = db.execute('SELECT * FROM access_credentials WHERE credential_id=?',(grant.credential_id,)).fetchone()
        current = self._grant(row,now)
        if current != grant:
            raise AccessError('forbidden')
        return current

    def revalidate(self, grant):
        with self._db() as db:
            result = self._revalidate(db,grant,self._checked_now(db))
        return result

    def _consume(self, db, bucket, owner, owner_limit, now):
        cutoff = now-self.WINDOW_SECONDS
        # Only ephemeral quota events expire. Credentials/revocations are retained.
        db.execute('DELETE FROM access_events WHERE at<=?',(cutoff,))
        total = db.execute('SELECT COUNT(*) FROM access_events WHERE bucket=? AND at>?',(bucket,cutoff)).fetchone()[0]
        count = db.execute('SELECT COUNT(*) FROM access_events WHERE bucket=? AND owner=? AND at>?',(bucket,owner,cutoff)).fetchone()[0]
        if total >= self.global_per_minute or count >= owner_limit:
            raise AccessError('limited')
        db.execute('INSERT INTO access_events(bucket,owner,at) VALUES(?,?,?)',(bucket,owner,now))
        return {'remaining':min(self.global_per_minute-total-1,owner_limit-count-1)}

    def consume(self, grant, bucket='request'):
        if bucket not in ('request','session'):
            raise AccessError('forbidden')
        with self._db() as db:
            now = self._checked_now(db)
            current = self._revalidate(db,grant,now)
            principal = current.principal
            owner = hashlib.sha256(json.dumps([principal.subject,principal.tenant],separators=(',',':')).encode()).hexdigest()
            limit = self.per_minute if bucket=='request' else self.SESSION_PER_MINUTE
            result = self._consume(db,bucket,owner,limit,now)
        return result

    def ingress(self):
        """Call before parsing/authenticating bearer credentials; global bound."""
        with self._db() as db:
            result = self._consume(db,'ingress','',self.global_per_minute,self._checked_now(db))
        return result
