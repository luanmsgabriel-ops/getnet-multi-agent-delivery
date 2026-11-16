"""Narrow reference detection; no fact extraction, authorization or retrieval."""
import re
from app.intents import normalize

MISSING_REFERENCE = 'Não tenho esse relato recuperado neste atendimento. Qual aparelho ou assunto e qual problema você quer retomar?'
DEGRADED_REFERENCE = 'Não consegui interpretar essa continuação com segurança. Informe o aparelho ou assunto e repita o detalhe que deseja consultar; não fiz nova consulta com uma referência presumida.'

def recall_request(message):
    text=normalize(message)
    return bool(re.search(r'\b(?:qual|quais|what|which|lembre|recorde)\b',text) and
        re.search(r'\b(?:informei|relatei|disse|mencionei|told|reported|de antes|anteriormente|antes disso)\b',text))

def dependent_reference(message):
    """Detect explicit recall or an unbound pronoun, not ordinary past tense."""
    text=normalize(message)
    if recall_request(message):return True
    from app.brazil_scope import BUSINESS
    # Named public subjects and within-message antecedents remain self-contained.
    subject_text=re.sub(r'\b(?:esse|essa|este|esta|aquele|aquela)\s+(?:erro|aparelho|problema|terminal|maquininha|caso|situacao)\b','',text)
    if BUSINESS.search(subject_text) or re.search(r'\b(?:clima|cotacao|previsao|weather|exchange)\b',text):return False
    return bool(re.search(r'\b(?:dela|dele|delas|deles|disso|daquilo|its|that one)\b',text) or
        re.search(r'\b(?:esse|essa|este|esta|aquele|aquela)\s+(?:erro|aparelho|problema|terminal|maquininha|caso|situacao)\b',text) or
        re.fullmatch(r'(?:e\s+)?agora[ ?!.]*',text))

def reference_clarification(message, state):
    """Only absent memory triggers this reply; stored dialogue is not factual proof."""
    if not dependent_reference(message):return None
    if any(state.get(k) for k in ('devices','facts','supervisor_dialogue','supervisor_pending','context','goals')):return None
    return MISSING_REFERENCE
