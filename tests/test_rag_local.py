"""Fixtures sinteticas sem segredos, API paga ou rede nos testes."""
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import io
import json
import unittest
from app.rag.core import extract,snapshot,save_snapshot,load_snapshot,Index
from app.rag.fetch import fetch,resolve_public,SOURCES
URL=SOURCES[3]
HTML='<nav>menu</nav><h1>Pix demonstrativo</h1><p>Pix pelo portal demonstrativo.</p><form>senha</form><p>Respondeu à sua dúvida?</p><footer>rodape</footer>'.encode()
def doc():
    data=snapshot(dict(body=HTML,requested_url=URL,final_url=URL,captured_at=datetime.now(timezone.utc).isoformat(),raw_sha256=sha256(HTML).hexdigest()))
    data['reviewed']=True
    return data
class CoreTest(unittest.TestCase):
    def test_clean(self):
        title,chunks=extract(HTML)
        self.assertEqual(title,'Pix demonstrativo');self.assertEqual(chunks,['Pix pelo portal demonstrativo.'])
    def test_missing_marker(self):
        with self.assertRaises(ValueError):extract(b'<h1>Teste</h1><p>Corpo</p>')
    def test_persist_reload(self):
        with TemporaryDirectory() as tmp:
            data=doc();path=save_snapshot(data,tmp)
            self.assertEqual(load_snapshot(path,SOURCES),data)
            self.assertEqual(Index([load_snapshot(path,SOURCES)]).search('pix portal')['status'],'candidates')
    def test_tamper(self):
        with TemporaryDirectory() as tmp:
            path=save_snapshot(doc(),tmp);env=json.loads(path.read_text(encoding='utf-8'));env['payload']['title']='alterado'
            path.write_text(json.dumps(env),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Integridade'):load_snapshot(path,SOURCES)
    def test_unreviewed(self):
        data=doc();data['reviewed']=False
        with self.assertRaises(ValueError):Index([data])
    def test_duplicate_source(self):
        with self.assertRaises(ValueError):Index([doc(),doc()])
    def test_missing_evidence(self):self.assertEqual(Index([doc()]).search('clima Curitiba')['status'],'insufficient_evidence')
    def test_unavailable(self):self.assertEqual(Index([]).search('pix')['status'],'unavailable')
    def test_extractive(self):
        answer=Index([doc()]).answer_extractive('pix portal')
        self.assertEqual(answer['mode'],'extractive');self.assertEqual(answer['candidates'][0]['source'],URL)
    def test_query_limit(self):
        with self.assertRaises(ValueError):Index([]).search('x'*2001)
    def test_idf_cached(self):
        index=Index([doc()])
        with patch('app.rag.core.math.log',side_effect=AssertionError()):index.search('pix')
    def test_atomic_failure_preserves(self):
        with TemporaryDirectory() as tmp:
            data=doc();path=save_snapshot(data,tmp);old=path.read_bytes();data['title']='novo'
            with patch('app.rag.core.os.replace',side_effect=OSError('fixture')):
                with self.assertRaises(OSError):save_snapshot(data,tmp)
            self.assertEqual(path.read_bytes(),old)
class Response:
    def __init__(self,status=200,headers=None,body=b'html'):
        self.status=status;self.headers=headers or {'Content-Type':'text/html'};self.stream=io.BytesIO(body)
    def getheader(self,key,default=None):return self.headers.get(key,default)
    def read(self,n):return self.stream.read(n)
class Conn:
    def __init__(self,response):self.response=response;self.closed=False
    def request(self,*a,**k):pass
    def getresponse(self):return self.response
    def close(self):self.closed=True
class FetchTest(unittest.TestCase):
    def test_fetch(self):
        c=Conn(Response());result=fetch(URL,resolver=lambda _: '93.184.216.34',connection_factory=lambda *_:c)
        self.assertEqual(result['body'],b'html');self.assertTrue(c.closed)
    def test_unapproved_url(self):
        with self.assertRaises(ValueError):fetch('https://127.0.0.1/')
    def test_redirect_not_allowed(self):
        c=Conn(Response(302,{'Location':'https://evil.invalid/'}))
        with self.assertRaises(ValueError):fetch(URL,resolver=lambda _: '93.184.216.34',connection_factory=lambda *_:c)
        self.assertTrue(c.closed)
    def test_dns_mixed(self):
        answers=[(2,1,6,'',('93.184.216.34',443)),(2,1,6,'',('127.0.0.1',443))]
        with patch('app.rag.fetch.socket.getaddrinfo',return_value=answers):
            with self.assertRaises(ValueError):resolve_public('site.getnet.com.br')
    def test_oversized(self):
        c=Conn(Response(body=b'x'*1000001))
        with self.assertRaises(ValueError):fetch(URL,resolver=lambda _: '93.184.216.34',connection_factory=lambda *_:c)
    def test_pdf_refused(self):
        c=Conn(Response(headers={'Content-Type':'application/pdf'}))
        with self.assertRaises(ValueError):fetch(URL,resolver=lambda _: '93.184.216.34',connection_factory=lambda *_:c)
if __name__=='__main__':unittest.main()

class DeadlineTest(unittest.TestCase):
    def test_timeout_terminates_only_child(self):
        from unittest.mock import Mock
        from app.rag.fetch import fetch_bounded
        ctx=Mock();receiver=Mock();sender=Mock();process=Mock()
        ctx.Pipe.return_value=(receiver,sender);ctx.Process.return_value=process
        receiver.poll.return_value=False;process.is_alive.return_value=True
        with patch('multiprocessing.get_context',return_value=ctx):
            with self.assertRaises(TimeoutError):fetch_bounded(URL,timeout=0.1)
        process.terminate.assert_called_once();receiver.close.assert_called_once()
    def test_bounded_success(self):
        from unittest.mock import Mock
        from app.rag.fetch import fetch_bounded
        ctx=Mock();receiver=Mock();sender=Mock();process=Mock()
        ctx.Pipe.return_value=(receiver,sender);ctx.Process.return_value=process
        receiver.poll.return_value=True;receiver.recv.return_value=('ok',{'body':b'fixture'})
        process.is_alive.return_value=False
        with patch('multiprocessing.get_context',return_value=ctx):
            self.assertEqual(fetch_bounded(URL)['body'],b'fixture')
        process.terminate.assert_not_called()
