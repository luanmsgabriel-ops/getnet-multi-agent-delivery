"""Dados por entidade/incidente: dependências locais e pendências não acionáveis."""
from copy import deepcopy
from datetime import datetime,timezone
from hashlib import sha256
import re,unicodedata,json
from uuid import uuid4
from app.context_contract import Turn
from app.context_proof import evidence_guard,identity_guard

def norm(s):return ''.join(c for c in unicodedata.normalize('NFKD',str(s).lower()) if not unicodedata.combining(c))
PROPERTY={'product','country','connection'}
BOOLEAN={'restart_attempted','network_menu_open','credential_correct','network_ok','network_selected','password_entered_on_device','connected','resolved','printing_ok'}
LABELS={'restart_attempted':'reinício tentado','network_menu_open':'menu Wi-Fi aberto','credential_correct':'credencial correta (sem guardar valor)','product':'modelo','country':'país','connection':'meio de conexão','symptom':'relato','error_code':'código técnico','network_ok':'rede funcionando','network_selected':'rede selecionada','password_entered_on_device':'senha digitada no aparelho','connected':'conectado','resolved':'resolvido','attempt':'tentativa','printing_ok':'impressão funcionando','payment_status':'estado do pagamento','modality':'modalidade','date':'data'}
# Conteúdo tem tipo/origem limitado e nunca controla o servidor. Detector é defesa adicional.
CONTROL=re.compile(r'ignore.{0,50}(?:instru|regr|restr)|(?:system|developer)\s*[:>]|(?:grave|marque|registre).{0,45}(?:resolvid|autenticad)|\.env|https?://|(?:envie|peca|solicite|compartilhe).{0,35}(?:senha|token|otp)',re.I)
from app.privacy import clean_message

def valid_literal(value,quote):
    if not value or norm(value) in norm(quote):return True
    # A compact display value may omit function words, but not invent substantive words.
    wanted=re.findall(r'[a-z0-9]+',norm(value));words=iter(re.findall(r'[a-z0-9]+',norm(quote)))
    return bool(wanted) and all(any(t==w for t in words) for w in wanted)

def names_in(quote,devices):
    text=norm(quote);found=[]
    for ref,d in devices.items():
        label=norm(d['label'])
        if label in text:found.append(ref)
    return found

