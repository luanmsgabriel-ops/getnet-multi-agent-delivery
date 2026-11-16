"""Bounded whole-excerpt composition; lexical coverage is not entailment."""
from .ranking import lexical_terms, lexical_match, TOPICS
from .core import evidence_text
from app.request_plan import grounded_attribute_limit, split_questions, informational_part
from app.intents import normalize
import re

def body_matches(question, candidate):
    terms=lexical_terms(question)-TOPICS
    body=lexical_terms(candidate['text'])
    return {q for q in terms if max((lexical_match(q,d) for d in body),default=0)>=.8}

def select_evidence(question,candidates):
    """At most two complete blocks, and only when the second adds evidence.

    Preserve all conditions/titles; never splice text or deduce a negative from
    non-mention. Hard cap reserves space for notices/sources in the response.
    """
    selected=[candidates[0]]
    covered=body_matches(question,candidates[0])
    gaps=grounded_attribute_limit(question,selected)
    for c in candidates[1:]:
        if c['text']==selected[0]['text']:continue
        combined=selected+[c]
        size=sum(len(evidence_text(e))+len(e['source'])+len(e['captured_at'])+30 for e in combined)
        if size>3000:continue
        adds=body_matches(question,c)-covered
        reduces=len(grounded_attribute_limit(question,combined))<len(gaps)
        if adds or reduces:
            selected.append(c);break
    return selected

def public_complement(question,candidates):
    """Keep known public parts when a requested commercial value is absent.

    This does not approve a price. Pure value questions still abstain.
    Documentary fee explanations can be shown only as partial evidence.
    """
    from .quality import commercial_attribute
    parts=split_questions(question)
    for part in parts:
        if commercial_attribute(part.text) is None and informational_part(part.text):
            if any(body_matches(part.text,c) for c in candidates):return True
    # Independently asked non-commercial attributes need no numerical price.
    attrs=set(__import__('app.request_plan',fromlist=['requested_attributes']).requested_attributes(question))
    if attrs & {'printing','installments','settlement','portability','eligibility'}:
        return any(body_matches(question,c)-{'taxa','tarifa','preco','custo','valor','juros'} for c in candidates)
    # "How is the fee calculated?" is a documentary concept, not a quote.
    q=normalize(question)
    concept=bool(re.search(r'\b(?:como|how|por que|why|o que|what is|explique|explain)\b',q))
    commercial_body=any(re.search(r'\b(?:taxa|tarifa|preco|custo|fee|price|cost|juros)\b',normalize(c['text'])) for c in candidates)
    return concept and commercial_body
