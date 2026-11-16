"""Limited quantitative sufficiency checks, separate from citation identity."""
import re
from app.intents import normalize

PERCENT=re.compile(r'\b(?:percentual|percentuais|porcentagem|percentagem|porcentagens|percentage|percent)\b')
RELATIONS={'cashback','taxa','tarifa','juros','desconto','margem','mdr'}

def numeric_limits(question,candidates):
    """Do not turn a mention of a percentage into an actual quoted number.

    A number must occur in the same sentence as its requested relation.
    This is a narrow measurable guard, not universal semantic entailment.
    """
    q=normalize(question)
    if not PERCENT.search(q):return ()
    from .ranking import lexical_terms
    relation=lexical_terms(q)&RELATIONS
    for c in candidates:
        for sentence in re.split(r'[.!?;\n](?!\d)',normalize(c['text'])):
            if not re.search(r'\d+(?:[.,]\d+)?\s*(?:%|por cento\b|percent\b)',sentence):continue
            if relation and not relation<=lexical_terms(sentence):continue
            if relation:
                number=r'\d+(?:[.,]\d+)?\s*(?:%|por cento\b|percent\b)'
                # Only a short grammatical link, not an intervening other attribute.
                link=r'\s*(?:(?:de|do|da|e|eh|is|of|a|o|the|em|at|ate|up to|sera|seria)\s+){0,4}'
                reverse=r'\s*(?:(?:de|do|da|of|for|a|o|the)\s+){0,3}'
                if not all(re.search(r'\b'+re.escape(term)+r's?\s*:?'+link+number+'|'+number+reverse+r'\b'+re.escape(term)+r's?\b',sentence) for term in relation):
                    continue
            return ()
    return ('Não encontrei um percentual numérico sustentado para '+('/'.join(sorted(relation)) if relation else 'o atributo solicitado')+
            '; a menção genérica ao benefício ou à porcentagem não confirma seu valor.',)
