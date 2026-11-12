"""Importacao offline de manuais oficiais; nunca executa scripts/links do PDF."""
from io import BytesIO
from datetime import datetime, timezone
from hashlib import sha256
from urllib.parse import urlsplit
import multiprocessing
from .fetch import PinnedHTTPS,resolve_public

PDF_SOURCES = (
 'https://site.getnet.com.br/wp-content/uploads/2025/09/Manul-GetSmart.pdf',
 'https://site.getnet.com.br/wp-content/uploads/2024/01/Manul_GetClassica.pdf',
 'https://site.getnet.com.br/wp-content/uploads/2025/06/Manul_GetClassica_-2.pdf',
 'https://site.getnet.com.br/wp-content/uploads/2026/06/getnet_12_06-26_Manul_GetClassica_V2.pdf',
)
MAX_PDF_BYTES=10_000_000

def extract_pages(raw):
    if not isinstance(raw,bytes) or not raw.startswith(b'%PDF-') or len(raw)>MAX_PDF_BYTES:
        raise ValueError('PDF invalido/excessivo')
    from pypdf import PdfReader
    reader=PdfReader(BytesIO(raw),strict=True)
    if reader.is_encrypted:raise ValueError('PDF protegido nao suportado')
    if not 1<=len(reader.pages)<=30:raise ValueError('Quantidade de paginas excedida')
    pages=[]
    for page in reader.pages:
        text=' '.join((page.extract_text() or '').split())
        if len(text)>20000:raise ValueError('Texto de pagina excedido')
        pages.append(text)
    if not any(pages):raise ValueError('PDF sem texto; revisao/OCR necessario')
    return pages

def capture(url):
    if url not in PDF_SOURCES:raise ValueError('Fonte PDF nao aprovada')
    parsed=urlsplit(url);conn=PinnedHTTPS(parsed.hostname,resolve_public(parsed.hostname))
    try:
        conn.request('GET',parsed.path,headers={'Host':parsed.hostname,'Accept':'application/pdf','Accept-Encoding':'identity','Connection':'close'})
        response=conn.getresponse()
        if response.status!=200:raise ValueError('HTTP inesperado; redirects nao permitidos')
        if response.getheader('Content-Type','').split(';')[0].strip().lower()!='application/pdf':raise ValueError('MIME inesperado')
        if response.getheader('Content-Encoding','identity').lower()!='identity':raise ValueError('Compressao nao permitida')
        size=response.getheader('Content-Length')
        if size and (not size.isdecimal() or int(size)>MAX_PDF_BYTES):raise ValueError('Tamanho invalido')
        raw=response.read(MAX_PDF_BYTES+1)
        if size and len(raw)!=int(size):raise ValueError('Corpo truncado')
    finally:conn.close()
    pages=extract_pages(raw)
    return {'url':url,'captured_at':datetime.now(timezone.utc).isoformat(),'raw_sha256':sha256(raw).hexdigest(),'pages':pages,'reviewed':False}

def _worker(sender,url):
    try:sender.send(('ok',capture(url)))
    except Exception as exc:sender.send(('error',type(exc).__name__))
    finally:sender.close()

def capture_bounded(url):
    if url not in PDF_SOURCES:raise ValueError('Fonte PDF nao aprovada')
    ctx=multiprocessing.get_context('spawn');receiver,sender=ctx.Pipe(duplex=False)
    process=ctx.Process(target=_worker,args=(sender,url),daemon=True);process.start();sender.close()
    try:
        if not receiver.poll(25):raise TimeoutError('Prazo PDF excedido')
        status,result=receiver.recv()
        if status!='ok':raise ValueError('Captura PDF falhou: '+result)
        return result
    finally:
        receiver.close();process.join(timeout=1)
        if process.is_alive():process.terminate();process.join(timeout=2)


def as_snapshot(capture):
    """Snapshot editorial não revisado; preserva página, origem e hash bruto.

    Apenas os PDFs já expostos na CLI; captura não publica no índice de serviço.
    Limites de extração são aplicados no subprocesso de capture_bounded.
    """
    from .fetch import SOURCES
    url=capture['url']
    if url not in SOURCES or url not in PDF_SOURCES:raise ValueError('Fonte PDF não exposta na CLI')
    chunks=[]
    for number,page in enumerate(capture['pages'],1):
        # Keep every word and the page label across bounded chunks.
        current=f'Página {number}: '
        for word in page.split():
            if len(word)>1100:raise ValueError('Palavra PDF excessiva')
            if len(current)+len(word)+1>1200:
                chunks.append(current.strip());current=f'Página {number} (continuação): '
            current+=word+' '
        if page.strip():chunks.append(current.strip())
    if not chunks:raise ValueError('PDF sem texto')
    return {'version':1,'requested_url':url,'final_url':url,'captured_at':capture['captured_at'],
            'raw_sha256':capture['raw_sha256'],'title':'Manual oficial — '+url.rsplit('/',1)[-1],
            'chunks':chunks,'market':'BR','reviewed':False}
