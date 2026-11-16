"""Explicit offline bootstrap of NEW local demonstration state; no token stdout."""
import argparse
import json
import os
from pathlib import Path
from app.access_store import AccessStore
from app.context_store import Store

CLIENT_SCOPES=frozenset({'chat:use','configuration:read','context:reset','terminal:read','recebiveis:read'})

def initialize(state_dir, *, ttl=3600):
    if type(ttl) is not int or not 1 <= ttl <= 86400:
        raise ValueError('Invalid credential lifetime')
    root=Path(state_dir).resolve()
    repo=Path(__file__).resolve().parents[1]
    if root==repo or repo in root.parents:
        raise ValueError('State must be outside the repository')
    # The parent directory is operator-owned. Exclusive mkdir is the concurrency
    # gate. A partial failure is intentionally preserved, never retried/reset.
    if not root.is_dir():raise ValueError('Create a private state directory first')
    target=root/'local'
    target.mkdir(mode=0o700)
    store=None;token=None
    try:
        store=AccessStore(target/'access.db',initialize=True)
        Store(target/'state.db')
        fd=os.open(target/'client.token',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w',encoding='ascii') as stream:
            token=store.issue('cliente1988','loja_ficticia_A',CLIENT_SCOPES,ttl_seconds=ttl)
            stream.write(token+'\n')
            stream.flush();os.fsync(stream.fileno())
        with (target/'setup.complete').open('x',encoding='ascii') as stream:
            stream.write('local-demo-v1\n')
    except Exception:
        if store is not None and token is not None:
            try:store.revoke(token)
            except Exception:pass
        raise RuntimeError('Setup incomplete; preserve partial state and review locally. Credential status may be uncertain.') from None
    return {'completed':True,'authentication':'local_opaque_token','getnet_identity_verified':False,
            'subject':'cliente1988','token_file':'local/client.token','credential_ttl_seconds':ttl,
            'provider_calls':0,'budget_initialized':False}

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir',required=True)
    parser.add_argument('--ttl',type=int,default=3600)
    args=parser.parse_args(argv)
    try:result=initialize(args.state_dir,ttl=args.ttl)
    except Exception:
        print('Setup refused or incomplete. Existing state preserved; inspect locally before any administrative recovery.')
        return 1
    print(json.dumps(result));return 0

if __name__=='__main__':raise SystemExit(main())
