"""Redação de divulgações explícitas antes de memória, modelo e ledger.

Gramática limitada PT/EN/ES: rótulo, qualificadores e valor divulgado. Não é um
classificador universal de segredos. Spans preservam as orações de atendimento,
os nomes de rede e relatos de estado/uso que não contêm um valor divulgado.
"""
import re
import unicodedata

_LABEL = (r'(?:senha|password|passphrase|passcode|credencial|credential|'
          r'clave|contrase[nñ]a|token|otp|cvv|cvc|pin|'
          r'(?:verification|authentication|security|access|sms)\s+code|'
          r'c[oó]digo(?=[^:;.!?\n]{0,65}\b(?:sms|verifica[cç][aã]o|'
          r'autentica[cç][aã]o|seguran[cç]a|acesso|verificaci[oó]n|'
          r'autenticaci[oó]n|seguridad|acceso)\b))')
# Only grammatical credential qualifiers belong to the head. Arbitrary words
# (e.g. the SSID "Senha Livre") must never be swallowed while looking for "=".
_QUALIFIER = (
    r'(?:do|da|de|del|para\s+(?:o|a|el|la))\s+(?:wi-?fi|rede|red|'
    r'acesso|acceso|login|lojista|usu[aá]rio|administrador|verifica[cç][aã]o|autentica[cç][aã]o|seguran[cç]a|'
    r'verificaci[oó]n|autenticaci[oó]n|seguridad|sms)|'
    r'(?:of|for)\s+(?:the\s+)?(?:wi-?fi|network|access|authentication|'
    r'login|sign-in|logging\s+in)|'
    r'para\s+(?:entrar|acessar|acceder|ingresar|autenticar|'
    r'iniciar\s+ses(?:s[aã]o|i[oó]n))|'
    r'(?:recebid[oa]|enviad[oa])\s+(?:por|via)\s+sms|'
    r'(?:received|sent)\s+(?:by|via)\s+sms|'
    r'(?:por|via)\s+sms|'
    r'corret[oa]|correct[oa]|atual|actual|nov[oa]|nuev[oa]|correct|current|new')
_HEAD = re.compile(r'\b' + _LABEL + r'\b(?:\s+(?:' + _QUALIFIER + r'))*', re.I)
_CONNECTOR = re.compile(
    r'\s*(?::|=|\b(?:é|e|is|es|reads|igual\s+a|equals)\b)'
    r'(?:\s+(?:(?:a|o|el|la)\s+(?:seguinte|siguiente)|'
    r'the\s+following|as\s+follows))?\s*:?\s*', re.I)
_STATE = re.compile(
    r'^(?:(?:esta|estava|foi|sera|sao|are|son|was|has\s+been)\s+)?'
    r'(?:(?:nao|not)\s+)?(?:digitad[ao]|inserid[ao]|necessari[ao]s?|'
    r'obrigatori[ao]s?|corret[ao]|incorret[ao]|errad[ao]|solicitad[ao]|aceit[ao]|'
    r'correct[oa]|incorrect[oa]|introducid[oa]|ingresad[oa]|requerid[oa]|rechazad[oa]|'
    r'accepted|rejected|wrong|incorrect|correct|required|entered|typed|needed)\b|'
    r'^(?:de\s+)?(?:\d+|seis|oito|six|eight)\s+'
    r'(?:digitos|caracteres|digits|characters)\b', re.I)
_USAGE = re.compile(
    r'^(?:(?:esta|estava|foi|sera|was|has\s+been)\s+)?'
    r'(?:(?:nao|not)\s+)?(?:funciona|funcionou|confere|faltando|'
    r'works|working|missing|existe)\b|'
    r'^(?:no|na|nos|nas|em|en|pelo|pela|on|in|at|into|by)\s+'
    r'(?:(?:o|a|el|la|um|uma|meu|minha|mi|su|seu|sua|proprio|propria|propio|the|my|your|own)\s+)*'
    r'(?:aparelho|dispositivo|maquininha|terminal|chat|tela|teclado|app|'
    r'aplicativo|rede|menu|equipo|pantalla|device|machine|screen|keyboard|application|network)\b|'
    r'^(?:devo|deve|precisa|pode|should|must|can)\b', re.I)
# Without an assignment, these are purpose/location descriptions, not values.
_PURPOSE = re.compile(r'^(?:para|to|for|aqui|ali|here|there)\b', re.I)
# A named/determined subject can have a location and an adverb before its
# predicate. This recognizes a new clause without enumerating terminal models.
_NOMINAL_CLAUSE = (
    r'(?:(?:a|o|as|os|el|la|the|this|that)\s+[\w-]+(?:\s+[\w-]+){0,2}|'
    r'(?=[\w-]*\d)[\w-]+)'
    r'(?:\s+(?:at|in|on|near|from|no|na|en)\s+'
    r'(?:(?:a|o|el|la|the)\s+)?[\w-]+){0,2}\s+'
    r'(?:(?:still|already|now|also|currently)\s+)?'
    r'(?:is|are|was|were|has|have|does|do|can|cannot|will|'
    r'[a-z]{2,}(?:s|ed))\b')
