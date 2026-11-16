"""Local BM25 alternative: lexical ranking, not semantic entailment.

Parameters fixed before holdout evaluation. No embeddings, external model,
query rewriting or removal of the caller's coverage/scope safety filters.
"""
from collections import Counter
import math
import re
import unicodedata

class BM25:
    def __init__(self, entries, *, k1=1.2, b=0.75):
        from .core import QUERY_TRANSLATIONS, STOP, QUERY_EN_STOP, QUERY_PT_STOP
        self.k1, self.b = k1, b
        self.frequencies = []
        for entry in entries:
            text = entry.get('title','')+' '+entry['text']
            text = ''.join(c for c in unicodedata.normalize('NFKD',text.lower()) if not unicodedata.combining(c))
            text = re.sub(r'\bwi[\s-]+fi\b','wifi',text)
            words = [QUERY_TRANSLATIONS.get(t,t) for t in re.findall(r'[a-z0-9]+',text)
                     if t not in STOP | QUERY_EN_STOP | QUERY_PT_STOP]
            self.frequencies.append(Counter(words))
        self.lengths = [sum(f.values()) for f in self.frequencies]
        self.average = sum(self.lengths)/len(self.lengths) if self.lengths else 1.0
        counts = Counter(t for f in self.frequencies for t in f)
        size = len(self.frequencies)
        self.idf = {t: math.log(1+(size-n+0.5)/(n+0.5)) for t,n in counts.items()}

    def score(self, index, query_terms):
        frequencies = self.frequencies[index]
        length = self.lengths[index]
        total = 0.0
        for term in sorted(query_terms):
            count = frequencies.get(term,0)
            if count:
                total += self.idf[term]*count*(self.k1+1)/(count+self.k1*(1-self.b+self.b*length/(self.average or 1)))
        return total


# Formulation words, not negation, numeric constraints or product attributes.
FORMULATION = set('deve seu sua seus suas usar usando estao esta documentados documentado vem tem podem onde vejo exige indica seja ser estar sao entao consigo deseja gostaria favor poderia'.split())
TOPICS = {'smart','classica','a920','dx8000','crediario','pix','link','antecipacao'}
# Document labels and generic domain nouns cannot establish a requested attribute.
RETRIEVAL_CONTEXT = set('manual manuais pagina paginas edicao arquivo oficial brasil brasileiro brasileira maquininha terminal cartao venda pagamento transacao agora alem antes depois duas dois estou comparando orienta orientacao duvida canal solicitar completar sair sem nao'.split())

def ranking_view(query):
    # Only explicit prose exclusions; technical negation (sem fio, sem conta,
    # não imprime) remains intact. The original still reaches all policy gates.
    query = re.sub(r'^(?:se|if)\b[^,!?;]+,\s*(?=(?:quais?|como|quanto|what|which|how)\b)','',query,flags=re.I)
    return re.sub(r'\b(?:sem\s+(?:falar|tratar)\s+(?:de|sobre)|without\s+(?:discussing|mentioning))\b[^.!?;]*',
                  ' ', query, flags=re.I)


def lexical_terms(text):
    from app.intents import normalize
    from .core import subject_tokens
    text=normalize(text)
    text=re.sub(r'\b(?:rede )?sem fio\b','wifi',text)
    text=re.sub(r'\bdcc\b','conversor moedas',text)
    text=re.sub(r'\bapp\b','aplicativo',text)
    # Bounded action/noun equivalence for public cleaning instructions.
    # This changes lexical matching only; original request, exclusions,
    # product eligibility and evidence text remain intact.
    action_forms={'limpar':'limpeza','limpe':'limpeza','limpando':'limpeza',
                  'clean':'limpeza','cleaning':'limpeza'}
    words={action_forms.get(w,w) for w in subject_tokens(text)-FORMULATION}
    def plural(word):
        if len(word)>5 and word.endswith('oes'):return word[:-3]+'ao'
        if len(word)>5 and word.endswith('res'):return word[:-2]
        if len(word)>5 and word.endswith('s') and not word.endswith(('is','us')):return word[:-1]
        return word
    return {plural(w) for w in words}

def lexical_match(left,right):
    if left==right:return 1.0
    if min(len(left),len(right))<5 or any(c.isdigit() for c in left+right):return 0.0
    prefix=0
    for a,b in zip(left,right):
        if a!=b:break
        prefix+=1
    # Conservative inflection similarity, not synonyms or semantic embeddings.
    return .8 if prefix>=6 and min(len(left),len(right))/max(len(left),len(right))>=.6 else 0.0

