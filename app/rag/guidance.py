"""Apresentações revisadas para evidências específicas, nunca fatos sem recuperação.

Cada apresentação exige URL, título e SHA-256 do trecho completo revisado. Mudança
de conteúdo ou título (inclusive ressalvas) desabilita a apresentação até nova revisão.
Não é um catálogo universal de produtos, preços ou capacidades atuais.
"""
from dataclasses import dataclass
from hashlib import sha256
from app.intents import normalize, request_facts

SMART = 'https://site.getnet.com.br/wp-content/uploads/2025/09/Manul-GetSmart.pdf'
CLASSICA = 'https://site.getnet.com.br/wp-content/uploads/2026/06/getnet_12_06-26_Manul_GetClassica_V2.pdf'
WIFI = 'https://site.getnet.com.br/get-ajuda-configuracoes/como-configurar-o-wi-fi-na-sua-maquininha-getnet/'
LINK = 'https://site.getnet.com.br/get-ajuda-whatsapp-business/descontinuacao-whatsapp-business/'
ADVANCE = 'https://site.getnet.com.br/get-ajuda-antecipacao-de-venda/como-antecipar-sua-vendas-pelo-app/'
DECLINE = 'https://site.getnet.com.br/get-ajuda-gestao-de-vendas/quais-possiveis-status-das-minhas-vendas/'
PIX_ACCOUNT = 'https://site.getnet.com.br/duvidas/'
CREDIARIO = 'https://site.getnet.com.br/crediario/'
REVIEWED = {
    PIX_ACCOUNT: '535456495da90b7a9858432cb930e8cc9976fddb029abd7dd7b57ad233928d25',
    CREDIARIO: '5d99d1baab350e135805a9ade53cdfb75db26f13b6278c9514c878cad6588711',
    SMART: '1a660a57423289a983920b1a00921e86052a0aa5a4bcea1cffcd4423a8b42116',
    CLASSICA: 'f826eaf1f58bd86ae104840bcfc84964b6279c3c1e633084d5868c88b4838f2f',
    WIFI: '322fa01d11cd6f2cef13f77ad2c0fb3dfa1dcaa6cd459bf026f947a8aa237a68',
    LINK: '57670ec3b2613abce6fa964958ae8b122dd977e76a5a654cfe74da6e54c67dda',
    ADVANCE: '037bc4c89c4ed4dcc8500fa01293bdc830e2570528d41c55a6dea8470027f9e0',
    DECLINE: 'abd99791d13bbebef93f9bfe10ba0529a9fdbe3fbea9a397c77f93844be460a2',
}
REVIEWED_TITLES = {
    PIX_ACCOUNT: 'Receber vendas via Pix: conta bancaria ou conta de pagamento',
    CREDIARIO: 'Crediário: perguntas frequentes',
    SMART: 'Get Smart: caracteristicas tecnicas, manual pagina 3',
    CLASSICA: 'Get Classica: botoes e conectividade, manual paginas 3, 4 e 9',
    WIFI: 'Como configurar o Wi-Fi na sua maquininha Getnet?',
    LINK: 'Descontinuação dos pagamentos via WhatsApp Busines',
    ADVANCE: 'Como antecipar suas vendas pelo app?',
    DECLINE: 'Quais são os possíveis status das minhas vendas?',
}


CLASSICA_WIFI_HASH = '4205e38c671d1d2d72d964b5e02feacef2ae78db72fa32ccdc3b4223da6f572f'
PIX_DECLINE_HASH = 'af1b16d4f29208ba6976c9a3b5a2bf3e8f08e85a2b7c62cc4ce85e9a0642ac2d'


def decline_followup(facts):
    from app.response_notices import Notice, compose_notices
    if facts.error_code:
        return compose_notices(f'Você informou o código {facts.error_code}. Não tenho evidência suficiente para confirmar seu significado.',
                               Notice('decline'), 'Se persistir, consulte o canal oficial com esse código.', Notice('card_privacy'))
    question = 'Qual código de erro aparece no pagamento?' if facts.modality == 'pix' else 'Qual código de erro aparece na maquininha?'
    return compose_notices(Notice('decline'), Notice('card_privacy'), question)


@dataclass(frozen=True)
class Guidance:
    text: str
    sources: tuple[str, ...]
    # Critérios mínimos limitados de completude; não um verificador semântico universal.
    coverage: tuple[tuple[str, ...], ...]
    # Bloco literal válido pode ser prolixo ou falar na voz histórica da fonte.
    # Nesses casos, manter a apresentação revisada também após seleção válida.
    prefer_reviewed: bool = False

    def covers(self, answer):
        text = normalize(answer)
        return all(any(term in text for term in alternatives) for alternatives in self.coverage)


