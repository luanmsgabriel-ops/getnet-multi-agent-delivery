"""SQLite isolado: CAS por sessão e eventos por componente dependente."""
import sqlite3,json,secrets,hmac,hashlib
from contextlib import contextmanager
from pathlib import Path
class Conflict(RuntimeError): pass
class Store:
    def __init__(self,path):
        self.path=str(path);Path(path).parent.mkdir(parents=True,exist_ok=True)
        keypath=Path(str(path)+'.key')
        try:
            with keypath.open('xb') as f:f.write(secrets.token_bytes(32))
        except FileExistsError:pass
        self.key=keypath.read_bytes()
        with self.connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, owner TEXT NOT NULL, version INTEGER NOT NULL, state TEXT NOT NULL, mac TEXT NOT NULL)')
    @contextmanager
    def connection(self):
        db=sqlite3.connect(self.path,timeout=5)
        try:
            with db: yield db
        finally: db.close()
    def create(self,owner):
        sid=secrets.token_urlsafe(24)
        payload=json.dumps(self.empty());mac=self.sign(owner,sid,payload)
        with self.connection() as db: db.execute('INSERT INTO sessions VALUES(?,?,0,?,?)',(sid,owner,payload,mac))
        return sid
    def sign(self,owner,sid,payload):return hmac.new(self.key,(owner+'|'+sid+'|'+payload).encode('utf-8'),hashlib.sha256).hexdigest()
    @staticmethod
    def empty():return {'devices':{},'facts':{},'observations':[],'events':[],'pending':[],'focus':[],'requests':[],'goals':[]}
    def read(self,owner,sid):
        with self.connection() as db: row=db.execute('SELECT version,state,mac FROM sessions WHERE id=? AND owner=?',(sid,owner)).fetchone()
        if row is None:raise PermissionError('Session unavailable')
        if not hmac.compare_digest(row[2],self.sign(owner,sid,row[1])):raise ValueError('Stored state integrity failed')
        return row[0],json.loads(row[1])
    def commit(self,owner,sid,version,state):
        with self.connection() as db:
            payload=json.dumps(state,ensure_ascii=False)
            n=db.execute('UPDATE sessions SET version=version+1,state=?,mac=? WHERE id=? AND owner=? AND version=?',(payload,self.sign(owner,sid,payload),sid,owner,version)).rowcount
            if n!=1:raise Conflict('Session changed; no stale write')
    def reset(self,owner,sid):
        version,_=self.read(owner,sid);self.commit(owner,sid,version,self.empty())
