"""Bounded, integrity-checked local session persistence with optimistic concurrency."""
import hashlib
import hmac
import json
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class Conflict(RuntimeError): pass
class Capacity(RuntimeError): pass
class Unavailable(RuntimeError): pass
class IntegrityUnavailable(Unavailable, ValueError): pass


class Store:
    MAX_BYTES = 262144
    MAX_DEVICES = 64
    MAX_FACTS = 512

    def __init__(self, path):
        self.path = str(Path(path).resolve())
        self.keypath = Path(self.path + '.key')
        target = Path(self.path)
        try:
            if target.exists() != self.keypath.exists():
                raise Unavailable('Session storage unavailable')
            fresh = not target.exists()
            if fresh:
                target.parent.mkdir(parents=True, exist_ok=True)
                with self.keypath.open('xb') as stream:
                    stream.write(secrets.token_bytes(32))
                with target.open('xb'):
                    pass
            self.key = self.keypath.read_bytes()
            if len(self.key) != 32:
                raise Unavailable('Session storage unavailable')
            with self.connection() as db:
                db.execute('BEGIN IMMEDIATE')
                if fresh:
                    db.execute('CREATE TABLE sessions(id TEXT PRIMARY KEY, owner TEXT NOT NULL, version INTEGER NOT NULL, state TEXT NOT NULL, mac TEXT NOT NULL)')
                # Upgrade only authentic legacy records, without changing their state/version.
                for sid, owner, version, payload, mac in db.execute('SELECT id,owner,version,state,mac FROM sessions').fetchall():
                    self._verify(owner, sid, version, payload, mac)
                    if not mac.startswith('v2:'):
                        db.execute('UPDATE sessions SET mac=? WHERE id=?', (self._sign_version(owner, sid, version, payload), sid))
        except IntegrityUnavailable:
            raise
        except (OSError, sqlite3.Error, ValueError, TypeError) as exc:
            raise Unavailable('Session storage unavailable') from None

    @contextmanager
    def connection(self):
        db = None
        try:
            try:
                current_key = self.keypath.read_bytes()
            except OSError:
                raise Unavailable('Session storage unavailable') from None
            if current_key != self.key:
                raise Unavailable('Session storage unavailable')
            db = sqlite3.connect(Path(self.path).as_uri() + '?mode=rw', uri=True, timeout=0.5)
            with db:
                yield db
        except PermissionError:
            raise
        except (sqlite3.Error, OSError):
            raise Unavailable('Session storage unavailable') from None
        finally:
            if db is not None:
                db.close()

    def sign(self, owner, sid, payload):
        """Legacy signature retained only for compatibility and verified migration."""
        return hmac.new(self.key, (owner+'|'+sid+'|'+payload).encode('utf-8'), hashlib.sha256).hexdigest()

    def _sign_version(self, owner, sid, version, payload):
        value = json.dumps([owner, sid, version, payload], ensure_ascii=False, separators=(',', ':'))
        return 'v2:' + hmac.new(self.key, value.encode('utf-8'), hashlib.sha256).hexdigest()

    def _verify(self, owner, sid, version, payload, mac):
        if type(version) is not int or version < 0 or not isinstance(mac, str):
            raise IntegrityUnavailable('Session storage integrity failed')
        expected = self._sign_version(owner, sid, version, payload) if mac.startswith('v2:') else self.sign(owner, sid, payload)
        if not hmac.compare_digest(mac, expected):
            raise IntegrityUnavailable('Session storage integrity failed')
        try:
            state = json.loads(payload)
            if not isinstance(state, dict):
                raise ValueError()
        except (TypeError, ValueError):
            raise IntegrityUnavailable('Session storage integrity failed') from None
        return state

    @staticmethod
    def empty():
        return {'devices': {}, 'facts': {}, 'observations': [], 'events': [], 'pending': [], 'focus': [], 'requests': [], 'goals': []}

    def _payload(self, state):
        if not isinstance(state, dict):
            raise Capacity('Session state exceeds supported bounds')
        for name, limit in [('devices', self.MAX_DEVICES), ('facts', self.MAX_FACTS)]:
            if not isinstance(state.get(name, {}), dict) or len(state.get(name, {})) > limit:
                raise Capacity('Session state exceeds supported bounds')
        try:
            payload = json.dumps(state, ensure_ascii=False, allow_nan=False)
            size = len(payload.encode('utf-8'))
        except (TypeError, ValueError, UnicodeError, RecursionError):
            raise Capacity('Session state exceeds supported bounds') from None
        if size > self.MAX_BYTES:
            raise Capacity('Session state exceeds supported bounds')
        return payload

    def create(self, owner):
        sid = secrets.token_urlsafe(24)
        payload = self._payload(self.empty())
        with self.connection() as db:
            db.execute('INSERT INTO sessions VALUES(?,?,0,?,?)', (sid, owner, payload, self._sign_version(owner, sid, 0, payload)))
        return sid

    def read(self, owner, sid):
        with self.connection() as db:
            row = db.execute('SELECT version,state,mac FROM sessions WHERE id=? AND owner=?', (sid, owner)).fetchone()
        if row is None:
            raise PermissionError('Session unavailable')
        return row[0], self._verify(owner, sid, *row)

    def assert_version(self, owner, sid, expected):
        version, _ = self.read(owner, sid)
        if version != expected:
            raise Conflict('Session changed; no stale response')
        return version

    def commit(self, owner, sid, version, state):
        payload = self._payload(state)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT version,state,mac FROM sessions WHERE id=? AND owner=?', (sid, owner)).fetchone()
            if row is None:
                raise PermissionError('Session unavailable')
            self._verify(owner, sid, *row)
            if row[0] != version:
                raise Conflict('Session changed; no stale write')
            n = db.execute('UPDATE sessions SET version=version+1,state=?,mac=? WHERE id=? AND owner=? AND version=?', (payload, self._sign_version(owner, sid, version+1, payload), sid, owner, version)).rowcount
            if n != 1:
                raise Conflict('Session changed; no stale write')

    def reset(self, owner, sid):
        version, _ = self.read(owner, sid)
        self.commit(owner, sid, version, self.empty())



