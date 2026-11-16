"""Small loopback-only demo client: token file, no proxies, redirects or token output."""
import argparse
import json
from pathlib import Path
import re
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from urllib.error import HTTPError


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(command, *, token_file, port=8000, message=None, user_id='cliente1988'):
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('Invalid local port')
    if command not in ('configuration', 'chat'):
        raise ValueError('Unsupported local operation')
    path=Path(token_file)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 128:
        raise ValueError('Invalid private credential file')
    token=path.read_text('ascii').strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
        raise ValueError('Invalid private credential file')
    data=None
    if command == 'chat':
        if not isinstance(message,str) or not 1 <= len(message.strip()) <= 4000:
            raise ValueError('Provide a message of 1 to 4000 characters')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',user_id):
            raise ValueError('Invalid synthetic identity')
        data=json.dumps({'message':message,'user_id':user_id}).encode('utf-8')
    req=Request(f'http://127.0.0.1:{port}/{command}',data=data,
        headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    opener=build_opener(ProxyHandler({}),NoRedirect())
    try:
        with opener.open(req,timeout=30) as response:
            payload=response.read(250001)
            if len(payload)>250000:raise ValueError('Response too large')
            if token.encode('ascii') in payload:raise ValueError('Reflected credential rejected')
            body=json.loads(payload)
            if token in json.dumps(body,ensure_ascii=False):raise ValueError('Reflected credential rejected')
            return {'status':response.status,'body':body}
    except HTTPError as exc:
        # No reflected response/URL/headers on error; never repeat a request.
        return {'status':exc.code,'error':'Local API rejected the request; check credential, scopes and configuration.'}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('configuration','chat'))
    parser.add_argument('--token-file',required=True)
    parser.add_argument('--port',type=int,default=8000)
    parser.add_argument('--message')
    parser.add_argument('--user-id',default='cliente1988')
    args=parser.parse_args(argv)
    try:result=request(**vars(args))
    except Exception:
        print(json.dumps({'error':'Local request failed; no retry or remote destination was used.'}))
        return 1
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['status']==200 else 1


if __name__=='__main__':raise SystemExit(main())
