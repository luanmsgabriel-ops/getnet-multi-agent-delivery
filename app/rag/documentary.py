"""Canonical documentary adapter: intact question, no scenario answer rewrites.

A retrieved block is available evidence, not automatic proof that every requested
attribute was answered. Model synthesis is separate and explicitly configured.
"""
import re
import time
from app.observability import emit_event
from app.contracts import Entrada,RespostaEspecialista
from app.knowledge import KnowledgeRag
from .core import MAX_QUERY,evidence_text
from .grounding import literal_claims,RejectedSynthesis
from .coverage import numeric_limits
from .applicability import CorpusScopes
from .semantic import SemanticInputError

# Recognize explicit instructions about response content, not negated product
# properties (e.g. "sem fio" or "não imprime"). No product/topic vocabulary.
PROSE_EXCLUSION = re.compile(
 r"\b(?:sem\s+(?:falar|tratar|mencionar|abordar|incluir|explicar|descrever)"
 r"|n[aã]o\s+(?:fale|trate|mencione|aborde|inclua|explique|descreva)"
 r"|without\s+(?:discussing|mentioning|including|explaining|describing)"
 r"|(?:do not|don't)\s+(?:discuss|mention|include|explain|describe))\b", re.I)

class DocumentaryKnowledge(KnowledgeRag):
 documentary=True
 def __init__(self,index,*,scopes=None,semantic=None,synthesizer=None):
  super().__init__(index,reviewed_presentations=False,synthesizer=synthesizer)
  self.scopes=scopes or CorpusScopes(index)
  self.semantic=semantic
 def _retrieve(self,message,*,requested_services=()):
  # Never rewrite the query into a scenario or a reported incident.
  options={'requested_services':requested_services} if requested_services else {}
  result=(self.semantic.search(message,market='BR',**options) if self.semantic is not None
          else self.index.rerank(message,[c for c in self.index.entries
                    if self.scopes.compatible(message,c)],market='BR'))
  from app.agentic_capabilities import safe_text
  from app.public_information import public_url
  scoped=[c for c in result['candidates'] if self.scopes.compatible(message,c)]
  # Isolate unsafe blocks instead of discarding independent, usable evidence.
  # Both generation and literal fallback consume this same filtered set.
  found=[c for c in scoped if public_url(c['source'])
         and not safe_text(c['title']+' '+c['text'])[1]]
  return {**result,'candidates':found,'safety_filtered_count':len(scoped)-len(found),
          'status':'candidates' if found else ('unavailable' if result['status']=='unavailable' else 'insufficient_evidence')}
 def responder(self,entrada,contexto):
  return self._single(entrada,contexto)
 def _single(self,entrada,contexto,*,deadline=None,focus=None,requested_services=(),non_geographic=()):
  from app.brazil_scope import market_of,REDIRECT_BR,CLARIFY_BR
  from app.privacy import clean_message
  from app.intents import request_facts,receivable_query
  def reply(text,status='limitado',sources=(),claims=(),coverage=None,mode='extrativo',limitation=None):
   return RespostaEspecialista(texto=text,status=status,fontes=list(sources),grounding=list(claims),
                              evidence_coverage=coverage,modo=mode,limitation_code=limitation)
  original=entrada.message
  from .applicability import validated_services
  try:validated_services(original,requested_services)
  except (TypeError,ValueError):
   return reply('O plano de serviços não está vinculado à pergunta original. Nenhuma síntese foi executada.','recusado')
  if focus is not None and (not isinstance(focus,str) or focus not in original
       or re.fullmatch(r'\w+(?:-\w+)?',focus) is None):
   return reply('O foco não está vinculado à pergunta original. Nenhuma síntese foi executada.','recusado')
  if len(original)>MAX_QUERY:return reply('Envie uma pergunta pública com até 2000 caracteres; a pergunta não foi truncada.')
  clean,redacted=clean_message(original)
  if redacted or self._suspicious(original):
   return reply('Não envio credenciais ou instruções de alteração de regras para consultas. Envie somente a pergunta pública, sem dados privados.','recusado')
  from .query_scope import documentary_market
  try:
   if non_geographic and contexto:raise ValueError('Conversation restrictions cannot be reinterpreted')
   market=documentary_market(original,non_geographic)
  except ValueError:
   return reply('Não foi possível validar a interpretação do escopo; confirme se a dúvida é documental da Getnet Brasil.','recusado')
  if market.value in ('OUT','UNKNOWN'):
   return reply(REDIRECT_BR if market.value=='OUT' else CLARIFY_BR)
  facts=request_facts(original)
  if facts.unsupported_action:
   return reply('Este adaptador apenas consulta documentos públicos. Não transferi valores, contratei, alterei ou cancelei serviços.')
  if facts.account_migration or receivable_query(original).individual:
   return reply('Documentos públicos não confirmam o estado da sua conta ou seus valores individuais. Nenhuma conta foi consultada.')
  retrieval_started=time.perf_counter()
  try:
   options={'requested_services':requested_services} if requested_services else {}
   result=self._retrieve(original,**options)
  except SemanticInputError:
   emit_event('retrieval',stage='retrieval',outcome='invalid',duration_ms=(time.perf_counter()-retrieval_started)*1000)
   return reply('A pergunta excede o limite de tokens do modelo local; divida-a sem remover condições. Nenhum texto foi truncado e não usei outro provedor.')
  except Exception:
   emit_event('retrieval',stage='retrieval',outcome='unavailable',duration_ms=(time.perf_counter()-retrieval_started)*1000)
   return reply('A recuperação documental configurada está indisponível; não usei outro provedor nem troquei silenciosamente de método.','indisponivel')
  emit_event('retrieval',stage='retrieval',outcome='ok' if result['status']=='candidates' else 'absent',duration_ms=(time.perf_counter()-retrieval_started)*1000,count=len(result['candidates']))
  if result['status']!='candidates':
   return reply('Não encontrei evidência documental pertinente suficiente para esta pergunta nas fontes brasileiras disponíveis.','sem_evidencia')
  candidates=result['candidates']
  if any(self._suspicious(c['text']) or self._suspicious(c['title']) for c in candidates):
   return reply('A evidência recuperada precisa de revisão de segurança antes de ser exibida.','sem_evidencia')
  from app.agentic_client import BudgetExhausted, ModelUnavailable
  scope_rejected=False
  budget_stopped=False
  generation_unavailable=False
  if self.synthesizer is not None:
   try:
    options={'deadline':deadline}
    if focus is not None:options['focus']=focus
    text,sources,claims,complete=self.synthesizer.synthesize(original,candidates,**options)
    return reply(text,'evidencias' if complete else 'limitado' if claims else 'sem_evidencia',sources,claims,
                 'supported' if complete else 'partial','gerado')
   except RejectedSynthesis as exc:
    failed=True;scope_rejected=exc.scope_rejected
   except BudgetExhausted:
    failed=True;budget_stopped=True
   except (ModelUnavailable,TimeoutError):
    failed=True;generation_unavailable=True
   except Exception:
    failed=True
  else:failed=False
  # The extractive path cannot certify semantic topic exclusions. Removing
  # matching words/sentences could also remove conditions or leave related facts.
  # Keep evidence intact for successful synthesis above; disclose sources only
  # when falling back under an explicit content restriction.
  if scope_rejected:
   sources=list(dict.fromkeys(c['source'] for c in candidates))
   return reply('A síntese não respeitou o escopo do pedido e foi rejeitada. Não reproduzi os blocos integrais porque a pertinência deles ao pedido não foi confirmada. As fontes recuperadas abaixo não constituem uma resposta nem comprovam ausência de informação.\n\nFontes recuperadas para consulta:\n'+'\n'.join(sources),sources=sources,coverage='partial',limitation='answer_rejected')
  if PROSE_EXCLUSION.search(original):
   reason=('O orçamento do modelo foi esgotado. ' if budget_stopped else
           'A síntese não foi validada. ' if failed else 'A geração por modelo está desativada. ')
   sources=list(dict.fromkeys(c['source'] for c in candidates))
   text=(reason+'Não consigo garantir que os blocos integrais recuperados respeitem as exclusões de assunto do pedido. '
         'Por isso não reproduzi trechos nem recortei suas condições. As fontes abaixo foram recuperadas, '
         'mas esta resposta não apresenta as orientações solicitadas nem afirma ausência de informação nelas.'
         +'\n\nFontes recuperadas para consulta:\n'+'\n'.join(sources))
   return reply(text,sources=sources,coverage='partial',
                limitation='budget_exhausted' if budget_stopped else 'generation_unavailable' if generation_unavailable else None)
  # Full blocks, no two-URL requirement and no numerical-price veto.
  # Size is bounded without clipping a condition or quote.
  selected=[];seen=set();size=0;omitted=False
  for c in candidates:
   identity=(c['source'],c['title'],c['text'])
   if identity in seen:continue
   block=evidence_text(c)+'\nFonte: '+c['source']+'\nCaptura: '+c['captured_at']
   if size+len(block)>3000:
    omitted=True;continue
   selected.append(c);seen.add(identity);size+=len(block)+2
   if len(selected)==3:break
  if not selected:return reply('Os blocos completos excedem o limite da resposta; reformule a pergunta sem retirar as condições relevantes.')
  lines=['Fontes públicas da Getnet Brasil. Trechos recuperados sem geração por LLM; cobertura integral da pergunta não verificada. Não executei operações nem confirmei condições individuais.']
  if any((self.scopes.metadata(c) or {}).get('applicability')=='generic_terminal_guidance_not_all_models' for c in selected):
   lines.append('Aplicabilidade: o procedimento é para a conexão descrita na fonte, não para qualquer falha de internet. Confirme o modelo e se usa Wi-Fi ou chip antes de aplicar a orientação; não diagnostiquei o aparelho.')
  if budget_stopped:lines.append('O orçamento do modelo foi esgotado. Preservo apenas os trechos disponíveis, sem nova chamada ou declaração de cobertura completa.')
  elif failed:lines.append('A síntese não foi validada; a redação rejeitada não foi exibida e não houve nova tentativa.')
  for c in selected:
   b=self.scopes.metadata(c)
   # Metadata is disclosed as scope context, never spliced into the literal quote.
   sections=b.get('section_scopes',[]) if b else []
   if any(x.get('context_dependency') for x in sections):
    lines.append('Contexto documental revisado: este bloco continua a seção anterior; não transfira suas definições a outra modalidade de pagamento.')
   lines.append(evidence_text(c)+'\nFonte: '+c['source']+'\nCaptura: '+c['captured_at'])
  if omitted:lines.append('Parte dos blocos recuperados não coube integralmente nesta resposta. A cobertura das partes solicitadas permanece não verificada; não trate omissão como ausência do recurso.')
  gaps=numeric_limits(original,selected)
  lines.extend(gaps)
  text='\n\n'.join(lines)
  if len(text)>4000:return reply('A evidência integral e suas ressalvas excedem o limite; envie uma parte da pergunta por vez.')
  return reply(text,'limitado',dict.fromkeys(c['source'] for c in selected),literal_claims(selected),
               'partial' if gaps else 'not_assessed',limitation='budget_exhausted' if budget_stopped else 'generation_unavailable' if generation_unavailable else None)
