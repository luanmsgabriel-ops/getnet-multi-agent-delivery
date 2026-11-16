"""Ephemeral documentary routing view, never retrieval text or authority.
Lowercase unknown place names without geographical cues remain a known risk.
Never persist this view as a country, identity or operational fact.
"""
import re
from app.intents import normalize
_PREP = re.compile(r'^(?:em|no|na|nos|nas|in|at)\s+', re.I)
_LOC = re.compile(r'\b(?:em|no|na|nos|nas|in|at)\s+', re.I)
_GEO = re.compile(r'\b(?:pais|paises|cidade|cidades|regiao|regioes|territorio|territorios|localizacao|localizacoes|municipio|municipios|country|countries|city|cities|region|regions|territory|territories|location|locations|town|towns)\b')
_SUBJECT = r'(?:loja|estabelecimento|operacao|comercio|empresa|store|shop|establishment|operation|business|terminal|maquininha)'
_VERB = r'(?:fica|ficam|esta|estao|opera|operam|situa-se|localiza-se|is|are|operates?|located|based)'
_BEFORE = re.compile(r'\b'+_SUBJECT+r'\b[^.;!?\n]{0,100}\b'+_VERB+r'\s+(?:(?:localizad[oa]s?|situad[oa]s?|sediad[oa]s?|located|based|atualmente|agora|currently|now)\s+)*$')
_AFTER = re.compile(r'^\s*,?\s*'+_VERB+r'\s+(?:(?:a|o|minha|meu|nossa|nosso|the|my|our)\s+)*'+_SUBJECT+r'\b')
_UNFINISHED = frozenset('em no na nos nas in at de do da dos das of from para for qualquer qual quais meu minha seu sua um uma o a os as the any which every'.split())

def documentary_policy_view(question: str, non_geographic: tuple[str, ...] = ()) -> str:
    """Validate exact quotes atomically, then mask only the routing view.

    Invalid plans raise ValueError. Consumers must retain the original question
    for explicit guards, retrieval, grounding and memory. This creates no BR fact.
    """
    if not isinstance(question,str) or not question.strip():raise ValueError('Invalid documentary question')
    if type(non_geographic) is not tuple or len(non_geographic)>4:raise ValueError('Invalid documentary scope plan')
    if not non_geographic:return question
    from app.brazil_scope import COUNTRIES
    ranges=[]
    for quote in non_geographic:
        if type(quote) is not str or not 1<=len(quote)<=100 or quote!=quote.strip():raise ValueError('Invalid documentary scope quote')
        lead=_PREP.match(quote)
        if not lead or len(list(_LOC.finditer(quote)))!=1:raise ValueError('Quote must contain one locative complement')
        positions=[m.start() for m in re.finditer(re.escape(quote),question)]
        if len(positions)!=1:raise ValueError('Quote must occur exactly once')
        start=positions[0];end=start+len(quote)
        if (start and (question[start-1].isalnum() or question[start-1]=='_')) or (end<len(question) and (question[end].isalnum() or question[end]=='_')):raise ValueError('Quote must preserve token boundaries')
        # A proposal must end at a clause boundary, never before a residual noun.
        # This intentionally rejects safe mid-clause complements too.
        tail=question[end:].lstrip()
        if tail and tail[0] not in '.;!?,:\n\r':raise ValueError('Scope quote leaves a residual complement')
        words=re.findall(r'[^\W\d_]+',quote[lead.end():],re.UNICODE);plain=normalize(quote)
        if not words or normalize(words[-1]) in _UNFINISHED or re.search(r'[.;!?\n\r:]',quote):raise ValueError('Incomplete or compound scope quote')
        if COUNTRIES.search(plain) or _GEO.search(plain):raise ValueError('Geographical evidence cannot be masked')
        if any(w[0].isupper() for w in words):raise ValueError('Proper-name candidate cannot be masked')
        before=normalize(question[max(0,start-180):start]);after=normalize(question[end:end+140])
        if _BEFORE.search(before) or _AFTER.search(after):raise ValueError('Operational location declaration cannot be masked')
        if any(start<b and a<end for a,b in ranges):raise ValueError('Scope quotes must not overlap')
        ranges.append((start,end))
    result=question
    for start,end in sorted(ranges,reverse=True):result=result[:start]+' '*(end-start)+result[end:]
    return result

def documentary_market(question: str, non_geographic: tuple[str, ...] = ()):
    """Existing explicit country/global restrictions always win."""
    from app.brazil_scope import market_of
    view = documentary_policy_view(question,non_geographic)
    original = market_of(question)
    if original.countries or original.value == 'OUT':
        return original
    return market_of(view)
