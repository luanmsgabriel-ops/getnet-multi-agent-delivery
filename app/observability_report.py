"""Bounded offline aggregation of sanitized operational JSONL, never semantic scoring."""
import json
import math
import re
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

MAX_FILE_BYTES = 20_000_000
MAX_RECORD_BYTES = 4096
MAX_RECORDS = 100_000
from .observability import EVENTS, STAGES, OUTCOMES, ROUTES as _ROUTES
ROUTES = _ROUTES | {"other"}
STOP_REASONS = frozenset(('deadline','step_limit','tool_limit','model_timeout','model_or_decision_unavailable','lookup_plan_unavailable','finish','limit','clarify','input_policy','no_progress','no_new_evidence'))
COMMON = {'schema_version','event','request_id','duration_ms'}
HTTP = COMMON | {'route','method','http_status','termination'}
STAGE = COMMON | {'stage','outcome','count','cost_usd','cost_state','mode'}
PROVIDER_ERROR = STAGE | {'http_status'}

def _number(value, maximum):
    return type(value) in (int,float) and math.isfinite(value) and 0 <= value <= maximum

def valid_record(r):
    if not isinstance(r,dict) or type(r.get('schema_version')) is not int or r['schema_version'] != 1:
        return False
    rid = r.get('request_id')
    if rid is not None and (not isinstance(rid,str) or not re.fullmatch('[a-f0-9]{32}',rid)):
        return False
    if not _number(r.get('duration_ms'),86_400_000):return False
    event = r.get('event')
    if event == 'http_request':
        return (set(r)==HTTP and rid is not None and r['route'] in ROUTES
                and r['method'] in ('GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS','other')
                and (r['http_status'] is None or type(r['http_status']) is int and 100<=r['http_status']<=599)
                and r['termination'] in ('completed','disconnected','incomplete','cancelled','error'))
    if not isinstance(event,str) or event not in EVENTS:return False
    if event == 'provider_http_error':
        if (set(r)!=PROVIDER_ERROR or r.get('stage')!='model' or r.get('mode') is None
            or type(r.get('http_status')) is not int
            or not 100<=r['http_status']<=599 or r['http_status']==200):return False
    elif set(r)!=STAGE:return False
    return (r['mode'] in (None,'controlled','remote')
            and (event not in ('model_call','budget_reservation','budget_reconciliation') or r['mode'] is not None)
            and (r['cost_state'] not in (None,'unknown') or r['cost_usd'] is None)
            and r['stage'] in STAGES and r['outcome'] in OUTCOMES
            and (r['count'] is None or type(r['count']) is int and 0<=r['count']<=1_000_000)
            and (r['cost_usd'] is None or _number(r['cost_usd'],1_000_000))
            and r['cost_state'] in (None,'confirmed','reserved','unknown')
            and (r['cost_state'] not in ('confirmed','reserved') or r['cost_usd'] is not None))

def _pairs(items):
    result={}
    for key,value in items:
        if key in result:raise ValueError('Duplicate JSON key')
        result[key]=value
    return result

def _latency(values):
    values=sorted(values);n=len(values)
    return {'n':n,'p50_ms':values[math.ceil(.50*n)-1] if n else None,
            'p95_ms':values[math.ceil(.95*n)-1] if n else None,'method':'nearest_rank'}

