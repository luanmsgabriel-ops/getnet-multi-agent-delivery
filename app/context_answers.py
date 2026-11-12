"""Resolve perguntas sobre relatos já validados sem convertê-los em fatos externos.

O plano semântico escolhe entidades; esta camada apenas lê o estado autorizado e
separa uma pergunta de memória de uma consulta documental. Não executa ações.
"""
import re
from app.context_state import norm, summary, display_label

MEMORY_FIELDS = {
    'country': r'\b(?:pais|country|onde|where)\b',
    'product': r'\b(?:modelo|model|aparelho|terminal|maquininha|machine)\b',
    'symptom': r'\b(?:problema|defeito|issue|problem|relatei|informei)\b',
}

def answer_from_context(state, task, refs, fact):
    """Retorna None quando o pedido deve seguir para ferramenta ou fonte pública."""
    if task['kind'] in ('unsupported_action','outside','exchange_reference','exchange_ambiguous','exchange_sale','pause'):
        return None
    text=norm(task['quote'])
    personal=bool(re.search(r'\b(?:meu|minha|meus|minhas|my|our|informei|relatei|disse|era|estava|told|reported)\b',text))
    question=bool(re.search(r'\b(?:qual|quais|onde|what|which|where|confirma|lembr|record)\w*\b',text))
    fields=[name for name,pattern in MEMORY_FIELDS.items() if re.search(pattern,text)]
    choosing=bool(re.search(r'\b(?:comprar|escolher|recomenda|melhor|posso|funciona|aceita|vender|contratar|buy|choose|best)\b',text))
    contextual_country='country' in fields and bool(refs) and not re.search(r'getnet.*(?:atua|opera|presenca)|(?:paises|countries)',text)
    if (personal or contextual_country) and question and fields and not choosing and task['kind'] in ('information','summary','next_step'):
        if not refs:
            return 'Não tenho um aparelho identificado para essa referência. A qual aparelho você se refere?', []
        lines=[]
        for ref in refs:
            label=display_label(state,ref)
            for field in fields:
                if field=='symptom':
                    # Summary includes modality, incident and certainty, not just
                    # a literal symptom field; it never asserts a diagnosis.
                    related=[f for f in state['facts'].values() if f['entity']==ref and f['field'] in ('symptom','payment_status','connected','network_ok','printing_ok','error_code')]
                    lines.append(summary(state,[ref]) if related else f'Não há relato confirmado de problema em {label}. Qual problema você relatou nesse aparelho?')
                    continue
                value=fact(state,ref,field)
                if value is None and field=='country':value=state.get('context',{}).get('country')
                noun={'country':'país','product':'modelo'}[field]
                if value and value['origin']=='customer' and value['status'] in ('asserted','corrected'):
                    lines.append(f'{label}: você informou {value["value"]} como {noun}. É um relato desta sessão, não uma verificação remota.')
                else:lines.append(f'Não tenho {noun} confirmado para {label}. Qual é o {noun} desse aparelho?')
        return '\n'.join(lines), []
    # Retomada de incidente: progresso positivo em Wi-Fi não cria uma nova falha
    # de conexão. Uma limitação documental deve nomear o problema atual.
    resume=task['kind']=='next_step' or bool(re.search(r'\b(?:continu|retom|prossegu|resume|continue|proximo passo|next step)\w*',text))
    printing=bool(re.search(r'imprim|impress|print',text))
    if refs and task['kind']!='summary' and (printing or (resume and task['topic']=='other')):
        lines=[]
        for ref in refs:
            current=fact(state,ref,'printing_ok')
            symptom=fact(state,ref,'symptom')
            relevant=(printing and len(refs)==1) or bool(current and current['origin']=='customer' and current['status'] in ('asserted','corrected','false') and current['value']=='false') or bool(symptom and re.search(r'imprim|impress|print',norm(symptom['value'])))
            if not relevant:continue
            label=display_label(state,ref)
            country=fact(state,ref,'country') or state.get('context',{}).get('country')
            market=(' em '+country['value']) if country and country['origin']=='customer' and country['status'] in ('asserted','corrected') else ''
            confirmed=current and current['origin']=='customer' and current['status'] in ('asserted','corrected','false')
            if confirmed and current['value']=='true':
                lines.append(f'{label}: você informou que a impressão voltou. Há algum problema de impressão ainda ocorrendo?')
            else:
                observed='você relatou que o comprovante não é impresso' if confirmed and current['value']=='false' else 'sua dúvida é sobre a impressão do comprovante'
                lines.append(f'Sobre {label}{market}: {observed}. Não tenho um procedimento de impressão revisado para esse modelo e mercado; não vou aplicar os passos de Wi-Fi a esse problema. Qual mensagem aparece quando tenta imprimir? Não envie dados do cartão ou credenciais.')
        if lines:return '\n\n'.join(lines), []
    return None
