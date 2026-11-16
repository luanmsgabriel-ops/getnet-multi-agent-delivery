"""Escopo documental: institucional global separado de produto/conta brasileiros."""
import re
from app.intents import normalize
from app.rag.core import query_tokens

COMMERCIAL = set('pix crediario taxa taxas fee fees price prices preco precos parcelas '
                 'installments conta account saldo balance recebiveis receivables venda vendas '
                 'sales suporte support maquininha maquina terminal smart classica wifi link '
                 'antecipacao advance contrato contratar pacote package produto produtos '
                 'product products condicoes conditions'.split())
FOREIGN = set('europa europe europeu european argentina argentine mexico mexicana chile '
              'colombia peru uruguai uruguay japao japan australia eua usa portugal '
              'espanha spain germany alemanha canada canadian canadense canadenses '
              'global internacional international worldwide'.split())
LOCATION = set('onde where atua atuar atuacao opera operar operacao operate operates operating '
               'presenca presence pais paises countries country mercados markets'.split())
QUESTION_WORDS = LOCATION | set('getnets s empresa company mundo world global internacional '
                                'international worldwide esta presente present quais faz fazer do '
                                'which seu sua da do no na em tem a o e what is does'.split())
REGIONS = {'europa':'europe','latina':'latin','brasil':'brazil','japao':'japan','espanha':'spain',
           'alemanha':'germany','uruguai':'uruguay'}

# Complemento locativo não reconhecido não autoriza assumir o mercado BR.
# Contextos operacionais conhecidos ("no app", "na maquininha") não são países.
LOCAL_CONTEXTS = set('brasil brazil br app aplicativo aplicacao application portal '
                     'maquininha maquina terminal machine getnet credito credit debito debit '
                     'pix crediario cartao cartoes card cards tela screen menu conta account '
                     'venda vendas sale sales internet wifi rede network whatsapp servico '
                     'servicos service services plano plan pacote package contrato contract '
                     'estabelecimento loja store site website computador computer celular phone '
                     'android ios campo field opcao option botao button classica smart tef saldo reais brl eur checkout balcao caixa maquininhas maquinas terminais aparelhos devices devices brasil brazil rede redes counter chat conversa conversation dialogo dispositivo aparelho'.split())
LOCATIVE = re.compile(r'\b(?:no|na|nos|nas|em|in|at)\s+'
                      r'(?:(?:o|a|os|as|um|uma|the|my|meu|minha|seu|sua)\s+)?([a-z0-9]+)\b')
# Modificadores só pertencem ao contexto local quando seguidos de aparelho.
# Não libera 'própria cidade', nem consome 'em Lisboa' depois do aparelho.
DEVICE_LOCATIVE = re.compile(
    r'\b(?:no|na|nos|nas|em|in|at|on|into)\s+'
    r'(?:(?:o|a|os|as|the|my|your|meu|minha|seu|sua|proprio|propria|own)\s+)*'
    r'(?:maquininhas?|maquinas?|terminais|terminal|aparelhos?|dispositivos?|devices?|machines?)\b')

INSTALLMENT_QUESTION = re.compile(
    r'\bem\s+(?:(?:ate|no\s+maximo)\s+)?(?:quantas|quantos)[\s,]+'
    r'(?:no\s+maximo[\s,]+)?(?:parcelas|prestacoes|vezes)\b|'
    r'\bin\s+how\s+many\s+(?:installments|instalments|payments)\b')
MAXIMUM_ADVERB = re.compile(r'\bno\s+maximo\b')
QUANTITY = re.compile(r'\b(?:em|in|at)\s+(?:(?:ate|up to|no maximo)\s+)?'
                      r'(?:\d+(?:[.,]\d+)?|uma?|duas?|tres|quatro|cinco|seis|sete|oito|nove|dez|doze|one|two|three|twelve)\s*'
                      r'(?:x\b|parcelas?\b|prestacoes?\b|vezes\b|installments?\b|instalments?\b|payments?\b|dias?\b|days?\b)')

BANK_RELATION = re.compile(r'\b(?:conta|account)\s+(?:(?:corrente|bancaria|bank|checking)\s+)?(?:no|na|em|in|at|with)\s+(?:(?:o|a|the|banco|bank)\s+)*(?:santander|itau|bradesco|nubank|caixa|banco do brasil)\b')
NUMBER_CONTEXT = re.compile(r'\b(?:em|in|at)\s+(?:\d+(?:[.,]\d+)?\s*(?:%|por cento|percent)(?=\W|$)|(?:ate\s+)?(?:\d+|um|uma|dois|duas|tres|one|two|three)\s+(?:dias?|horas?|minutos?|days?|hours?|minutes?)\b)')