_CLAUSE = (_NOMINAL_CLAUSE + r'|'
    r'(?:minh[ao]s?|meus?|mi|mis|nuestro|nuestra|my|our|your|seu[s]?|sua[s]?|eu|ele|ela|it|we|i|'
    r'agora|ainda|mas|porém|então|now|still|but|however|then|'
    r'como|how|qual|what|onde|where)\b|'
    r'(?:(?:a|o|as|os|the|esta|esse)\s+)?(?:maquininha|aparelho|terminal|'
    r'rede|device|network|machine)\b|'
    r'(?:a|o|the)\s+(?:minh[ao]|meu|my|our|your)\b|'
    r'(?:(?:a|o|as|os|el|la|the|this|that)\s+)?[\w-]+(?:\s+[\w-]+){0,2}\s+'
    r'(?:n[aã]o|no|not|is|est[aá]|does|won)\b|'
    r'(?:n[aã]o|cannot|can\x27t|doesn\x27t)\s+\w+\b|'
    r'(?:preciso|quero|posso|need|want)\s+\w+\b')
_BOUNDARY = re.compile(
    r'[;\n]|[.!?](?=\s|$)|\s+(?=(?:que|which|that)\s+(?:est[aá]|fica|opera|is|are|operates)\b)|,\s+(?=(?:(?:and|e|y|but|mas)\s+)?(?:'
    + _CLAUSE + r'|' + _LABEL + r'\b))|'
    r'\s+(?:e|y|and|mas|but)\s+(?=(?:' + _CLAUSE + r'|' + _LABEL + r'\b))|'
    r'(?:\s+|[.!?]\s*)[—–]\s*(?=(?:' + _CLAUSE + r'|' + _LABEL + r'\b))', re.I)
# A naming complement is a name, including an unquoted multiword SSID.
_NAME_PREFIX = re.compile(
    r'\b(?:rede|red|network|ssid|wi-?fi)\b[^;.!?\n]{0,45}\b'
    r'(?:chama-se|se\s+chama|se\s+llama|chamada|chamado|llamada|llamado|nome|named|called|name\s+is)'
    r'\s*(?:é|e|is|:|=)?\s*["\x27“‘]?[^;.!?\n]*$', re.I)
_NON_DISCLOSURE_PREFIX = re.compile(
    r'\b(?:sem|sin|without|no)\s+(?:(?:uma?|a|any)\s+)?$', re.I)
_REDACTION = '[credencial removida]'


def _plain(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.casefold())
                   if not unicodedata.combining(c))


def _generic_description(tail):
    """A recognized prefix cannot hide an unparsed value in the same clause."""
    boundary = _BOUNDARY.search(tail)
    clause = tail[:boundary.start()] if boundary else tail
    plain = _plain(clause).strip()
    if re.search(r'[:=]|\b(?:valor|value)\s+(?:e|is|equals)\b|'
                 r'\b(?=\w*[a-z])(?=\w*\d)\w+\b', plain):
        return False
    match = _STATE.match(plain) or _USAGE.match(plain)
    if match:
        rest = plain[match.end():].strip()
        if re.fullmatch(r'(?:devo|deve|precisa|pode|should|must|can)', match.group()):
            rest = re.sub(r'^(?:ser|be)\s+', '', rest)
            rest = re.sub(r'^(?:ter|have)\s+', '', rest)
            match = _STATE.match(rest)
            if not match:
                return False
            rest = rest[match.end():].strip()
        if not rest:
            return True
        if re.fullmatch(r'corretamente',rest):
            return True
        if re.fullmatch(r'(?:sem|without|sin)\s+(?:erros?|errors?|errores?)(?:\s+antes de tentar novamente)?',rest):
            return True
        # A bounded UI-location modifier remains a procedure description,
        # not a credential value (e.g. "na tela indicada e confirme").
        if (re.search(r'\b(?:tela|teclado|pantalla|screen|keyboard)\b', match.group())
                and re.fullmatch(r'(?:indicad[ao]|exibid[ao]|principal|inicial)(?:\s+e\s+confirme)?', rest)):
            return True
        if re.search(r'\b(?:digitos|caracteres|digits|characters)\b',match.group()):
            if re.fullmatch(r'(?:ou|or)\s+(?:\d{1,3}|um|uma|dois|duas|tres|quatro|cinco|seis|sete|oito|nove|dez|one|two|three|four|five|six|seven|eight|nine|ten)(?:\s+(?:digitos|caracteres|digits|characters))?',rest):
                return True
        return bool(_PURPOSE.match(rest) or (_USAGE.match(rest) and _generic_description(rest)))
    return bool(_PURPOSE.match(plain))


