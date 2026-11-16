"""Explicit LOCAL administration; never an HTTP or model tool. No token stdout."""
import argparse,json,os
from pathlib import Path
from app.access_store import AccessStore,AccessError,ALLOWED_SCOPES

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',required=True);p.add_argument('--per-minute',type=int,default=30);p.add_argument('--global-per-minute',type=int,default=180)
    commands=p.add_subparsers(dest='command',required=True)
    commands.add_parser('init')
    issue=commands.add_parser('issue');issue.add_argument('--subject',required=True);issue.add_argument('--tenant',required=True);issue.add_argument('--scope',action='append',required=True,choices=sorted(ALLOWED_SCOPES));issue.add_argument('--ttl',type=int,default=3600);issue.add_argument('--output',required=True)
    revoke=commands.add_parser('revoke');revoke.add_argument('--token-file',required=True)
    args=p.parse_args()
    try:
        store=AccessStore(args.db,initialize=args.command=='init',per_minute=args.per_minute,global_per_minute=args.global_per_minute)
        if args.command=='issue':
            target=Path(args.output).resolve();repo=Path(__file__).resolve().parent.parent
            if target==repo or repo in target.parents:raise ValueError('Credential output must be outside the repository')
            # Exclusive creation, private mode on POSIX; Windows inherits directory ACL.
            fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            token=None
            try:
                with os.fdopen(fd,'w',encoding='ascii') as stream:
                    token=store.issue(args.subject,args.tenant,frozenset(args.scope),ttl_seconds=args.ttl)
                    stream.write(token+'\n')
            except Exception:
                if token:
                    try:store.revoke(token)
                    except Exception:p.exit(3,"Emissao e salvamento nao reconciliados; pode restar credencial ativa. Nao use o arquivo ate revisar o cadastro local.\n")
                raise
        elif args.command=='revoke':store.revoke(Path(args.token_file).read_text('ascii').strip())
    except Exception:p.exit(2,'Administracao local nao concluida; nenhum segredo foi exibido.\n')
    print(json.dumps({'action':args.command,'completed':True,'getnet_identity_verified':False}))
if __name__=='__main__':main()
