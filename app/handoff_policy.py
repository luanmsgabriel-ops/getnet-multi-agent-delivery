"""Pure local-handoff recommendation. It never registers or confirms a ticket."""
import re
from app.intents import normalize
from app.privacy import clean_message


def handoff_offer(message,result,*,enabled=False):
    if not enabled:return None
    safe,redacted=clean_message(message);text=normalize(safe)
    from app.agentic_capabilities import suspicious
    if redacted or suspicious(safe):return None
    from app.brazil_scope import market_of
    if market_of(safe).value in ('OUT','UNKNOWN'):return None
    human=r'(?:humano|atendente|operador|human|operator)'
    if re.search(r'\b(?:nao|nunca|not|never)\b.{0,35}\b(?:encaminh|transfir|transfer|cham|registr|human|atendent|operador)',text):return None
    direct=bool(re.search(r'\b(?:quero|preciso|pode|falar|chame|encaminhe|transfira|want|need|speak)\b.{0,60}\b'+human+r'\b',text))
    billing=bool(re.search(r'\b(?:fui cobrad[oa]|me cobraram|cobranca indevida|cobranca duplicada)\b',text))
    explanatory=bool(re.match(r'^(?:explique|o que (?:e|significa)|como funciona|what is|explain)\b',text))
    if explanatory and not direct:billing=False
    topic=('recebiveis' if billing or re.search(r'\b(?:recebiveis|recebimento|minhas vendas|meu saldo)\b',text) else
           'conectividade' if re.search(r'\b(?:wifi|wi-fi|internet|conecta|conexao)\b',text) and re.search(r'\b(?:getnet|maquininha|terminal|smart|classica|aparelho)\b',text) else
           'terminal' if re.search(r'\b(?:maquininha|terminal|aparelho)\b',text) else None)
    status=result.get('status');stop=result.get('agentic',{}).get('stop')
    reason=None
    if direct:reason='customer_request'
    elif billing:reason='billing_review'
    elif topic and (status=='indisponivel' or stop in ('model_timeout','model_or_decision_unavailable')):reason='tool_unavailable'
    elif topic and stop in ('no_progress','no_new_evidence','tool_limit','step_limit'):reason='unresolved'
    elif topic and status=='sem_evidencia':reason='evidence_gap'
    if reason is None:return None
    return {'state':'offer_only','reason':reason,'topic':topic,'summary_preview':safe[:600],
        'summary_is_excerpt':len(safe)>600,'summary_review_required':True,'requires_confirmation':True,
        'destination':'local_operator_demo','sent_to_getnet':False,'operator_notified':False,
        'message':'Posso preparar um encaminhamento para a fila de operador desta demonstracao local. Revise o resumo e a categoria antes de confirmar. Nada foi registrado ou enviado a Getnet; nao ha prazo de resposta nem reembolso prometido.'}
