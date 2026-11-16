"""Bounded conversational records, not facts, permissions or a cache of live data."""
import hashlib,json
from datetime import datetime,timezone
from uuid import uuid4
from app.privacy import clean_message

RECENT_TURNS=4
PENDING_TURNS=2
MAX_BYTES=16000
_FIELDS={'request','currency_pair','date','location','terminal','terminal_error','connectivity','market'}
_STATUSES={'answered','partial','missing','unavailable','pending'}

def _text(value,limit):
    return clean_message(value)[0][:limit] if isinstance(value,str) else ''

def normalize_history(rows):
    """One closed projection is used for storage, prompt and goal anchoring."""
    normalized=[]
    for index,row in enumerate(rows if isinstance(rows,list) else list(rows)):
        if not isinstance(row,dict):continue
        request=_text(row.get('request'),4000)
        if not request:continue
        tid=row.get('turn_id','')
        if not isinstance(tid,str) or not __import__('re').fullmatch(r't_[a-f0-9]{16,32}',tid):
            tid='t_'+hashlib.sha256((str(index)+'|'+request).encode()).hexdigest()[:16]
        item={'turn_id':tid,'request':request,'origin':'user_report',
              'clarification':row.get('clarification') if row.get('clarification') in _FIELDS else None}
        outcome=row.get('outcome')
        if isinstance(outcome,dict):
            goals=[]
            for g in outcome.get('goals',[])[:4]:
                if isinstance(g,dict) and g.get('status') in _STATUSES:
                    goals.append({'goal_id':_text(g.get('goal_id'),80),'request':_text(g.get('request'),1000),'status':g['status']})
            status=outcome.get('status')
            item['outcome']={'status':status if status in _STATUSES else 'unavailable',
                'answer_excerpt':_text(outcome.get('answer_excerpt'),1200),
                'excerpt_only':True,'historical_only':True,'current_evidence':False,
                'origin':'assistant_output','request_id':_text(outcome.get('request_id'),80),
                'sources':[_text(v,500) for v in outcome.get('sources',[])[:3] if isinstance(v,str) and v.startswith('https://') and '?' not in v and '#' not in v],
                'observation_refs':[_text(v,80) for v in outcome.get('observation_refs',[])[:6]],
                'clarification_goal_id':_text(outcome.get('clarification_goal_id'),80),
                'goals':goals,'observed_at':_text(outcome.get('observed_at'),40)}
        normalized=[n for n in normalized if n['turn_id']!=tid]+[item]
    normalized=normalized[-(RECENT_TURNS+PENDING_TURNS):]
    while normalized and len(json.dumps(normalized,ensure_ascii=False).encode('utf-8'))>MAX_BYTES:
        normalized.pop(0)
    return normalized

def history_for(state):
    return normalize_history([*state.get('supervisor_pending',[]),*state.get('supervisor_dialogue',[])])

