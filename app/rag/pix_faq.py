"""Extração fechada das duas seções Pix da FAQ oficial brasileira."""
from html.parser import HTMLParser
import unicodedata

URL = 'https://site.getnet.com.br/duvidas/'
SECTIONS = ('Mais respostas sobre o Pix', 'Pix')
VOID = set('area base br col embed hr img input link meta param source track wbr'.split())
SKIP = set('script style nav footer header form noscript template svg head'.split())

def clean(value):
    return ' '.join(''.join(c for c in value if unicodedata.category(c) != 'Cf').split())

class Node:
    def __init__(self, tag='', attrs=()):
        self.tag, self.attrs, self.children, self.closed = tag, dict(attrs), [], False
    def has(self, name):
        return name in self.attrs.get('class', '').split()
    def text(self):
        if self.tag in SKIP:
            return ''
        return ''.join(c if isinstance(c,str) else c.text() for c in self.children)
    def find(self, predicate):
        if self.tag in SKIP:
            return []
        result = [self] if predicate(self) else []
        for child in self.children:
            if isinstance(child, Node):
                result.extend(child.find(predicate))
        return result

class Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node(); self.stack = [self.root]
    def handle_starttag(self, tag, attrs):
        node = Node(tag,attrs); self.stack[-1].children.append(node)
        if tag in VOID:
            node.closed = True
            if tag == 'br': node.children.append('\n')
        else:
            self.stack.append(node)
    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag,attrs)
        if tag not in VOID: self.handle_endtag(tag)
    def handle_endtag(self,tag):
        for index in range(len(self.stack)-1,0,-1):
            if self.stack[index].tag == tag:
                node = self.stack[index]
                # Desbalanceamento não é reparado silenciosamente na seção selecionada.
                node.closed = index == len(self.stack)-1
                if tag in {'p','li','div','h2'}: node.children.append('\n')
                del self.stack[index:]
                break
    def handle_data(self,text):
        self.stack[-1].children.append(text)

def one(nodes, description):
    if len(nodes) != 1:
        raise ValueError('FAQ Pix ausente ou ambígua: ' + description)
    return nodes[0]

def extract_pix_faq(raw):
    if not isinstance(raw,bytes) or not raw or len(raw)>1_000_000:
        raise ValueError('Snapshot vazio ou excessivo')
    tree = Tree(); tree.feed(raw.decode('utf-8',errors='strict')); tree.close()
    sections = tree.root.find(lambda n:n.has('c-all-faq__content'))
    chunks=[]; seen_ids=set()
    for name in SECTIONS:
        matches=[]
        for section in sections:
            headings=section.find(lambda n:n.tag=='h2' and n.has('c-all-faq__title'))
            if any(clean(h.text())==name for h in headings): matches.append(section)
        section=one(matches,name)
        one(section.find(lambda n:n.tag=='h2' and n.has('c-all-faq__title')), 'título da seção')
        if any(not n.closed for n in section.find(lambda n:True)):
            raise ValueError('FAQ Pix incompleta: estrutura HTML não fechada')
        questions=section.find(lambda n:n.tag=='a' and n.has('c-all-faq__question'))
        modals=section.find(lambda n:n.has('o-modal__content--faq'))
        if not questions or len(questions)!=len(modals):
            raise ValueError('FAQ Pix incompleta: associação pergunta/resposta')
        for question in questions:
            ident=question.attrs.get('data-modal')
            if not ident or ident in seen_ids:
                raise ValueError('FAQ Pix ambígua: identificador duplicado ou ausente')
            seen_ids.add(ident)
            modal=one([n for n in modals if n.attrs.get('data-modal')==ident], 'resposta')
            title=clean(one(modal.find(lambda n:n.has('o-modal__title')), 'pergunta').text())
            answer=clean(one(modal.find(lambda n:n.has('o-modal__text-content')), 'corpo').text())
            if not title or title!=clean(question.text()) or not answer:
                raise ValueError('FAQ Pix incompleta: pergunta ou resposta divergente/vazia')
            chunk=name+'\n'+title+'\n'+answer
            # Nunca separar as condições da resposta que elas qualificam.
            if len(chunk)>1200:
                raise ValueError('FAQ Pix extensa: revisar particionamento editorial')
            chunks.append(chunk)
    return 'Pix: perguntas frequentes Getnet Brasil',chunks
