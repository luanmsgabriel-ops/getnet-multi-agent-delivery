"""Avisos explícitos do servidor; texto livre/fonte nunca ganha autoridade.

AnswerText conserva os blocos somente entre helpers privados que já retornam
texto. Os modelos de resposta preservam esses blocos em campo excluído do JSON.
Não há busca por frases, regex, remoção ou normalização de trechos de fontes.
"""
from dataclasses import dataclass
from typing import Literal

NoticeId = Literal['credentials', 'diagnosis', 'technical', 'decline', 'card_privacy']
CREDENTIAL_WARNING = ('Não envie senhas ou códigos de autenticação nesta conversa; '
                      'use-os somente no dispositivo ou canal oficial pertinente.')
DIAGNOSIS_LIMIT = ('Os relatos disponíveis não permitem confirmar a causa. '
                   'Não consultei transações reais nem fiz diagnóstico remoto.')
TECHNICAL_LIMIT = ('Não consultei dados de conta ou terminal para este identificador. '
                   'Posso apresentar apenas orientações públicas.')
DECLINE_LIMIT = ('Não tenho acesso à transação real para confirmar a causa ou regularizar a venda; '
                 'posso apresentar apenas orientações públicas.')
CARD_PRIVACY = ('Responda sem dados do cartão, senhas ou códigos de autenticação nesta conversa; '
                'use credenciais somente no dispositivo ou canal oficial pertinente.')
_TEXT = dict(credentials=CREDENTIAL_WARNING, diagnosis=DIAGNOSIS_LIMIT,
             technical=TECHNICAL_LIMIT, decline=DECLINE_LIMIT, card_privacy=CARD_PRIVACY)
_COVERS = {'decline': {'diagnosis', 'technical'}, 'card_privacy': {'credentials'}}

@dataclass(frozen=True)
class Notice:
    key: NoticeId

class AnswerText(str):
    """Adapter de texto interno com proveniência explícita e imutável dos blocos."""
    def __new__(cls, parts):
        blocks=[]
        for part in parts:
            if isinstance(part, AnswerText): blocks.extend(part.parts)
            elif isinstance(part, (str, Notice)): blocks.append(part)
            else: raise TypeError('Bloco de apresentação inválido')
        present={p.key for p in blocks if isinstance(p, Notice)}
        covered=set().union(*(_COVERS.get(k,set()) for k in present))
        seen=set(); output=[]; kept=[]
        for part in blocks:
            if isinstance(part, Notice):
                if part.key in covered or part.key in seen: continue
                seen.add(part.key); output.append(_TEXT[part.key]);kept.append(part)
            elif part:
                output.append(part);kept.append(part)
        value=super().__new__(cls,'\n\n'.join(output))
        value.parts=tuple(kept)
        return value


def compose_notices(*parts, credentials=False):
    return AnswerText([*parts, *([Notice('credentials')] if credentials else [])])


def response_parts(response):
    """Metadado obsoleto após model_copy nunca substitui o texto efetivo."""
    text=getattr(response,'answer',None)
    if text is None:text=response.texto
    parts=getattr(response,'presentation',())
    if parts and str(AnswerText(parts))==text:return tuple(parts)
    return (text,)