def apply_turn(old,proposal,message,now=None,review=None):
    p=Turn.model_validate(proposal);state=deepcopy(old);events=[];rejected=[]
    stamp=now or datetime.now(timezone.utc).isoformat()
    digest=sha256(message.encode('utf-8')).hexdigest()
    if review and (review['message_sha256']!=digest or review['proposal_sha256']!=sha256(p.model_dump_json().encode()).hexdigest()):raise ValueError('Review does not match immutable proposal')
    def proof(quote):
        if quote not in message:raise ValueError('quote_not_exact')
        if clean_message(quote)[1]:raise ValueError('credential_in_evidence')
        return {'quote':quote,'message_sha256':digest,'at':stamp}
    def record(kind,data):events.append({'kind':kind,'data':data,'at':stamp})
    blocked=set();claims_this_turn={}
    for di,d in enumerate(p.devices):
        semantic=review if review and review['devices'][di].get('basis')!='local_constraints' else None
        try:
            ev=proof(d.quote)
            if CONTROL.search(norm(d.quote)):raise ValueError('unsafe_identity_evidence')
            if semantic:
                if review['devices'][di]['verdict']!='supported':raise ValueError('semantic_identity_not_supported')
            else:identity_guard(d.quote)
            existing=state['devices'].get(d.ref)
            if CONTROL.search(norm(d.label+' '+d.store)):raise ValueError('unsafe_identity')
            if not existing:
                if not semantic and (not valid_literal(d.label,d.quote) or not valid_literal(d.store,d.quote)):raise ValueError('identity_not_literal')
                if semantic and (not set(re.findall(r'[a-z0-9]+',norm(d.label+' '+d.store))) <= set(re.findall(r'[a-z0-9]+',norm(message)))):raise ValueError('identity_words_not_in_message')
            elif d.store!=existing['store'] and not valid_literal(d.store,d.quote):raise ValueError('relation_not_literal')
            if existing and norm(existing['label'])!=norm(d.label):raise ValueError('identity_immutable')
            duplicate=[k for k,v in state['devices'].items() if k!=d.ref and norm(v['label'])==norm(d.label) and norm(v['store'])==norm(d.store)]
            if duplicate:raise ValueError('duplicate_identity')
            if not semantic and existing and d.store!=existing['store'] and not re.search(r'corrig|na verdade|troquei|enganei',norm(message)):raise ValueError('relation_needs_correction')
            state['devices'][d.ref]={'label':d.label,'store':d.store,'evidence':ev}
            if existing!=state['devices'][d.ref]:record('device',{'ref':d.ref,'before':existing,'after':state['devices'][d.ref]})
        except ValueError as exc:
            blocked.add(d.ref);rejected.append({'component':'device','index':di,'ref':d.ref,'reason':str(exc)})
    for n,o in enumerate(p.observations):
        semantic=review if review and review['observations'][n].get('basis')!='local_constraints' else None
        try:
            ev=proof(o.quote)
            if semantic:
                decision=review['observations'][n]
                if decision['verdict']=='unsupported':raise ValueError('semantic_observation_not_supported')
                if decision['verdict']=='uncertain' or decision['origin']!=o.origin:o=o.model_copy(update={'status':'uncertain','origin':decision['origin']})
            else:evidence_guard(o)
            if semantic:
                try:evidence_guard(o)
                except ValueError as exc:
                    # A revisão pode reconhecer paráfrases; não pode apagar contradição/origem explícita.
                    if str(exc)!='field_not_evidenced' and not (o.field in BOOLEAN and o.value in ('false','unknown')):raise
            if CONTROL.search(norm(o.value)) or clean_message(o.value)[1] or CONTROL.search(norm(o.quote)):raise ValueError('unsafe_observation')
            if o.entity in blocked:raise ValueError('dependency_rejected')
            if o.field in BOOLEAN:
                if o.value not in ('true','false','unknown'):raise ValueError('boolean_domain')
            elif o.field=='payment_status':
                if o.value not in ('approved','declined','unconfirmed'):raise ValueError('payment_state_domain')
            elif not valid_literal(o.value,o.quote):raise ValueError('value_not_literal')
            if o.field=='error_code' and not re.fullmatch(r'[A-Za-z0-9 -]{1,16}',o.value):raise ValueError('technical_code_domain')
            item=o.model_dump();item['evidence']=ev
            item['assertion_id']='claim_'+uuid4().hex
            if o.scope=='conversation':
                if o.field!='country':raise ValueError('conversation_field_forbidden')
                if o.origin!='customer':
                    state['observations'].append(item);record('context_observation',item)
                else:
                    state.setdefault('context',{})['country']=item;record('context',item)
                continue
            if o.entity is None and o.field=='date' and any(t.topic=='settlement' and not t.entities and (o.quote in t.quote or t.quote in o.quote) for t in p.requests):
                # Query date is retained as evidence, never an ambiguous device fact.
                item.update(role='query_parameter',actionable=False)
                state['observations'].append(item);record('query_parameter',item);continue
            if o.entity is None:
                pid='p_'+digest[:10]+'_'+str(n)
                state['pending'].append({'id':pid,'observation':item,'reason':'entity_ambiguous','actionable':False})
                record('pending',{'id':pid});continue
            if o.entity not in state['devices']:raise ValueError('unknown_entity')
            named=names_in(o.quote,state['devices'])
            if len(named)==1 and named[0]!=o.entity:raise ValueError('different_named_subject')
            if not semantic and not named and len(state['devices'])>1 and o.entity not in old.get('focus',[]) and not any(x.ref==o.entity for x in p.devices):raise ValueError('unproven_subject')
            active_key=o.entity+'|'+o.subject
            incident='' if o.field in PROPERTY else o.incident or state.get('active_incidents',{}).get(active_key) or (state.get('active_incidents',{}).get(o.entity) if o.subject=='device' else None) or 'episode1'
            if o.field not in PROPERTY and not incident:raise ValueError('incident_required')
            # Field and modality belong to an incident, never a global device slot.
            key='|'.join((o.entity,incident,o.field)) if o.subject=='device' else '|'.join((o.entity,incident,o.subject,o.field))
            prior=state['facts'].get(key)
            item['incident']=incident
            if o.status=='retracted' and o.origin!='customer':
                state['observations'].append(item);record('context_observation',item);continue
            if o.status=='retracted':
                # Explicit version binding, not equality of values, determines the withdrawn claim.
                target=o.retracts
                committed=old['facts'].get(key)
                current=state['facts'].get(key)
                if target is None and current==committed and committed is not None:
                    target=committed.get('assertion_id') or 'legacy_previous'
                if target and target.startswith('turn:'):
                    try:target_index=int(target.split(':')[1])
                    except ValueError:raise ValueError('retraction_target_invalid')
                    bound=claims_this_turn.get(target_index)
                    if bound is None or bound[0]!=key:raise ValueError('retraction_target_dependency')
                    target=bound[1]
                prior_id=(committed or {}).get('assertion_id') or ('legacy_previous' if committed else None)
                current_id=(current or {}).get('assertion_id') or ('legacy_previous' if current else None)
                if target is None and committed is None and current is None:
                    # A withdrawn historical claim never stored here needs no target clarification.
                    state['observations'].append(item);record('historical_retraction',item);continue
                if target is None:
                    if current:
                        state['facts'][key]={**current,'status':'uncertain'}
                    pid='p_'+digest[:10]+'_'+str(n)
                    state['pending'].append({'id':pid,'observation':item,'reason':'retraction_target_ambiguous','actionable':False})
                    record('pending',{'id':pid});continue
                if target not in (prior_id,current_id):raise ValueError('retraction_target_mismatch')
                if target==prior_id and current_id!=prior_id:
                    state['observations'].append(item);record('historical_retraction',item);continue
                # This update withdraws only the exact target version of the same claim slot.
                item['retracts']=target
            if incident and o.origin=='customer' and o.status in ('asserted','corrected','false'):
                state.setdefault('active_incidents',{})[active_key]=incident
                if o.subject=='device':state['active_incidents'][o.entity]=incident
            actionable=o.origin=='customer' and o.status in ('asserted','corrected','false')
            if o.origin!='customer' or o.status=='uncertain':
                state['observations'].append(item)
                # A correction explicitly withdrawing a prior direct observation cannot leave it confirmed.
                if prior and (o.field=='payment_status' or o.status=='corrected' or re.search(r'corrig|nao vi|nao confirmei|so ouvi',norm(o.quote))):
                    state['facts'][key]={**item,'status':'uncertain'};record('uncertain',{'key':key,'before':prior,'after':item})
            else:
                claims_this_turn[n]=(key,item['assertion_id'])
                state['facts'][key]=item;record('fact',{'key':key,'before':prior,'after':item})
        except ValueError as exc:
            reason=str(exc)
            # Rejected new category must not leave a contradicted older value actionable.
            # Scope invalidation to the already resolved subject; never erase other devices.
            if reason in ('categorical_polarity_not_evidenced','categorical_value_not_evidenced') and o.origin=='customer' and o.entity in state['devices'] and o.entity not in blocked:
                named=names_in(o.quote,state['devices'])
                bound=(len(named)==1 and named[0]==o.entity) or (not named and (len(state['devices'])==1 or old.get('focus')==[o.entity]))
                if bound and o.quote in message and not CONTROL.search(norm(o.quote)):
                    key='|'.join((o.entity,'',o.field));prior=state['facts'].get(key)
                    if prior and norm(prior['value'])==norm(o.value):
                        item={**prior,'status':'uncertain','evidence':proof(o.quote)}
                        state['facts'][key]=item;record('uncertain',{'key':key,'before':prior,'after':item})
                    from app.context_proof import explicit_categorical
                    direct=explicit_categorical(message,o.field)
                    if direct:
                        value,quote=direct
                        recovery=o.model_copy(update={'value':value,'quote':quote,'status':'corrected'})
                        try:
                            evidence_guard(recovery)
                            item=recovery.model_dump();item.update(evidence=proof(quote),assertion_id='claim_'+uuid4().hex,incident='')
                            state['facts'][key]=item;record('fact',{'key':key,'before':prior,'after':item})
                        except ValueError:pass
                    elif prior is None:
                        state['pending'].append({'id':'p_'+digest[:10]+'_'+str(n),'observation':{**o.model_dump(),'status':'uncertain'},'reason':'category_ambiguous','actionable':False})
            rejected.append({'component':'observation','index':n,'field':o.field,'entity':o.entity,'reason':reason})
    # Pending cannot be promoted without a newly grounded observation in this transaction.
    for pid in p.resolve_pending:
        pending=next((x for x in state['pending'] if x['id']==pid),None)
        if pending and pending.get('reason')=='retraction_target_ambiguous':
            if not any(x.get('field')==pending['observation']['field'] for x in rejected) and any((e['kind']=='fact' and e['data']['after']['status']=='retracted' and e['data']['after']['field']==pending['observation']['field'] and e['data']['after']['entity']==pending['observation']['entity']) or (e['kind']=='historical_retraction' and e['data']['field']==pending['observation']['field'] and e['data']['entity']==pending['observation']['entity']) for e in events):
                state['pending']=[x for x in state['pending'] if x['id']!=pid];record('pending_resolved',{'id':pid})
            continue
        if pending and not any(x.get('field')==pending['observation']['field'] for x in rejected) and any(e['kind']=='fact' and e['data']['after']['field']==pending['observation']['field'] and e['data']['after'].get('subject','device')==pending['observation'].get('subject','device') and e['data']['after']['status'] in ('asserted','corrected') and e['data']['after']['origin']=='customer' and ((pending['observation']['field'] in BOOLEAN and (e['data']['after']['value']==pending['observation']['value']=='true' or pending['observation']['value']=='unknown' and e['data']['after']['value'] in ('true','false'))) or (pending['observation']['field'] not in BOOLEAN and any(a[:5]==b[:5] for a in norm(e['data']['after']['value']).split() for b in norm(pending['observation']['value']).split() if len(a)>=5 and len(b)>=5))) for e in events):
            state['pending']=[x for x in state['pending'] if x['id']!=pid];record('pending_resolved',{'id':pid})
    state['requests']=[]
    for request in p.requests:
        try:proof(request.quote)
        except ValueError:
            rejected.append({'component':'request','reason':'quote_not_exact'});continue
        if request.kind in ('information','next_step') and request.topic=='connectivity' and not request.entities and not state['focus']:
            from app.intents import request_facts
            from app.request_plan import dependent_help
            whole=request_facts(message)
            # A short help request can refer to the explicit, single technical
            # problem in the SAME validated message, without assigning an entity.
            same_turn_problem=dependent_help(request.quote) and whole.connectivity and not (whole.decline or whole.comparison or whole.fee or whole.unsupported_action)
            if not request_facts(request.quote).connectivity and not same_turn_problem:
                request=request.model_copy(update={'kind':'clarify','topic':'other'})
        state['requests'].append(request.model_dump())
    goals=state.setdefault('goals',[])
    for task in state['requests']:
        if task['kind'] in ('information','next_step','exchange_sale'):
            goal={k:v for k,v in task.items() if k!='quote'}
            if goal not in goals:goals.append(goal)
    state['goals']=goals[-12:]
    state['focus']=[ref for ref in p.focus if ref in state['devices'] and ref not in blocked]
    # Preserve prior useful target if new request is off-topic or does not identify a new device.
    if not state['focus']:state['focus']=old.get('focus',[])
    state['events']=(state['events']+events)[-256:]
    state['observations']=state['observations'][-64:];state['pending']=state['pending'][-24:]
    return state,{'accepted_events':len(events),'rejected':rejected,'pending':len(state['pending'])}

