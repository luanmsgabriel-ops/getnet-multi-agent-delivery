"""Candidata enxuta: contexto separado do plano de atendimento e do núcleo existente."""
from pathlib import Path
from copy import deepcopy
from datetime import date
import hashlib,json,re,time,os
from app.context_state import apply_turn,summary,clean_message,norm,CONTROL
from app.context_store import Store,Conflict
from app.context_contract import Turn
from app.response_notices import Notice, compose_notices, response_parts
from app.contracts import Entrada
from app.knowledge import KnowledgeRag,KnowledgeDispatch
from app.orchestration import Orquestrador
from app.support import SupportCatalogoDemo, simulation_date
from app.service_policy import DISCLOSURE,REDIRECT,QUOTE,CLARIFY,DCC_SOURCE
from app.rag.guidance import WIFI,CLASSICA,LINK,REVIEWED,REVIEWED_TITLES,CLASSICA_WIFI_HASH

def fingerprint(c):
    return hashlib.sha256(json.dumps({k:c.get(k) for k in ('source','title','text','market')},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
class ApprovedIndex:
    """Publicação editorial é configuração do servidor, não autoaprovação da fonte."""
    def __init__(self,index,approved):self.index=index;self.approved=frozenset(approved)
    def __getattr__(self,name):return getattr(self.index,name)
    def search(self,*args,**kw):
        result=self.index.search(*args,**kw)
        if result.get('status')!='candidates':return result
        found=[c for c in result['candidates'] if fingerprint(c) in self.approved]
        return {**result,'candidates':found,'status':'candidates' if found else 'insufficient_evidence'}

class ContextService:
    def __init__(self,store,interpreter=None,corpus=None,core=None):
        self.store=store;self.interpreter=interpreter
        corpus=Path(corpus or Path(__file__).resolve().parent.parent/'corpus_publico')
        local=KnowledgeRag.from_directory(corpus)
        # Approved file is versioned and reviewed separately from user/document input.
        manifest=Path(__file__).with_name('context_evidence.json')
        approved=json.loads(manifest.read_text('utf-8'))
        local.index=ApprovedIndex(local.index,approved)
        self.local=local
        web=None
        if os.environ.get('GETNET_WEB_SEARCH')=='1':
            from app.knowledge import KnowledgeWeb
            from app.rag.official_catalog import official_search
            web=KnowledgeWeb(official_search())
        self.core=core or Orquestrador(knowledge=KnowledgeDispatch(local,web),support=SupportCatalogoDemo())
    def create(self,principal):return self.store.create(principal)
    def state(self,principal,session):return self.store.read(principal,session)[1]
    def reset(self,principal,session):self.store.reset(principal,session)
    def public(self,dados):
        entrada=Entrada.model_validate(dados);message=entrada.message;principal=entrada.user_id
        safe,redacted=clean_message(message)
        from app.service_policy import service_plan
        policy=service_plan(safe)
        # Orchestrator handles policy replies; fallback must never reintroduce excluded clauses.
        scoped=policy.message
        result=self.core.executar({'message':safe[:4000],'user_id':principal})
        from app.intents import request_facts
        facts=request_facts(scoped)
        from app.rag.scope import retrieval_plan
        market,_=retrieval_plan(scoped) if scoped else (None,scoped)
        # Technical instructions do not require a registered synthetic account.
        if scoped and market=='BR' and not policy.replies and result.status in ('recusado','limitado') and not result.sources and not facts.unsupported_action and (facts.connectivity or facts.decline) and not re.search(r'saldo|recebiveis|outra conta|outro cliente',norm(message)) and not CONTROL.search(message):
            public=self.local.responder(Entrada(message=safe,user_id=principal),())
            result=result.model_copy(update={'answer':public.texto,'sources':public.fontes,'status':public.status})
        allowed_link=LINK
        if facts.fee and facts.entities==frozenset({'link'}) and any(source!=allowed_link for source in result.sources):
            result=result.model_copy(update={'answer':'Não tenho evidência pertinente suficiente para confirmar a taxa do Link aplicável à sua conta. Não consultei sua conta nem contratei serviços.','sources':[],'status':'sem_evidencia'})
        credential=redacted or bool(re.search(r'senha|password|autenticacao|otp|codigo sms',norm(message)))
        if credential:
            parts=[*response_parts(result),Notice('credentials')]
            if market=='BR' and WIFI not in result.sources and (facts.connectivity or re.search(r'configur.+(?:maquinin|terminal)',norm(scoped))) and not CONTROL.search(safe):
                dummy={'devices':{'public':{'label':'Clássica' if 'classica' in facts.entities else 'maquininha'}},'facts':{}}
                text,sources=self._wifi(dummy,'public')
                parts.append('Se sua dúvida é configurar Wi-Fi: '+text)
                result=result.model_copy(update={'sources':list(dict.fromkeys(result.sources+sources))})
            answer=compose_notices(*parts)
            result=result.model_copy(update={'answer':str(answer),'presentation':list(answer.parts)})
        return result
    def _core(self,message,principal):
        result=self.public({'message':message,'user_id':principal})
        return compose_notices(*response_parts(result)),result.sources,[e.model_dump() for e in result.eventos]
    def _fact(self,state,ref,field,subject='device'):
        active=state.get('active_incidents',{}).get(ref+'|'+subject) or (state.get('active_incidents',{}).get(ref) if subject=='device' else None)
        matches=[f for f in state['facts'].values() if f['entity']==ref and f['field']==field and f.get('subject','device')==subject and (not f['incident'] or f['incident']==active)]
        return matches[-1] if matches else None
    def _wifi(self,state,ref):
        from app.brazil_scope import known_country, REDIRECT_BR, CLARIFY_BR
        market=known_country(state,ref)
        if market!='BR':return (REDIRECT_BR if market=='OUT' else CLARIFY_BR),[]
        evidence=self.local._retrieve('maquininha Wi-Fi configurar redes internet')
        valid=any(c['source']==WIFI and c['title']==REVIEWED_TITLES[WIFI] and hashlib.sha256(c['text'].encode()).hexdigest()==REVIEWED[WIFI] for c in evidence.get('candidates',[]))
        if not valid:return 'Não tenho a orientação Wi-Fi revisada disponível nesta tentativa; não vou inventar os passos.',[]
        def known(field,value):
            f=self._fact(state,ref,field)
            return f and f['origin']=='customer' and f['status'] in ('asserted','corrected','false') and f['value']==value
        if known('connected','true'):
            text='Você relatou que a conexão voltou. Isso encerra este relato de conexão, sem comprovar outras operações ou diagnóstico remoto.'
        elif known('password_entered_on_device','true'):
            text='Você já selecionou a rede e digitou a senha no aparelho, mas isso não comprova que ela estava correta nem a causa da falha. Confira se a rede está funcionando e os dados foram digitados corretamente. Qual mensagem de erro aparece?'
        elif known('network_selected','true'):
            text='Como você já selecionou a rede, digite a senha somente na própria maquininha e confirme; não envie a senha nesta conversa. Depois confira se conectou; nenhuma configuração foi feita pelo assistente.'
        else:
            text='Se estiver usando Wi-Fi, na maquininha, abra Wi-Fi na tela principal, selecione Procurar Redes e escolha sua rede. Digite a senha somente no próprio aparelho e confirme; nunca envie a senha nesta conversa. Confira se a rede está funcionando e os dados foram digitados corretamente.'
        # Unknown progress is neither completed nor undone: make the procedure conditional.
        uncertain=[]
        names={'network_selected':'seleção da rede','password_entered_on_device':'senha digitada no aparelho','connected':'conexão concluída'}
        active=state.get('active_incidents',{}).get(ref+'|device') or state.get('active_incidents',{}).get(ref)
        for field,label in names.items():
            current=self._fact(state,ref,field)
            confirmed=current and current['origin']=='customer' and current['status'] in ('asserted','corrected','false') and current['value'] in ('true','false')
            if confirmed:continue
            alternatives=[f for f in state.get('observations',[]) if f.get('entity')==ref and f.get('field')==field and f.get('subject','device')=='device' and (not f.get('incident') or f['incident']==active) and f.get('status')!='retracted']
            if current or alternatives:uncertain.append(label)
        if uncertain and not known('connected','true'):
            text='Ainda não tenho confirmação direta de: '+', '.join(uncertain)+'. Confira no aparelho quais etapas já foram concluídas e execute apenas as que faltarem. '+text
        product=self._fact(state,ref,'product')
        if 'classica' in norm((product or {}).get('value','')+' '+state['devices'].get(ref,{}).get('label','')):
            manual=self.local._retrieve('Wi-Fi Get Clássica')
            checked=any(c['source']==CLASSICA and c['title']==REVIEWED_TITLES[CLASSICA] and hashlib.sha256(c['text'].encode()).hexdigest()==CLASSICA_WIFI_HASH for c in manual.get('candidates',[]))
            if checked:
                text+=' A orientação da Clássica depende da edição e do modelo; a página 9 do manual de 2026 documenta Wi-Fi.'
                return text,[WIFI,CLASSICA]
            text+=' Não recuperei o manual da edição da Clássica para confirmar detalhes específicos desse modelo.'
        return text,[WIFI]
    def _plan(self,state,message,principal):
        lines=[];sources=[];traces=[]
        requests=state['requests']
        for task in requests:
            kind,topic=task['kind'],task['topic'];refs=[x for x in task['entities'] if x in state['devices']] or state['focus']
            # Reading already validated session facts is not a local procedure.
            # Resolve each requested field even if another field is unknown.
            from app.context_answers import answer_from_context
            contextual=answer_from_context(state,task,refs,self._fact)
            if contextual is not None:
                text,src=contextual;lines.append(text);sources+=src
                continue
            from app.brazil_scope import known_country, market_of, REDIRECT_BR, CLARIFY_BR
            explicit=market_of(task.get('quote',''))
            scoped_refs=[]
            for ref in refs:
                market=explicit.value if explicit.value!='NONE' else known_country(state,ref)
                if market=='BR':scoped_refs.append(ref)
                else:lines.append(REDIRECT_BR if market=='OUT' else CLARIFY_BR)
            if refs and not scoped_refs:continue
            refs=scoped_refs
            if not refs:
                market=explicit.value if explicit.value!='NONE' else known_country(state)
                if market in ('OUT','UNKNOWN'):
                    lines.append(REDIRECT_BR if market=='OUT' else CLARIFY_BR);continue
            if kind=='summary' and not refs and topic!='other':kind='information'
            if kind=='summary':
                lines.append(summary(state,refs) or 'Não há fatos anteriores confirmados nesta sessão para esse resumo.')
                if any(f['entity'] in refs and f['field'] in ('connected','symptom','payment_status') for f in state['facts'].values()):lines.append('Esses são relatos do atendimento, não diagnóstico remoto. A causa da falha e o resultado de operações reais não foram confirmados.')
                continue
            if kind=='diagnosis':
                lines.append(Notice('diagnosis'))
                if topic=='connectivity':
                    from app.intents import request_facts
                    if not request_facts(task['quote']).connectivity:
                        if refs:lines.append(summary(state,refs))
                        lines.append('Qual mensagem aparece no aparelho? Não envie senhas ou códigos de autenticação.')
                        continue
                kind='information'
            if kind=='pause':lines.append('O atendimento ficou pausado; os relatos anteriores permanecem separados por aparelho.');continue
            if kind=='unsupported_action':
                action=task.get('action','other')
                limitations={
                    'configure_device':'Não posso configurar o aparelho remotamente nem receber sua senha.',
                    'cancel_registration':'Não tenho ferramenta para cancelar cadastro. Nenhum cadastro foi cancelado.',
                    'transfer_funds':'Não tenho ferramenta para transferir saldo. Nenhuma transferência foi executada.',
                    'contract_service':'Não tenho ferramenta para contratar serviços. Nenhum serviço foi contratado.',
                    'other':'As ferramentas deste protótipo apenas consultam dados fictícios. Não posso executar alterações, cancelamentos, configurações remotas ou operações financeiras; nenhuma dessas ações foi realizada.'}
                lines.append(limitations[action]+' Nenhuma operação foi executada.')
                if topic=='connectivity':
                    lines.append('Posso orientar os passos que você executa no próprio aparelho, sem receber senhas.')
                    for ref in refs:
                        text,src=self._wifi(state,ref);lines.append(text);sources+=src
                continue
            if kind=='outside':lines.append(REDIRECT);continue
            if kind=='exchange_reference':
                from app.service_policy import currency_reply
                policy=currency_reply(task['quote'])
                lines.append(policy.texto if policy else CLARIFY);continue
            if kind=='exchange_ambiguous':lines.append(CLARIFY);continue
            if kind=='clarify':
                if state['pending']:continue
                lines.append('Preciso identificar a qual aparelho ou assunto você se refere para continuar sem misturar os relatos.');continue
            country='Brasil'  # Every selected entity passed the market boundary above.
            if kind=='exchange_sale':
                from app.service_policy import dcc_available
                if not dcc_available():
                    lines.append('A fonte revisada de conversão não está íntegra ou disponível nesta execução; não consigo confirmar essas condições.');continue
                if norm(country) not in ('brasil','brazil','br'):
                    lines.append(f'A fonte disponível descreve a conversão de venda Getnet no Brasil. Não tenho fonte pertinente para confirmar que a mesma regra se aplica em {country}; não vou transferir condições brasileiras para esse mercado.');sources.append(DCC_SOURCE)
                else:
                    text,src,tr=self._core('Como funciona o DCC em uma venda Getnet no Brasil?',principal);lines.append(text);sources+=src;traces+=tr
                continue
            if topic=='connectivity' and refs and kind in ('next_step','information'):
                for ref in refs:
                    text,src=self._wifi(state,ref)
                    label=state['devices'][ref]['label']
                    generic=re.fullmatch(r'(?:(?:minha|meu|a|o)\s+)?(?:maquininha|terminal|aparelho)(?:\s+getnet)?',norm(label).strip())
                    prefix='' if len(state['devices'])==1 and generic else label+': '
                    lines.append(prefix+text);sources+=src
                continue
            queries={'commercial':task['quote'], 'advance':'Como funciona antecipação de vendas Getnet?', 'settlement':'Quando recebo vendas de ontem?' if re.search(r'ontem|yesterday',norm(task['quote'])) else 'Meu saldo', 'pix_account':'Preciso de conta bancária para receber vendas via Pix?', 'link':'Posso vender via WhatsApp com Link de Pagamento?', 'link_fee':'Qual a taxa do Link de Pagamento?', 'migration':'Minha conta já foi migrada?', 'installments':'Em quantas parcelas posso vender no crediário?', 'comparison':'Qual a diferença entre Get Clássica e Get Smart? Wi-Fi da Clássica', 'connectivity':'Como configurar Wi-Fi na maquininha Getnet?'}
            query=queries.get(topic,task['quote'])
            # Preserve the requested attribute/period when the current question is self-contained.
            from app.request_plan import project_topic
            projected=project_topic(task['quote'],topic)
            if projected:query=projected
            if topic=='decline':
                modality='Pix' if task.get('subject')=='pix' else 'cartão'
                query=f'Meu pagamento com {modality} foi recusado na maquininha'
                for ref in refs:
                    f=self._fact(state,ref,'error_code',task.get('subject','device'))
                    if f is None and not any(x['entity']==ref and x['field']=='error_code' and x.get('subject','device')!='device' for x in state['facts'].values()):f=self._fact(state,ref,'error_code')
                    if f and f['status'] in ('asserted','corrected'):query+=' código '+f['value']
            if topic=='settlement' and re.fullmatch(r'(?:hoje|ontem|today|yesterday|\d{4}-\d{2}-\d{2})[.!?]?',norm(task['quote']).strip()):
                query='Consulte minhas vendas de '+task['quote']
            if norm(country) not in ('brasil','brazil','br'):
                query+=' no '+country
            text,src,tr=self._core(query,principal);lines.append(text);sources+=src;traces+=tr
            if norm(country) not in ('brasil','brazil','br') and not src:
                lines.append(f'Não confirmei uma orientação aplicável a {country}. Conteúdo brasileiro não comprova procedimentos, taxas ou condições desse mercado; preciso de uma fonte pertinente ao país para confirmar.')
        if state['pending']:
            if state['focus']:lines.append(summary(state,state['focus']))
            fields=list(dict.fromkeys(x['observation']['field'] for x in state['pending']))
            from app.context_state import LABELS
            if any(x['reason']=='retraction_target_ambiguous' for x in state['pending']):
                lines.append('A retirada ficou pendente: você está retirando o relato anterior ou a informação que acabou de dar? Não usarei a confirmação em disputa enquanto isso.')
            if any(x['reason']=='entity_ambiguous' for x in state['pending']) and not (sources and not state['devices']):
                lines.append('Mantive sem atribuir a aparelho: '+', '.join(LABELS[x] for x in fields)+'. A qual aparelho se refere essa informação?')
        return compose_notices(*dict.fromkeys(lines)),list(dict.fromkeys(sources)),traces
    def step(self,principal,session,message,documents=(),*,today=None,proposal=None):
        start=time.perf_counter();version,before=self.store.read(principal,session)
        original_before=deepcopy(before)
        safe,redacted=clean_message(message)
        from app.service_policy import service_plan
        from app.brazil_scope import scoped_parts, market_of, remember_boundary
        policy=service_plan(safe,state=before)
        restricted=before
        for part,_ in scoped_parts(safe,state=before):
            market=market_of(part)
            if market.value!='NONE':restricted=remember_boundary(restricted,part,market.value,allow_global=not bool(policy.message) or not policy.replies)
        if not policy.message:
            self.store.commit(principal,session,version,restricted)
            answer=compose_notices(*(p for r in policy.replies for p in response_parts(r)),credentials=redacted)
            return {'answer':DISCLOSURE+'\n\n'+answer,'sources':list(dict.fromkeys(source for r in policy.replies for source in r.fontes)), 'mode':'scope_policy',
                    'state':restricted,'validation':{},'traces':[],'seconds':time.perf_counter()-start,
                    'documents_received':len(documents),'external_documents_actionable':False}
        safe=policy.message
        before=restricted
        # Attachments never enter interpreter or memory. Only server-reviewed evidence serves answers.
        try:
            if proposal is None:
                if self.interpreter is None:raise RuntimeError('No semantic interpreter configured')
                proposal=self.interpreter.interpret(safe,before,str(today or simulation_date()))
            after,validation=apply_turn(before,proposal,safe,review=getattr(self.interpreter,'last_review',None) if self.interpreter else None)
            answer,sources,traces=self._plan(after,safe,principal)
            # A intenção é memória útil; texto de comando do turno não é memória futura.
            after['requests']=[{**task,'quote':''} for task in after['requests']]
            self.store.commit(principal,session,version,after)
            corrections=[e for e in after['events'][len(before['events']):] if e['kind']=='device' and e['data'].get('before')]
            if corrections:answer=compose_notices('Vínculos corrigidos: '+', '.join(e['data']['after']['label']+' — '+e['data']['after']['store'] for e in corrections)+'.',answer)
            changed_certainty=[e for e in after['events'][len(before['events']):] if e['kind']=='uncertain' or (e['kind']=='fact' and e['data'].get('before') and e['data']['after']['status'] in ('unknown','uncertain','retracted'))]
            if changed_certainty:
                updates=[]
                for event in changed_certainty:
                    previous=event['data'].get('before') or {};current=event['data']['after']
                    confirmed=previous.get('origin')=='customer' and previous.get('status') in ('asserted','corrected') and previous.get('value') not in ('unknown','unconfirmed')
                    label={'pix':'Pix','card':'cartão','device':'aparelho'}.get(current.get('subject'),'aparelho')
                    updates.append(label+' não confirmado'+('; a confirmação anterior foi retirada' if confirmed else '; permaneceu sem confirmação direta'))
                answer=compose_notices('Atualizei a certeza dos relatos: '+', '.join(dict.fromkeys(updates))+'. Os demais relatos permanecem conforme registrados.',answer)
            mode='semantic_interpretation_reviewed_response'
        except (PermissionError,Conflict):raise
        except Exception as exc:
            # Preserve state; answer self-contained public questions from the existing core.
            fallback=safe
            # A source/model failure never resets the previous market to Brazil.
            from app.rag.scope import FOREIGN
            explicit_country=bool(set(re.findall(r'\w+',norm(safe))) & (FOREIGN | {'brasil','brazil'}))
            if not explicit_country:
                countries=[]
                for ref in before.get('focus',[]):
                    fact=self._fact(before,ref,'country') or before.get('context',{}).get('country')
                    if fact:countries.append(fact)
                if not countries and before.get('context',{}).get('country'):countries=[before['context']['country']]
                if countries:
                    confirmed={f['value'] for f in countries if f['origin']=='customer' and f['status'] in ('asserted','corrected')}
                    if len(confirmed)==1 and all(f['origin']=='customer' and f['status'] in ('asserted','corrected') for f in countries) and len({f['value'] for f in countries})==1:
                        fallback+=' no '+next(iter(confirmed))
                    else:fallback=None
            if fallback is None:
                answer='O país aplicável ficou sem confirmação. Em qual país está o aparelho ou serviço?';sources=[];traces=[]
            else:answer,sources,traces=self._core(fallback,principal)
            after=before;validation={'error':type(exc).__name__};mode='fallback_extractive'
            if after!=original_before:self.store.commit(principal,session,version,after)
            answer=compose_notices('Não consegui atualizar o contexto nesta tentativa.',answer)
        if policy.replies:
            answer=compose_notices(answer,*(p for r in policy.replies for p in response_parts(r)))
            sources=list(dict.fromkeys(sources+[source for r in policy.replies for source in r.fontes]))
        credential=redacted or bool(re.search(r'senha|password|autenticacao|otp|codigo sms',norm(message)))
        answer=compose_notices(answer,credentials=credential)
        return {'answer':DISCLOSURE+'\n\n'+answer,'sources':sources,'mode':mode,'state':after,'validation':validation,'traces':traces,'seconds':time.perf_counter()-start,'documents_received':len(documents),'external_documents_actionable':False}