def _value_start(text, head):
    """Return the start of an explicit or delimiter-free value, if present."""
    connector = _CONNECTOR.match(text, head.end())
    start = connector.end() if connector else head.end()
    # Qualifiers may end immediately before punctuation. Inspect an explicit
    # value continuation before the whitespace/bare-value early return.
    tail = text[start:]
    continued = re.match(r'^[,;.!?]\s*(?:(?:o|the)\s+)?(?:valor|value)\s*'
                         r'(?::|=|\b(?:é|e|is|equals)\b)\s*',tail,re.I)
    if continued:
        return start + continued.end()
    if not connector:
        # Whitespace separates a bare value from its label/qualifiers.
        if start == len(text) or not text[start].isspace():
            return None
        start += len(text[start:]) - len(text[start:].lstrip())
        tail = text[start:]
    if connector and connector.group().strip().casefold() == 'e':
        if re.match(_CLAUSE, tail, re.I):
            return None
        # In an entry instruction, "e confirme para ..." starts a new
        # procedural clause, not the value of an accentless copula "é".
        # The existing purpose grammar still rejects assignments and mixed
        # alphanumeric values; subsequent credential heads are scanned too.
        instruction = re.search(r'\b(?:digite|insira|digitar|inserir)\s+(?:(?:a|o|sua|seu)\s+)?$', text[:head.start()], re.I)
        if instruction:
            boundary = _BOUNDARY.search(tail)
            clause = (tail[:boundary.start()] if boundary else tail).strip()
            # Consume a complete UI choice after entry, never an assignment
            # or an arbitrary credential value/trailing suffix.
            label = r'["“][A-Za-zÀ-ÖØ-öø-ÿ -]{1,40}["”]'
            choice = r'(?:escolha|escolher|selecione|selecionar)\s+(?:a\s+(?:via|opção)\s+)?'
            confirmation_order = r'(?:\s+(?:(?:antes|depois)\s+de\s+confirmar|e\s+confirme))?'
            if re.fullmatch(choice+label+r'(?:\s+ou\s+'+label+r')?'+confirmation_order+r'\)?',clause,re.I):
                return None
        confirmation = re.match(r'confirme\b', tail, re.I)
        if instruction and confirmation:
            rest = tail[confirmation.end():]
            boundary = _BOUNDARY.search(rest)
            clause = rest[:boundary.start()] if boundary else rest
            if not clause.strip() or _generic_description(clause):
                return None
    if tail.startswith(_REDACTION):
        rest = tail[len(_REDACTION):]
        if not rest.strip() or _BOUNDARY.match(rest):
            return None
    if not tail or tail[0] in '.;,!?':
        return None
    # A quoted value is disclosure even if its words look like a state.
    if tail[0] not in ('"', "'", '“', '‘', '«'):
        plain = _plain(tail)
        # ':' and '=' are explicit disclosure, even when the value starts
        # with a word such as 'required'. Copular state descriptions must
        # consume the clause rather than waive an arbitrary suffix.
        if connector and re.search(r'[:=]',connector.group()):
            return start
        if (_STATE.match(plain) or _USAGE.match(plain)
                or (not connector and _PURPOSE.match(plain))) and _generic_description(tail):
            return None
    return start


def clean_message(text):
    spans = []
    # The placeholder contains the Portuguese label 'credencial'; its own text
    # is not another disclosure, while a value appended after it still is.
    markers = list(re.finditer(re.escape(_REDACTION), text))
    boundaries = list(_BOUNDARY.finditer(text))
    for head in _HEAD.finditer(text):
        if any(marker.start() <= head.start() < marker.end() for marker in markers):
            continue
        if spans and head.start() < spans[-1][1]:
            continue
        # Limit the naming context to the current clause. A later disclosure
        # after ";", a full stop or "e minha senha" is assessed independently.
        prefix = text[:head.start()]
        preceding = [boundary for boundary in boundaries if boundary.end() <= head.start()]
        if preceding:
            prefix = prefix[preceding[-1].end():]
        if _NAME_PREFIX.search(prefix) or _NON_DISCLOSURE_PREFIX.search(prefix):
            continue
        start = _value_start(text, head)
        if start is None:
            continue
        tail = text[start:]
        if tail[0] in ('"', "'", '“', '‘', '«'):
            close = {'“': '”', '‘': '’', '«': '»'}.get(tail[0], tail[0])
            end = text.find(close, start + 1)
            end = len(text) if end < 0 else end + 1
        else:
            boundary = _BOUNDARY.search(tail)
            end = start + boundary.start() if boundary else len(text)
            while end > start and text[end - 1].isspace():
                end -= 1
        if end > start:
            # Keep the label: downstream search guards still need to know that
            # this message contained authentication data, after value removal.
            spans.append((start, end))
    safe = text
    for start, end in reversed(spans):
        safe = safe[:start] + _REDACTION + safe[end:]
    return safe, bool(spans)