def aggregate_file(path):
    """Read one regular JSONL file. No raw input, correlation IDs or paths in output.

    A complete file does not prove a complete capture. Producer loss is unknown.
    Repeated stage records are retained: without event IDs deduplication is unsafe.
    """
    path=Path(path)
    if not path.is_file() or path.stat().st_size>MAX_FILE_BYTES:raise ValueError('Input unavailable or over limit')
    counts=Counter();http=Counter();provider_http=Counter();functional=Counter();stages=Counter();outcomes=Counter();terminations=Counter()
    functional_by_stage=defaultdict(Counter);tool_by_stage=defaultdict(Counter);stops=Counter()
    durations=defaultdict(list);costs=defaultdict(Counter);confirmed=defaultdict(lambda:Decimal(0));reserved=defaultdict(lambda:Decimal(0))
    seen_http=set();seen_ids=set();http_ids=set();lines=invalid=truncated=oversized=duplicates=consumed=uncorrelated=0;bounded=False
    with path.open('rb') as stream:
        while True:
            raw=stream.readline(MAX_RECORD_BYTES+1)
            if not raw:break
            consumed+=len(raw)
            if consumed>MAX_FILE_BYTES:bounded=True;break
            lines+=1
            if lines>MAX_RECORDS:bounded=True;break
            if len(raw)>MAX_RECORD_BYTES:
                oversized+=1
                while raw and not raw.endswith(b'\n'):
                    raw=stream.readline(MAX_RECORD_BYTES+1);consumed+=len(raw)
                    if consumed>MAX_FILE_BYTES:bounded=True;break
                if bounded:break
                continue
            if not raw.endswith(b'\n'):
                truncated+=1;continue
            try:
                r=json.loads(raw.decode('utf-8'),object_pairs_hook=_pairs,parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                if not valid_record(r):raise ValueError()
            except (ValueError,TypeError,KeyError,RecursionError):invalid+=1;continue
            rid=r['request_id'];event=r['event']
            if event=='http_request' and rid in seen_http:
                duplicates+=1;continue
            if rid:seen_ids.add(rid)
            else:uncorrelated+=1
            counts[event]+=1;durations[event].append(r['duration_ms'])
            if event=='http_request':
                seen_http.add(rid);http_ids.add(rid)
                http[str(r['http_status']) if r['http_status'] is not None else 'unknown']+=1
                terminations[r['termination']]+=1
            else:
                if event=='provider_http_error':provider_http[str(r['http_status'])]+=1
                stages[r['stage']]+=1;outcomes[r['outcome']]+=1
                if event=='execution_completed':
                    functional[r['outcome']]+=1
                    functional_by_stage[r['stage']][r['outcome']]+=1
                if event=='stage_result' and r['stage']=='supervisor' and r['outcome'] in STOP_REASONS:
                    stops[r['outcome']]+=1
                if event=='tool_call':
                    tool_by_stage[r['stage']]['records']+=1
                    if r['count'] is None:tool_by_stage[r['stage']]['count_unknown_records']+=1
                    else:tool_by_stage[r['stage']]['reported_attempts']+=r['count']
                mode=r['mode'] or 'unspecified'
                if event in ('model_call','tool_call'):
                    if r['count'] is None:costs[mode][event+'_count_unknown_records']+=1
                    else:costs[mode][event+'_reported_count']+=r['count']
                if event=='budget_reconciliation':
                    if r['cost_state']=='confirmed':confirmed[mode]+=Decimal(str(r['cost_usd']));costs[mode]['confirmed_records']+=1
                    else:costs[mode]['unconfirmed_reconciliation_records']+=1
                elif event=='budget_reservation':
                    if r['cost_state']=='reserved':reserved[mode]+=Decimal(str(r['cost_usd']));costs[mode]['reservation_records']+=1
                    else:costs[mode]['unknown_reservation_records']+=1
    rejected=invalid+truncated+oversized+duplicates
    return {'schema_version':1,'scope':'observed_sanitized_file_only','semantic_quality_measured':False,
        'input_quality':{'lines_seen':min(lines,MAX_RECORDS),'accepted_records':sum(counts.values()),'invalid_records':invalid,
            'truncated_records':truncated,'oversized_records':oversized,'duplicate_http_records':duplicates,
            'bounded_stop':bounded,'incomplete':bool(rejected or bounded or uncorrelated or seen_ids-http_ids or any(k!='completed' and v for k,v in terminations.items())),
            'uncorrelated_records':uncorrelated,'orphan_correlations':len(seen_ids-http_ids),'producer_dropped_records':None,'capture_completeness':'unknown'},
        'http':{'requests':counts['http_request'],'statuses':dict(http),'terminations':dict(terminations)},
        'provider_http_errors':{'records':counts['provider_http_error'],'statuses':dict(provider_http)},
        'functional_outcomes':dict(functional),
        'functional_outcomes_by_stage':{k:dict(v) for k,v in sorted(functional_by_stage.items())},
        'tool_calls_by_stage':{k:dict(v) for k,v in sorted(tool_by_stage.items())},'stop_reasons':dict(stops),'event_counts':dict(counts),'stage_counts':dict(stages),'stage_outcomes':dict(outcomes),
        'latencies':{k:_latency(v) for k,v in sorted(durations.items())},
        'costs':{'by_mode':{mode:{'confirmed_usd':str(confirmed[mode]),'recorded_reserved_usd':str(reserved[mode]),**dict(costs[mode])} for mode in ('controlled','remote','unspecified')},
            'reservation_is_current_balance':False,'complete_billing':False},
        'limitations':['HTTP success is not functional or semantic success.','Repeated stage records cannot be deduplicated without event IDs.',
            'Provider and model IDs are absent; no provider attribution is inferred. Tool categories use closed stage labels; stop reasons use only supervisor stage_result stop outcomes.',
            'Model-call counts indicate transport attempts initiated, not provider receipt or successful completion.',
            'Functional outcomes count component execution_completed records, not one result per HTTP request.',
            'An ok model, rag_plan, rag_draft or rag_verify event means a call returned, not semantic validation.',
            'Confirmed and reserved USD are separate; no credits, attempts or token-based estimates are added.',
            'Missing, rotated or producer-dropped events cannot be reconstructed. No time window is inferred without timestamps.']}