def display_label(state,ref):
    """O identificador/alias fica estável; o modelo corrigido muda a apresentação."""
    device=state['devices'][ref]
    label=device['label']
    products=[f for f in state['facts'].values() if f['entity']==ref and f['field']=='product' and f['origin']=='customer' and f['status'] in ('asserted','corrected')]
    if not products:return label
    current=products[-1]['value']
    old_values=[]
    for event in state.get('events',[]):
        data=event.get('data',{});old=data.get('before')
        if isinstance(old,dict) and old.get('entity')==ref and old.get('field')=='product':old_values.append(old['value'])
    if not old_values:
        old_values=re.findall(r'(?<!\w)(?:[a-z]+[0-9]+[a-z0-9-]*|Smart|Clássica)(?!\w)',label,flags=re.I)
    for old in old_values:
        label=re.sub(r'(?<!\w)'+re.escape(old)+r'(?!\w)',lambda _:current,label,flags=re.I)
    return label


def summary(state,refs):
    result=[]
    for ref in refs:
        d=state['devices'].get(ref)
        if not d:continue
        pieces=[]
        for key,f in state['facts'].items():
            if f['entity']!=ref:continue
            value={'true':'sim','false':'não','unknown':'desconhecido','approved':'aprovação relatada','declined':'recusado','unconfirmed':'não confirmado'}.get(f['value'],f['value'])
            status={'asserted':'relatado','corrected':'corrigido','false':'negado','unknown':'desconhecido','approved':'aprovação relatada','declined':'recusado','unconfirmed':'não confirmado','uncertain':'não confirmado','retracted':'retirado'}[f['status']]
            subject_label={'card':'cartão ','pix':'Pix '}.get(f.get('subject'),'')
            pieces.append(f"{subject_label}{LABELS[f['field']]}: {value} ({status}; origem {f['origin']})")
        for f in state['observations']:
            if f['entity']==ref:
                # Texto documental não é uma instrução do atendimento, nem mesmo no fallback.
                value=f['value'] if f['origin']!='quoted' and not CONTROL.search(norm(f['value'])) else 'conteúdo citado, não adotado como fato ou instrução'
                value={'true':'sim','false':'não','unknown':'desconhecido'}.get(value,value)
                current=[x for x in state['facts'].values() if x['entity']==ref and x['field']==f['field'] and x.get('subject','device')==f.get('subject','device') and x.get('incident')==f.get('incident') and x['origin']=='customer' and x['status'] in ('asserted','corrected','false') and f['field'] in BOOLEAN|PROPERTY|{'payment_status','error_code'} and x.get('evidence',{}).get('at','')>f.get('evidence',{}).get('at','')]
                historical='histórico, não é o estado atual; ' if current else ''
                pieces.append(f"{LABELS[f['field']]}: {value} ({historical}não confirmado; origem {f['origin']})")
        for event in state['events']:
            data=event.get('data',{});previous=data.get('before');current=data.get('after')
            if isinstance(previous,dict) and isinstance(current,dict) and previous.get('entity')==ref and current.get('status') in ('retracted','unknown','uncertain') and previous.get('status') in ('asserted','corrected'):
                modality={'pix':'Pix','card':'cartão'}.get(previous.get('subject'),'aparelho')
                value={'approved':'aprovação','declined':'recusa','true':'sim','false':'não'}.get(previous.get('value'),'estado anterior')
                reason=current.get('evidence',{}).get('quote','')
                reason=(' Motivo relatado: '+reason) if reason and not CONTROL.search(norm(reason)) and not clean_message(reason)[1] else ''
                pieces.append(f"relato anterior de {value} ({modality}) retirado como confirmação; origem anterior {previous.get('origin')}."+reason)
        result.append(f"{display_label(state,ref)} — {d['store'] or 'loja não informada'}: "+('; '.join(dict.fromkeys(pieces)) or 'sem observações confirmadas')+'.')
    return '\n'.join(result)
