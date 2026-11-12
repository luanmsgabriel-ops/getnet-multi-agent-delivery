"""Coleta HTTPS restrita a fontes publicas aprovadas; sem proxy ou credenciais."""
from datetime import datetime, timezone
from hashlib import sha256
from urllib.parse import urlsplit, urljoin
import http.client
import socket
import ssl
import ipaddress
from .core import MAX_BYTES

SOURCES = (
 'https://www.getnet.net/', 'https://www.getnet.net/en', 'https://www.getnet.net/en/',
 'https://site.getnet.com.br/get-ajuda-pix/como-habilitar-pix-pelo-portal/',
 'https://site.getnet.com.br/get-ajuda-gestao-de-vendas/quais-possiveis-status-das-minhas-vendas/',
 'https://site.getnet.com.br/get-ajuda-erros-maquininha/erro-adq-1-19/',
 'https://site.getnet.com.br/crediario/', 'https://site.getnet.com.br/link-de-pagamento/',
 'https://site.getnet.com.br/get-ajuda-whatsapp-business/descontinuacao-whatsapp-business/',
 'https://site.getnet.com.br/get-ajuda-antecipacao-de-venda/como-antecipar-sua-vendas-pelo-app/',
 'https://site.getnet.com.br/get-ajuda-configuracoes/como-configurar-o-wi-fi-na-sua-maquininha-getnet/',
 'https://site.getnet.com.br/wp-content/uploads/2025/09/Manul-GetSmart.pdf',
 'https://site.getnet.com.br/wp-content/uploads/2026/06/getnet_12_06-26_Manul_GetClassica_V2.pdf',
 'https://site.getnet.com.br/duvidas/',
)

class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, ip, *, context=None):
        context = context if context is not None else ssl.create_default_context()
        if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
            raise ValueError('TLS exige certificado e hostname verificados')
        super().__init__(host, timeout=10, context=context)
        self.ip = ip
    def connect(self):
        family = socket.AF_INET6 if ':' in self.ip else socket.AF_INET
        raw = socket.socket(family, socket.SOCK_STREAM)
        raw.settimeout(10)
        try:
            raw.connect((self.ip,443))
            self.sock = self._context.wrap_socket(raw,server_hostname=self.host)
        except BaseException:
            raw.close(); raise


def resolve_public(host):
    ips = sorted({x[4][0] for x in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)})
    if not ips: raise ValueError('DNS vazio')
    for address in ips:
        if '%' in address: raise ValueError('Escopo IPv6 nao permitido')
        ip = ipaddress.ip_address(address)
        # Enderecos de traducao podem encapsular loopback/metadados IPv4 apesar de is_global.
        if ip.version == 6 and any(ip in ipaddress.ip_network(net) for net in ('64:ff9b::/96','64:ff9b:1::/48')):
            raise ValueError('Traducao IPv6 nao permitida')
        if not ip.is_global or ip.is_multicast or (ip.version == 6 and (ip.ipv4_mapped or ip.sixtofour or ip.teredo)):
            raise ValueError('IP de destino proibido')
    return ips[0]


def fetch(url, *, resolver=resolve_public, connection_factory=PinnedHTTPS):
    """Timeout por operacao 10s, nao prazo global: executar CLI sob supervisor."""
    current, chain = url, []
    for _ in range(4):
        if current not in SOURCES or current in chain: raise ValueError('Destino nao aprovado ou ciclo')
        chain.append(current)
        from .official_catalog import PRODUCT_PAGES, HTML_LIMIT
        limit=HTML_LIMIT if current in PRODUCT_PAGES else MAX_BYTES
        parsed = urlsplit(current)
        conn = connection_factory(parsed.hostname,resolver(parsed.hostname))
        try:
            conn.request('GET', parsed.path or '/',headers={'Host':parsed.hostname,'Accept-Encoding':'identity','Connection':'close','User-Agent':'GetnetChallengeResearch/0.2'})
            response = conn.getresponse()
            if response.status in (301,302,303,307,308):
                location = response.getheader('Location')
                if not location: raise ValueError('Redirect sem destino')
                current = urljoin(current,location); continue
            if response.status != 200: raise ValueError('HTTP '+str(response.status))
            if response.getheader('Content-Type','').split(';')[0].strip().lower() not in ('text/html','application/xhtml+xml'):
                raise ValueError('Tipo de conteudo nao permitido')
            if response.getheader('Content-Encoding','identity').lower() != 'identity': raise ValueError('Compressao nao permitida')
            declared = response.getheader('Content-Length')
            if declared and (not declared.isdecimal() or int(declared)>limit): raise ValueError('Tamanho excessivo/invalido')
            body = response.read(limit+1)
            if not body or len(body)>limit or (declared and len(body)!=int(declared)): raise ValueError('Corpo vazio/excessivo/truncado')
            return dict(requested_url=url, final_url=current, redirect_chain=chain,
                        captured_at=datetime.now(timezone.utc).isoformat(),raw_sha256=sha256(body).hexdigest(),body=body)
        finally: conn.close()
    raise ValueError('Limite de redirects')


def _worker(url, sender):
    try:
        sender.send(('ok', fetch(url)))
    except Exception as exc:
        sender.send(('error', type(exc).__name__ + ': ' + str(exc)))
    finally:
        sender.close()


def fetch_bounded(url, timeout=30):
    """Prazo global por processo dedicado; cancela somente o coletor filho criado aqui."""
    import multiprocessing
    if url not in SOURCES or not 0 < timeout <= 30: raise ValueError('URL ou prazo invalido')
    context = multiprocessing.get_context('spawn')
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(url,sender), daemon=True)
    process.start()
    sender.close()
    try:
        if not receiver.poll(timeout): raise TimeoutError('Prazo global da captura excedido')
        status, result = receiver.recv()
        if status != 'ok': raise ValueError(result)
        return result
    finally:
        receiver.close()
        process.join(timeout=1)
        if process.is_alive(): process.terminate();process.join(timeout=2)
