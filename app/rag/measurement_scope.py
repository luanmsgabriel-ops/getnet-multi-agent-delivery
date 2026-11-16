"""Conservative measurement complements, not a geographic classifier.

A recognized physical quantity immediately governs a compatible unit expression.
Only that complement is masked for geographic routing. This does not establish
Brazil, a product specification or factual support; unknown grammar/units abstain.
Pint's pinned standard registry supplies units/prefixes/plurals. No user definition,
calculation, file access or dynamic registry configuration is accepted.
"""
from functools import lru_cache
import re
from app.intents import normalize

# A small quantity ontology, not a list of exempt places or product answers.
# Dimensional compatibility here only disambiguates a measurement expression.
QUANTITIES = {
    'luminancia': 'candela/meter**2', 'luminance': 'candela/meter**2',
    'iluminancia': 'lux', 'illuminance': 'lux',
    'tensao': 'volt', 'voltagem': 'volt', 'voltage': 'volt',
    'corrente': 'ampere', 'current': 'ampere',
    'potencia': 'watt', 'power': 'watt',
    'energia': 'joule', 'energy': 'joule',
    'carga': 'coulomb', 'charge': 'coulomb',
    'frequencia': 'hertz', 'frequency': 'hertz',
    'resistencia': 'ohm', 'resistance': 'ohm',
    'pressao': 'pascal', 'pressure': 'pascal',
    'temperatura': 'kelvin', 'temperature': 'kelvin',
    'massa': 'kilogram', 'mass': 'kilogram',
    'comprimento': 'meter', 'length': 'meter',
    'largura': 'meter', 'width': 'meter',
    'altura': 'meter', 'height': 'meter',
    'espessura': 'meter', 'thickness': 'meter',
    'duracao': 'second', 'duration': 'second',
}
MODIFIERS = frozenset((
    'maxima maximo minima minimo media medio nominal tipica tipico '
    'eletrica eletrico total efetiva efetivo '
    'maximum minimum maximal minimal average nominal typical electric electrical total effective'
).split())
# Tokens are taken from the original string: SI symbol case is significant.
PREPOSITION = re.compile(r'\b(?:em|in)\s+', re.I)
WORDS = re.compile(r'[^\W\d_]+', re.UNICODE)
UNIT_ATOM = r'[A-Za-z\u00b5\u03bc\u00b0]{1,24}'
UNIT_EXPR = re.compile(
    rf'{UNIT_ATOM}(?:\s*(?:\*\*|\^)\s*-?[123])?'
    rf'(?:\s*[/\*\u00b7]\s*{UNIT_ATOM}(?:\s*(?:\*\*|\^)\s*-?[123])?){{0,3}}'
)
END = re.compile(r'\s*$|[?!,;:\n.]|\s+(?:e|ou|and|or|em|no|na|nos|nas|in|at|on|is|are|'
                 r'esta|estao|foi|eram|para|for|conforme|segundo|according)\b', re.I)

@lru_cache(maxsize=1)
def _registry():
    from pint import UnitRegistry
    # Disk cache and custom definitions are never enabled.
    return UnitRegistry(case_sensitive=True, cache_folder=None)

def _quantity_before(text, end):
    # Only a quantity and up to two closed-class technical modifiers immediately
    # precede the preposition. Never cross punctuation, a verb or another phrase.
    prefix = text[max(0, end-80):end].rstrip()
    words = list(WORDS.finditer(prefix))
    for distance in range(1, min(3, len(words))+1):
        head = words[-distance]
        name = normalize(head.group())
        if name not in QUANTITIES:
            continue
        tail = prefix[head.end():]
        tokens = WORDS.findall(tail)
        if (len(tokens) == distance-1
                and all(normalize(t) in MODIFIERS for t in tokens)
                and re.fullmatch(r'(?:\s+[^\W\d_]+)*', tail, re.UNICODE)):
            return QUANTITIES[name]
    return None

def measurement_complements(text):
    """Return validated original-string spans; bounded parse, no model/network."""
    if not isinstance(text, str) or len(text) > 4000:
        return ()
    found = []
    for prep in PREPOSITION.finditer(text):
        expected = _quantity_before(text, prep.start())
        if expected is None:
            continue
        # Limited unit syntax; never pass the whole user sentence to Pint.
        match = UNIT_EXPR.match(text, prep.end())
        if not match or match.end()-prep.end() > 64:
            continue
        if not END.match(text[match.end():]):
            continue
        expression = match.group().replace('\u00b7', '*')
        registry = _registry()
        from pint.errors import PintError
        try:
            dim = registry.parse_units(expression, case_sensitive=True).dimensionality
            if not dim or dim != registry.parse_units(expected).dimensionality:
                continue
        except (PintError, ValueError, TypeError, KeyError):
            continue
        found.append((prep.start(), match.end()))
    return tuple(found)

def mask_measurement_complements(text):
    """Mask just the measurement relation, leaving all other locations intact."""
    spans = measurement_complements(text)
    for start, end in reversed(spans):
        text = text[:start] + ' '*(end-start) + text[end:]
    return text
