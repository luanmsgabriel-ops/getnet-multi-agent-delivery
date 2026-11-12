"""Subconsultas limitadas preservam modalidade e cobertura de entidades."""
import re
from app.intents import request_facts, normalize
from app.rag.core import tokens


def retrieve_brazil(index, question):
    from app.request_plan import without_declined_requests
    question=without_declined_requests(question)
    facts = request_facts(question)
    if facts.decline:
        # A definição Pix está no bloco seguinte ao catálogo de cartões. Não
        # converter modalidade ausente em cartão nem usar status do terminal.
        query = 'negada banco pagador' if facts.modality == 'pix' else 'transacao negada cartao'
        result = index.search(query)
        if facts.modality is None:
            other = index.search('negada banco pagador')
            result = merge_results([result, other])
        return result
    if facts.comparison:
        results = [index.search(f'get {entity} botoes' if entity == 'classica' else 'get smart touchscreen')
                   for entity in ('classica','smart')]
        # Uma evidência principal por entidade antes de preencher os demais slots.
        selected=[]
        for entity,result in zip(('classica','smart'),results):
            matching=[c for c in result['candidates'] if entity in tokens(c['title'])]
            if matching:selected.append(matching[0])
        if facts.connectivity:
            result=index.search('classica wifi')
            selected += [c for c in result['candidates'] if 'classica' in tokens(c['title']) and 'wifi' in tokens(c['text'])][:1]
        return merge_results([{'status':'candidates','candidates':selected}])
    if 'classica' in facts.entities and facts.connectivity:
        result=index.search('classica wifi')
        return merge_results([{'status':result['status'],'candidates':[c for c in result['candidates']
                              if 'classica' in tokens(c['title']) and 'wifi' in tokens(c['text'])]}])
    if 'link' in facts.entities and facts.fee:
        return index.search('link pagamento whatsapp')
    if facts.connectivity:
        return index.search('configurar wifi maquininha')
    if re.search(r'\b(?:antecipacao|antecipar|advance|advancement)\b',normalize(question)):
        return index.search('antecipacao vendas app')
    if re.search(r'\bcrediario\b',normalize(question)):
        return index.search('crediario parcelas')
    # Uma cláusula que apenas nega pedir uma ação não dilui a pergunta pública.
    # Escopo e guardrails já examinaram a mensagem original, antes deste passo.
    clauses=re.split(r'[;!?]',question)
    if len(clauses)>1:
        meaningful=[c.strip() for c in clauses if c.strip() and not re.fullmatch(
            r'\s*(?:nao|not)\s+(?:quero|desejo|want to)\s+(?:transferir|contratar|alterar|cancelar)\b[^.!?;]*',normalize(c))]
        if meaningful:question=' '.join(meaningful)
    return index.search(question)


def merge_results(results):
    rows=[]; seen=set()
    for result in results:
        for row in result['candidates']:
            identity=(row['source'],row.get('ordinal'),row['text'])
            if identity not in seen:
                rows.append(row);seen.add(identity)
    return {'status':'candidates' if rows else 'insufficient_evidence','candidates':rows[:3]}