def reviewed_guidance(question, candidates):
    from app.response_notices import compose_notices
    import re
    from app.propositions import canonical
    words = set(re.findall(r'[a-z0-9]+', canonical(question)))
    facts = request_facts(question)
    def verified_block(source, digest):
        return any(c['source']==source and c.get('title')==REVIEWED_TITLES[source]
                   and sha256(c['text'].encode()).hexdigest()==digest for c in candidates)
    verified = {c['source'] for c in candidates
                if c['source'] in REVIEWED
                and c.get('title') == REVIEWED_TITLES[c['source']]
                and sha256(c['text'].encode('utf-8')).hexdigest() == REVIEWED[c['source']]}
    # Narrow presentations require the complete reviewed condition-bearing block.
    # Other attributes keep the multi-question/evidence path below.
    from app.request_plan import requested_attributes
    attrs=set(requested_attributes(question))
    if PIX_ACCOUNT in verified and 'pix' in words and words & {'conta','account'} and not facts.fee and not facts.decline:
        return Guidance('Você precisa de uma conta de recebimento elegível, mas não necessariamente de uma conta corrente: a FAQ também admite poupança e conta de pagamento pré-paga entre diferentes bancos. '
                        'Informe à Getnet uma chave Pix vinculada à conta desejada e confirme com o canal oficial a disponibilidade do provedor de serviços de pagamento (PSP) integrado. '
                        'Não consultei nem habilitei sua conta.', (PIX_ACCOUNT,), (('pre-paga',),('chave',),('psp',)), prefer_reviewed=True)
    if CREDIARIO in verified and 'crediario' in words and 'installments' in attrs and not attrs & {'settlement','eligibility'}:
        return Guidance('O Crediário anuncia parcelamento em até 48 vezes; o limite efetivo e os juros variam conforme o emissor do cartão. '
                        'Faça a simulação na maquininha antes da venda para conferir parcelas e encargos com o cliente. '
                        'Isso não confirma aprovação nem condições para uma transação específica.'+(' Não consigo confirmar a taxa aplicável ao seu estabelecimento; consulte as condições do contrato no app Getnet Brasil ou Portal do Cliente.' if facts.fee else ''), (CREDIARIO,), (('48',),('emissor',),('juros',),('simulacao',)))
    comparison = facts.comparison
    if comparison and {'smart','classica'} <= words and {SMART, CLASSICA} <= verified:
        wifi_note = ''
        if facts.connectivity:
            wifi_note = (' A página 9 da edição de 2026 também documenta Wi-Fi na Clássica; confirme a edição do seu modelo.'
                         if verified_block(CLASSICA,CLASSICA_WIFI_HASH) else
                         ' Não recuperei o trecho específico para confirmar Wi-Fi na Clássica nesta consulta.')
        return Guidance(
            'A diferença documentada está na interface e na conexão móvel: a Get Smart tem tela touchscreen e 4G; '
            'a Get Clássica tem botões físicos e chip 3G.\n\n'
            'O manual da Smart de junho/2025 também informa Wi-Fi e Bluetooth. A comparação usa essa edição e '
            'a da Clássica de 2026 (até quatro modelos); a ausência de um recurso no trecho não prova que ele não exista.'+wifi_note+'\n\n'
            'Qual é o modelo exato que você está considerando?',
            (SMART, CLASSICA), (('touchscreen',), ('botoes', 'botao'), ('3g',), ('4g',), ('2025',), ('2026',)),
            prefer_reviewed=True)
    from app.rag.core import query_tokens
    terms = query_tokens(question)
    decline = facts.decline
    if decline and facts.modality == 'pix' and verified_block(DECLINE,PIX_DECLINE_HASH):
        return Guidance(compose_notices('Para Pix, a fonte define o status “Negada” como pagamento do QR Code negado pelo banco do pagador. '
                        'Essa definição geral não confirma o motivo da sua transação.',decline_followup(facts)),
                        (DECLINE,), (('pix',),('banco do pagador',)),prefer_reviewed=True)
    if decline and not comparison and facts.modality != 'pix' and DECLINE in verified:
        return Guidance(
            compose_notices('Se o status da venda com cartão for “Negada”, a fonte da Getnet o define como não autorizado '
            'pelo emissor ou pela bandeira; isso não identifica o motivo específico da recusa.',decline_followup(facts)),
            (DECLINE,), (('emissor',), ('bandeira',), ('motivo',), ('codigo',)), prefer_reviewed=True)
    if 'classica' in facts.entities and facts.connectivity and verified_block(CLASSICA,CLASSICA_WIFI_HASH):
        return Guidance('A página 9 do manual da Get Clássica de 2026 documenta Wi-Fi na Clássica além do chip 3G. '
                        'Confira a edição e o modelo do aparelho; essa informação não comprova sua conexão atual. '
                        'A senha de rede deve ser inserida apenas na própria maquininha, nunca nesta conversa.',
                        (CLASSICA,), (('2026',),('wi-fi',)),prefer_reviewed=True)
    if 'link' in facts.entities and facts.fee and LINK in verified:
        return Guidance('Não consigo confirmar a taxa aplicável ao seu Link de Pagamento com as informações disponíveis. '
                        'A página consultada trata da migração do antigo pacote WhatsApp Business; suas condições não são uma tarifa universal para toda conta. '
                        'Confira a oferta e as condições da sua conta no app Getnet Brasil ou Portal do Cliente antes de contratar; não consultei sua conta nem contratei serviços.',
                        (LINK,), (('taxa',),('nao consigo confirmar',)),prefer_reviewed=True)
    # O mesmo fato por proposição governa recuperação e apresentação; não
    # reintroduzir aqui palavras de pedidos negados ou de credenciais removidas.
    if facts.connectivity and not comparison and not facts.decline and not words & {'saldo','balance','recebiveis'} and WIFI in verified:
        import re
        from app.rag.scope import DEVICE_LOCATIVE
        local_password_question=bool(DEVICE_LOCATIVE.search(normalize(question)) and
            not re.search(r'\b(?:chat|conversa|aqui|here|nao|not)\b',normalize(question)) and re.search(r'\b(?:senha|password)\b',normalize(question)) and
            re.search(r'\b(?:digitar|digitad[ao]|inserir|enter|entered|type|typed)\b',normalize(question)) and
            re.search(r'\b(?:posso|devo|pode|can i|should i)\b',normalize(question)))
        opening=('Sim: a orientação oficial é inserir e confirmar a senha da rede no próprio aparelho. '
                 if local_password_question else '')
        return Guidance(
            opening+'Para uma maquininha Getnet Brasil: Se estiver usando Wi-Fi, abra “Wi-Fi” na tela principal, selecione “Procurar Redes” '
            'e escolha a sua rede.\n\n'
            'Digite a senha da rede somente na própria maquininha e confirme; não envie a senha nesta conversa.\n\n'
            'Confira se a rede está funcionando e se os dados foram digitados corretamente; '
            'se ainda não conectar, qual mensagem de erro aparece? Nenhuma configuracao ou operacao foi realizada pelo assistente.',
            (WIFI,), (('tela principal', 'tela inicial'), ('procurar redes',), ('escolha', 'selecione sua rede'), ('confirme', 'confirmacao')))
    if {'whatsapp','link'} <= words and not comparison and LINK in verified:
        return Guidance(
            'Sim: a fonte consultada orienta criar o Link de Pagamento pelo app Getnet Brasil ou Portal do Cliente '
            'e compartilhá-lo com o cliente pelo WhatsApp.\n\n'
            'Isso é diferente do pagamento integrado ao WhatsApp Business: a página traz um anúncio de descontinuação '
            'datado de 15/01/2026, com migração para quem tinha aquele pacote. Esse anúncio não confirma uma migração na sua conta.\n\n'
            'Não criei nem enviei um link; confirme a disponibilidade e as condições da sua conta no app ou Portal do Cliente.',
            (LINK,), (('link',), ('compartilh', 'envio'), ('whatsapp',)), prefer_reviewed=True)
    if words & {'antecipacao','antecipar','advance','advancement'} and not comparison and ADVANCE in verified:
        return Guidance(
            'A antecipação permite receber antes as vendas no crédito, à vista ou parceladas. '
            'Segundo a página consultada, no app Getnet Brasil acesse Serviços e Antecipação de Vendas '
            'para consultar o valor disponível e simular valores, bandeiras e taxas antes de decidir.\n\n'
            'A fonte informa valor mínimo de R$ 50,00; confira os termos e as condições aplicáveis no próprio app. '
            'Não tenho acesso à sua conta para confirmar elegibilidade, taxa ou data de recebimento.\n\n'
            'Não solicitei nem confirmei uma antecipação. Não envie dados de autenticação nesta conversa.',
            (ADVANCE,), (('credito',), ('parcelad',), ('simular', 'simulacao'), ('taxa',), ('50',), ('termos',)))
    return None