# General complement classes. These are lexical scope hints, not a geographic
# classifier or authorization to execute the described operation.
COMPLEMENT_HEADS = (
    r'manua(?:l|is)|manuals?|documentos?|documents?|documentacao|documentation|'
    r'fontes?|sources?|tutoriais|tutorial|guides?|guias?|paginas?|pages?|'
    r'orientacao|orientacoes|guidance|instructions?|instrucoes|nomenclatura|terminologia|'
    r'secao|secoes|sections?|capitulos?|chapters?|tabelas?|tables?|figuras?|figures?|'
    r'simulacao|simulacoes|simulations?|transacao|transacoes|transactions?|'
    r'operacao|operacoes|operations?|pre[- ]?autorizacao|pre[- ]?authorization|'
    r'configuracao|configuracoes|settings|impressao|printing|comprovantes?|receipts?|'
    r'modo|modes?|memoria|memory|casos?|cases?|situacao|situacoes|situations?|'
    r'condicao|condicoes|conditions?|momentos?|moments?|pratica|practice|'
    r'relacao|relation|geral|general|ingles|english|portugues|portuguese|'
    r'modelos?|models?|aparelhos?|devices?|maquininhas?|terminais|terminal|'
    r'dias?|days?|horas?|hours?|minutos?|minutes?|segundos?|seconds?|'
    r'semanas?|weeks?|mes|meses|months?|anos?|years?|prazos?|periodos?|periods?|'
    r'milimetros?|millimet(?:er|re)s?|centimetros?|centimet(?:er|re)s?|'
    r'reais|dolares|euros|brl|usd|eur'
)
COMPLEMENT_DETERMINERS = (
    r'o|a|os|as|um|uma|uns|umas|the|my|your|meu|minha|meus|minhas|seu|sua|seus|suas|'
    r'algum|alguma|alguns|algumas|qualquer|quaisquer|todo|toda|todos|todas|cada|qual|quais|que|'
    r'outro|outra|outros|outras|mesmo|mesma|mesmos|mesmas|proprio|propria|'
    r'any|every|each|all|another|other|same|which|what|own|'
    r'\d+(?:[.,]\d+)?|dois|duas|tres|quatro|cinco|seis|sete|oito|nove|dez|onze|doze|'
    r'one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve'
)
NON_GEOGRAPHIC_COMPLEMENT = re.compile(
    r'\b(?:no|na|nos|nas|em|in|at)\s+'
    r'(?:(?:'+COMPLEMENT_DETERMINERS+r')\s+){0,4}'
    r'(?:'+COMPLEMENT_HEADS+r')\b')
COMPOUND_PRODUCT_COMPLEMENT = re.compile(
    r'\b(?:no|na|em|in|at)\s+(?:(?:o|a|the)\s+)?'
    r'(?:conversor de moedas|currency converter)(?:\s+getnet)?\b')
# A complete year is temporal, not an arbitrary numeric place name. A following
# word prevents partial consumption of an unknown named locale ("em 2026land").
TEMPORAL_YEAR = re.compile(r'\b(?:em|in)\s+(?:19|20)\d{2}\b')


def unsupported_location(text, *, measurement_checked=False):
    """Abstém em locais/complementos incertos; não é um reconhecedor geográfico universal."""
    from app.rag.measurement_scope import mask_measurement_complements
    # Callers that already masked the original spelling must not reparse folded SI symbols.
    text=normalize(text if measurement_checked else mask_measurement_complements(text))
    # "No máximo" pode vir antes, dentro ou depois da pergunta quantitativa.
    # Só o reconhece como advérbio quando há a construção de parcelas inteira;
    # não libera "máximo" como nome de local nem remove outros complementos.
    if INSTALLMENT_QUESTION.search(text):
        text = MAXIMUM_ADVERB.sub(' ', text)
    text = INSTALLMENT_QUESTION.sub(' ', text)
    text = QUANTITY.sub(' ', text)
    # Um banco só é instituição quando ligado explicitamente a conta.
    # 'maquininha no Santander', 'em Lisboa' e outros locais continuam incertos.
    text = BANK_RELATION.sub(' ', text)
    text = re.sub(r'\b(?:cartao|card)\b.{0,35}\b(?:emitido|issued)\s+(?:(?:no|na|em|in|from|the)\s+)*\w+', ' ', text)
    text = NUMBER_CONTEXT.sub(' ', text)
    text = re.sub(r'\b(?:em|in)\s+(?:quanto tempo|quantos dias|quantas horas|qual prazo|qual data|how many days|how many hours)\b',' ',text)
    text = DEVICE_LOCATIVE.sub(' ', text)
    # Preposition + determiner/quantifier + a known non-geographic head.
    # Recognize the noun phrase, not the determiner alone: "em qualquer
    # cidade" remains unresolved, while "em qualquer transacao" is operational.
    # Only this complement is consumed; a later "em Lisboa" remains visible.
    text = NON_GEOGRAPHIC_COMPLEMENT.sub(' ',text)
    text = COMPOUND_PRODUCT_COMPLEMENT.sub(' ',text)
    text = TEMPORAL_YEAR.sub(' ',text)
    # O nome comercial composto é um dispositivo, não um país chamado "Get".
    text = re.sub(r'\b(?:no|na|em|in|at)\s+(?:the\s+)?get\s+(?:smart|classica)\b', ' ', text)
    return any(m.group(1) not in LOCAL_CONTEXTS for m in LOCATIVE.finditer(text))

def foreign_terms(message):
    words=set(re.findall(r'[a-z0-9]+',normalize(message)))
    foreign=words & FOREIGN
    # USA is a country acronym only in explicit location/case context; 'usa' is also a PT verb.
    if 'usa' in foreign and not re.search(r'\bUSA\b|\b(?:nos|em|in|no)\s+(?:the\s+)?usa\b',message):foreign.remove('usa')
    return foreign

def retrieval_plan(message):
    """Atendimento brasileiro; fontes globais preservadas para proveniência offline."""
    from app.brazil_scope import market_of
    market=market_of(message)
    if market.value in ('OUT','UNKNOWN'):return None,message
    from app.rag.measurement_scope import mask_measurement_complements
    text=re.sub(r'\bwi[- ]fi\b','wifi',normalize(mask_measurement_complements(re.sub(r'\bnós\b','we',message,flags=re.I))))
    # Quantidades e passos operacionais não são nomes de país.
    text=re.sub(r'\b(?:cartao|card|cliente|customer)\s+(?:de|do|da|from|no|in)\s+\w+','',text)
    if market.value!='BR' and unsupported_location(text, measurement_checked=True):return None,message
    return 'BR',message