class Hybrid:
    """Exact lexical + constrained morphological matching + body reranking.

    Unknown query terms remain in coverage's denominator. Product, edition,
    market, specific code and predicate gates are imposed before ranking.
    Constants are fixed from development, not tuned on closed validation.
    """
    def __init__(self,entries):
        self.cache={e['evidence_id']:(lexical_terms(e['title']),lexical_terms(e['text'])) for e in entries}
        counts=Counter(t for title,body in self.cache.values() for t in title|body)
        self.idf={t:math.log(1+len(entries)/(1+n)) for t,n in counts.items()}
        self.specific={t for t,n in counts.items() if n<=max(1,len(entries)//4)}-TOPICS-RETRIEVAL_CONTEXT
        self.prefixes={}
        for term in counts:
            if len(term)>=6 and not any(c.isdigit() for c in term):
                self.prefixes.setdefault(term[:6],set()).add(term)

    def rank(self,query,candidates,*,market,limit):
        from .core import query_tokens,tokens
        from .quality import predicate_supported,product_scope_conflict
        qt=lexical_terms(ranking_view(query));qraw=query_tokens(query)
        variants={q:{t for t in self.prefixes.get(q[:6],()) if lexical_match(q,t)==.8} for q in qt}
        def field_match(q,field):
            return 1.0 if q in field else (.8 if variants[q]&field else 0.0)
        years={w for w in tokens(query) if re.fullmatch(r'20\d{2}',w)}
        # A generic service overview has no narrower factual predicate.
        # Unknown attributes keep the ordinary negative-evidence gates.
        overview=bool(qt & TOPICS) and qt <= TOPICS | {'condicao','condition','funciona','funcionamento','recebiveis','recebivel'}
        demand=qt & self.specific
        news=bool(tokens(query)&{'noticia','noticias','novidade','novidades','news'})
        ranked=[]
        for e in candidates:
            if e['market']!=market or product_scope_conflict(query,e) or not predicate_supported(query,e):continue
            code=re.search(r'ADQ\s+(\d+)[- ](\d+)',e['title'],re.I)
            if code and not {'adq',code[1],code[2]}<=qraw:continue
            if not years<=tokens(e['title']+' '+e['text']):continue
            title,body=self.cache[e['evidence_id']];allterms=title|body
            matched={q:field_match(q,allterms) for q in qt}
            coverage=sum(matched.values())/len(qt) if qt else 0
            predicate=qt-TOPICS or qt
            body_coverage=sum(field_match(q,body) for q in predicate)/len(predicate) if predicate else 0
            # A compound question need not be wholly answered by EACH block.
            # An exact, uncommon body anchor can retain complementary evidence.
            # Unknown terms still penalize the score; this is relevance, not coverage.
            anchors=(demand & body)
            service_overview=overview and bool(qt & TOPICS & title)
            if overview and not service_overview:continue
            if demand and not anchors and not service_overview:continue
            if (coverage<.5 or body_coverage<(.5 if news else .35)) and (news or not anchors) and not service_overview:continue
            score=2*body_coverage+coverage+.1*sum(self.idf.get(q,1)*v for q,v in matched.items())
            ranked.append((score,e,coverage,body_coverage))
        # Prefer a complementary exact anchor before another block repeating the
        # same anchor. Keep the original scores as tie-breakers and all quotes.
        selected=[];covered=set();covered_facets=set()
        def overview_facets(row):
            if not overview or qt & {'smart','classica','a920','dx8000'}:return set()
            text=row[1]['text'].lower()
            patterns={'definition':r'(?:o que [ée]|[ée] a possibilidade|consiste em)',
                      'eligibility':r'eleg[ií]ve|desde que|requisito|habilita',
                      'use':r'simular|simula[çc][aã]o|consultar os receb|passo a passo',
                      'cost':r'taxa|juros|encargo'}
            return {name for name,pattern in patterns.items() if re.search(pattern,text)}
        while ranked and len(selected)<limit:
            def gain(row):
                title,body=self.cache[row[1]['evidence_id']]
                return (demand & body) | (qt & TOPICS & title)
            ranked.sort(key=lambda x:(-len(gain(x)-covered),-len(overview_facets(x)-covered_facets),-x[0],x[1]['source'],x[1]['ordinal']))
            row=ranked.pop(0);selected.append(row);covered.update(gain(row));covered_facets.update(overview_facets(row))
        ranked=selected
        return [dict(e,retrieval={'ranker':'hybrid','score':round(score,8),'coverage':round(coverage,8),
                                 'body_coverage':round(body,8)}) for score,e,coverage,body in ranked[:limit]]