def quote_coverage(goals,history,current):
    """Every goal must overlap the current request, not revive an old request.
    Optional turn binding resolves duplicate historical wording explicitly.
    """
    current=' '.join(current.split());rows=normalize_history(history)
    candidates=[(None,'')]+[(h['turn_id'],' '.join(h['request'].split())+' ') for h in rows]
    covered=[False]*len(current);bound=[]
    for goal in goals:
        # An interpretation is not an executable request. Explicit current anchors
        # let the model resolve references without inventing/omitting instructions.
        # Reconstruct ONLY from authenticated historical input + entire current input.
        anchor=getattr(goal,'current_request_quote',None)
        if anchor is not None:
            if not goal.context_turn_id or ' '.join(anchor.split())!=current:
                raise ValueError('Invalid current request anchor')
            selected=[row for row in rows if row['turn_id']==goal.context_turn_id]
            if len(selected)!=1:raise ValueError('Unknown historical anchor')
            canonical=' '.join(selected[0]['request'].split())+' '+current
            if len(canonical)>1000:raise ValueError('Anchored request exceeds limit')
            goal=goal.model_copy(update={'request':canonical,'current_request_quote':None})
        quote=' '.join(goal.request.split());matches=[]
        for tid,prefix in candidates:
            if goal.context_turn_id and tid!=goal.context_turn_id:continue
            available=prefix+current
            import re
            for match in re.finditer(re.escape(quote),available,re.IGNORECASE) if quote else ():
                # Permit case alone, restore original text; no synonyms or accents.
                if match.group().casefold()!=quote.casefold():continue
                start=match.start()
                lo=max(start,len(prefix));hi=min(start+len(quote),len(available))
                if hi>lo:
                    overlap=available[lo:hi]
                    if any(w.casefold() not in {'e','and','por','favor','please'} for w in __import__('re').findall(r'\w+',overlap)):
                        matches.append((tid if start<len(prefix) else None,lo-len(prefix),hi-len(prefix),match.group()))
        if not matches:raise ValueError('Goal does not represent current request')
        # A current-only literal never needs a historical interpretation.
        if any(t is None for t,_,_,_ in matches):matches=[m for m in matches if m[0] is None]
        ids={t for t,_,_,_ in matches}
        if len(ids)>1:raise ValueError('Ambiguous historical reference')
        tid=next(iter(ids))
        for _,lo,hi,_ in matches:covered[lo:hi]=[True]*(hi-lo)
        bound.append(goal.model_copy(update={'context_turn_id':tid,'request':matches[0][3]}))
    return current,covered,bound

def record_turn(state,request,result):
    info=result.agentic
    coverage={c.goal_id:c.status for c in info.coverage}
    tid='t_'+uuid4().hex
    goals=[{'goal_id':tid+'/'+g.id,'request':g.request,'status':coverage.get(g.id,'unavailable')} for g in info.goals]
    statuses=[g['status'] for g in goals]
    status=('pending' if info.stop=='clarify' else 'answered' if statuses and all(s=='answered' for s in statuses)
            else 'partial' if 'partial' in statuses or 'answered' in statuses else 'unavailable')
    # Refused hostile text is not retained to be reintroduced on a later turn.
    request='[Pedido não retido por segurança.]' if info.stop=='input_policy' else request
    row={'turn_id':tid,'request':request,'clarification':info.clarification,
         'outcome':{'status':status,'answer_excerpt':result.answer,'goals':goals,
                    'request_id':result.request_id,'sources':result.sources,
                    'observation_refs':[tid+'/'+ev.observation_id for ev in info.trace if ev.observation_id],
                    'clarification_goal_id':tid+'/'+info.clarification_goal_id if info.clarification_goal_id else '',
                    'observed_at':datetime.now(timezone.utc).isoformat()}}
    row=normalize_history([row])[0]
    existing=normalize_history(state.get('supervisor_dialogue',[]))
    recent=normalize_history([*existing,row])[-RECENT_TURNS:]
    answered=[g for g in info.goals if coverage.get(g.id)=='answered']
    def resolved(p):
        unfinished=[g['request'] for g in p.get('outcome',{}).get('goals',[]) if g['status']!='answered'] or [p['request']]
        linked=[g.request for g in answered if g.context_turn_id==p['turn_id']]
        return bool(linked) and all(any(q in answer for answer in linked) for q in unfinished)
    pending=[p for p in normalize_history(state.get('supervisor_pending',[])) if not resolved(p)]
    if status!='answered' and info.stop!='input_policy':pending.append(row)
    pending=normalize_history(pending)[-PENDING_TURNS:]
    combined=normalize_history([*pending,*recent]);kept={x['turn_id'] for x in combined}
    recent=[x for x in recent if x['turn_id'] in kept];pending=[x for x in pending if x['turn_id'] in kept]
    return {**state,'supervisor_dialogue':recent,'supervisor_pending':pending,
            'memory_window':{'schema':1,'recent_limit':RECENT_TURNS,'pending_limit':PENDING_TURNS,
               'max_bytes':MAX_BYTES,'bounded':True,'historical_results_are_current':False,
               'retained_turns':len(combined)}}
