"""Conservative routing of intact documentary requests, never evidence assessment.
No product-specific answer, tool authorization or inferred session fact lives here.
"""
import re
from app.intents import normalize, request_facts, receivable_query, terminal_status_query
from app.request_plan import informational_part

# Domains handled by dedicated public tools must not be absorbed by a Getnet mention.
OTHER_DOMAIN = re.compile(r'\b(?:clima|previsao|weather|forecast|chover|chuva|cotacao|ptax|exchange rate|python|dns|futebol|receita|horoscopo|programacao|programming)\b')
REFERENCE = re.compile(r'\b(?:dela|dele|delas|deles|disso|daquilo|anterior|ela|ele|its|that one)\b')

def dependent_plural_instruction(message):
    """Bounded anaphoric instructions, never a new subject inferred from nouns.

    Only complete nominal references are accepted; a named subject after the
    noun (e.g. "regras da compostagem") remains an independent request.
    """
    text=normalize(message).strip(' .!?;')
    nominal=(r'(?:explique|descreva) (?:(?:as|os|essas|esses) (?:duas|dois|tres)|ambas|ambos) '
             r'(?:orientacoes|instrucoes|regras|procedimentos|pontos)(?: documentad[oa]s)?'
             r'|(?:explain|describe) (?:both|the two|the three) '
             r'(?:instructions|rules|procedures|points)(?: documented)?')
    qualifier=r'(?:,\s*(?:sem|nao|without|do not|don.t)\s+[^?!;]+)?'
    return bool(re.fullmatch('(?:'+nominal+')'+qualifier,text))


def needs_documentary_reference(message):
    from app.brazil_scope import BUSINESS
    text=normalize(message)
    return bool((REFERENCE.search(text) or dependent_plural_instruction(message))
                and not BUSINESS.search(text) and not OTHER_DOMAIN.search(text))


def independent_public_question(message):
    """Strong standalone subject, rather than a new topic inferred from a noun.

    Bounded deterministic separation: incomplete follow-ups stay with their
    business anchor. This is not a general semantic parser.
    """
    from app.brazil_scope import BUSINESS
    text=normalize(message).strip(' .!?;')
    if BUSINESS.search(text) or REFERENCE.search(text):return False
    if OTHER_DOMAIN.search(text):return True
    if dependent_plural_instruction(message):return False
    # Whole dependent forms; an occurrence of "limite" alone cannot bind a new
    # subject (e.g. "limite da compostagem") to the previous Getnet product.
    if re.fullmatch(r'(?:explique|explain|describe) (?:o |the )?(?:limite|limit|alternativa|alternative|procedimento|procedure)(?: e (?:a |the )?(?:alternativa|alternative))?(?: documentad[oa]| documented)?',text):return False
    if re.fullmatch(r'(?:como (?:acompanho|funciona|procedo)|how (?:does it work|can i proceed)|e (?:quanto custa|na outra)|quero so orientacao.*)',text):return False
    return bool(re.match(r'^(?:o que (?:e|sao)|what (?:is|are)|como (?:funciona[m]?|fazer)|how (?:does|do|to)|como [ao]s? |explique |explain |fale sobre |tell me about )\s*\w',text))

def intact_documentary(message):
    from app.brazil_scope import BUSINESS
    text=normalize(message)
    if not BUSINESS.search(text) or OTHER_DOMAIN.search(text):return False
    if any(independent_public_question(part) for part in re.split(r'[?!;\n]',message) if part.strip()):return False
    # A later business mention does not retroactively bind an independent public
    # question. Inheritance is forward-only, after an explicit business anchor.
    first=re.split(r'[?!;\n]',text,maxsplit=1)[0]
    if not BUSINESS.search(first) and informational_part(first):return False
    facts=request_facts(message)
    if facts.unsupported_action or facts.account_migration or receivable_query(message).individual:return False
    if terminal_status_query(message):return False
    return informational_part(message)
