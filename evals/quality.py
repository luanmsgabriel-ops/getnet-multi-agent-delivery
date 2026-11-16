"""Offline evaluation protocol. Metrics do not certify semantic correctness."""
import hashlib,json,math,re
from collections import Counter,defaultdict
from pathlib import Path

DIMENSIONS=('correctness','relevance','completeness','groundedness','usefulness')
LABELS=('pass','partial','fail','not_assessable')

def digest(value):
 return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def read_json(path):
 p=Path(path)
 if p.stat().st_size>20_000_000:raise ValueError('Evaluation input too large')
 return json.loads(p.read_text('utf-8-sig'))

def write_new(path,value):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 encoded=json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)
 with p.open('x',encoding='utf-8') as f:f.write(encoded)

def catalog(root):
 root=Path(root);data=read_json(root/'evals/cases.json');gold=read_json(root/'evals/oracles.json')
 cases=data.get('cases',[]);oracles=gold.get('oracles',[])
 if data.get('schema_version')!=1 or gold.get('schema_version')!=1:raise ValueError('Unknown dataset version')
 if len(cases)!=40 or Counter(c.get('split') for c in cases)!=Counter(original=10,regression=10,holdout=20):raise ValueError('Expected 10 original, 10 regression, 20 holdout')
 ids=[c.get('id') for c in cases]
 if len(set(ids))!=40 or set(ids)!={f'{p}{n:02d}' for p,count in (('O',10),('R',10),('H',20)) for n in range(1,count+1)}:raise ValueError('Invalid or duplicate case IDs')
 for c in cases:
  if not c.get('tags') or c.get('evaluation_scope') not in ('answer','security','workflow') or not c.get('provenance'):raise ValueError('Missing case provenance')
  if not 1<=len(c.get('turns',[]))<=6:raise ValueError('Invalid turns')
  for t in c['turns']:
   if set(t)!={'action','message'} or t['action'] not in ('chat','reset') or not isinstance(t['message'],str) or not 1<=len(t['message'])<=2000:raise ValueError('Invalid public turn')
   if t['action']=='reset' and t['message']!='reset':raise ValueError('Ambiguous reset')
 if len(oracles)!=40 or {o.get('case_id') for o in oracles}!=set(ids):raise ValueError('Oracle coverage mismatch')
 for o in oracles:
  if not o.get('criteria') or not all(isinstance(x,str) and x for x in o['criteria']):raise ValueError('Missing criteria')
  if not o.get('acceptable_outcomes') or not set(o['acceptable_outcomes'])<={'answer','clarify','refuse','limit'}:raise ValueError('Invalid expected outcome')
  if type(o.get('needs_live_reference')) is not bool:raise ValueError('Missing live-reference annotation')
  supplemental=o.get('supplemental_references',[])
  if not isinstance(supplemental,list):raise ValueError('Invalid supplemental references')
  for g in [*o.get('evidence_groups',[]), *([[r] for r in supplemental])]:
   if not g or any(set(x)!={'source','ordinal'} or not isinstance(x['source'],str) or not x['source'].startswith('https://') or type(x['ordinal']) is not int or x['ordinal']<0 for x in g):raise ValueError('Invalid evidence group')
 return data,gold

def source_references(root,oracle):
 """Resolve annotator-selected references against stored corpus bytes, not model citations."""
 root=Path(root);docs={}
 from app.rag.core import load_snapshot
 from app.rag.fetch import SOURCES
 for path in sorted((root/'corpus_publico').glob('*.json')):
  doc=load_snapshot(path,SOURCES);docs.setdefault(doc['final_url'],[]).append(doc)
 refs=[];seen=set()
 # Supplemental context is available to the blind judge, not an additional
 # required retrieval group or a new answer obligation.
 for group in [*oracle['evidence_groups'], oracle.get('supplemental_references',[])]:
  for ref in group:
   choices=docs.get(ref['source'],[]);ordinal=ref['ordinal']
   matches=[d for d in choices if ordinal<len(d.get('chunks',[])) and d.get('reviewed') is True]
   if not matches:raise ValueError('Annotated reviewed reference missing')
   texts={(d.get('chunk_titles',[d['title']]*len(d['chunks']))[ordinal],d['chunks'][ordinal]) for d in matches}
   if len(texts)!=1:raise ValueError('Ambiguous duplicate reference')
   title,value=texts.pop();eid=hashlib.sha256((ref['source']+'\n'+title+'\n'+str(ordinal)+'\n'+value).encode()).hexdigest()
   if eid not in seen:refs.append({'source':ref['source'],'text':value,'evidence_id':eid});seen.add(eid)
 return refs

def freeze(root):
 root=Path(root);data,gold=catalog(root);files={}
 for folder in ('app','corpus_publico','evals','scripts','tests','docs'):
  for p in sorted((root/folder).rglob('*')):
   if p.is_file() and '__pycache__' not in p.parts and p.suffix in ('.py','.json','.jsonl','.md'):
    files[p.relative_to(root).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
 for p in sorted((root/'.github/workflows').glob('*.yml')):
  files[p.relative_to(root).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
 for name in ('Dockerfile','requirements.txt','requirements-semantic.txt','constraints-tested.txt','README.md','.env.example','.dockerignore','.gitignore'):
  p=root/name;files[name]=hashlib.sha256(p.read_bytes()).hexdigest()
 return {'schema_version':1,'dataset':data,'dataset_hash':digest(data),'oracle_hash':digest(gold),'protocol_hash':hashlib.sha256((root/'evals/protocol.json').read_bytes()).hexdigest(),'manifest_hash':digest(files),'files':files,'case_ids':[c['id'] for c in data['cases']],'case_questions':{c['id']:c['turns'][-1]['message'] for c in data['cases']},'case_annotations':{c['id']:{'split':c['split'],'tags':c['tags']} for c in data['cases']},'planned_cases':40,'planned_replicates':3,'semantic_runs_performed':0,'holdout_policy':'Any case used for correction is a known regression thereafter; exposure must be recorded in result artifacts.'}

def retrieval_metrics(rows,k=3):
 if type(k) is not int or not 1<=k<=20:raise ValueError('Invalid k')
 if len({r['case_id'] for r in rows})!=len(rows):raise ValueError('Duplicate retrieval cases')
 positives=[];negatives=[];excluded=0
 for r in rows:
  retrieved=r['retrieved']
  if len(set(retrieved))!=len(retrieved) or not all(isinstance(x,str) and x for x in retrieved):raise ValueError('Duplicate or invalid retrieved IDs')
  groups=r.get('gold_groups',[])
  if groups:
   if any(not g or not all(isinstance(x,str) and x for x in g) for g in groups):raise ValueError('Invalid gold groups')
   top=retrieved[:k];ranks=[i+1 for i,x in enumerate(top) if any(x in g for g in groups)]
   covered=sum(bool(set(top)&set(g)) for g in groups)
   positives.append((bool(ranks),1/min(ranks) if ranks else 0,covered/len(groups),covered==len(groups)))
  elif r.get('expect_abstain') is True:negatives.append(not retrieved[:k])
  else:excluded+=1
 n=len(positives);m=len(negatives)
 return {'k':k,'positive_denominator':n,'negative_denominator':m,'not_applicable':excluded,'hit_at_k':sum(x[0] for x in positives)/n if n else None,'mrr_at_k':sum(x[1] for x in positives)/n if n else None,'required_group_recall_at_k':sum(x[2] for x in positives)/n if n else None,'all_required_groups_at_k':sum(x[3] for x in positives)/n if n else None,'negative_abstention':sum(negatives)/m if m else None,'negative_false_positive_rate':1-sum(negatives)/m if m else None,'claim':'Retrieval coverage only, not answer correctness or completeness.'}

def quality_report(records,*,planned_cases=40,planned_replicates=3):
 """Never pool controlled and real execution. Missing or malformed review is inconclusive."""
 if type(planned_cases) is not int or planned_cases<1 or type(planned_replicates) is not int or planned_replicates<1:raise ValueError('Invalid planned denominator')
 seen=set();groups=defaultdict(list)
 for r in records:
  required={'case_id','replicate','execution_kind','dataset_hash','manifest_hash','judgment','packet'}
  if not required<=set(r) or type(r['replicate']) is not int or not 1<=r['replicate']<=planned_replicates:raise ValueError('Missing run provenance')
  if not re.fullmatch(r'(?:O(?:0[1-9]|10)|R(?:0[1-9]|10)|H(?:0[1-9]|1[0-9]|20))',r['case_id']):raise ValueError('Unknown case ID')
  if r['execution_kind'] not in ('controlled','deterministic_local','model_real'):raise ValueError('Unknown execution kind')
  if any(not re.fullmatch('[a-f0-9]{64}',r[x]) for x in ('dataset_hash','manifest_hash')):raise ValueError('Invalid provenance hash')
  identity=(r['dataset_hash'],r['manifest_hash'],r['execution_kind'],r['case_id'],r['replicate'])
  if identity in seen:raise ValueError('Duplicate execution cannot replace an earlier result')
  seen.add(identity);groups[identity[:3]].append(r)
 result=[]
 for (dataset,manifest,kind),rows in groups.items():
  dimensions={d:Counter() for d in DIMENSIONS};inconclusive=0;patterns=defaultdict(list);workflow=0;case_results={}
  for r in rows:
   per=case_results.setdefault(r['case_id'],{'recorded':0,'assessed':0,'inconclusive':0,'dimensions':{d:Counter() for d in DIMENSIONS}});per['recorded']+=1
   from evals.judging import JudgeResult,validate_verdict
   try:
    imported=JudgeResult.model_validate(r['judgment'])
    checked=validate_verdict(r['packet'],imported.verdict.model_dump()) if imported.status=='assessed' and imported.verdict and imported.error_code is None else None
   except Exception:checked=None
   if checked is None or checked.status!='assessed':
    inconclusive+=1;per['inconclusive']+=1;continue
   v=checked.verdict.model_dump();per['assessed']+=1
   for d in DIMENSIONS:per['dimensions'][d][v[d]]+=1
   for d in DIMENSIONS:dimensions[d][v[d]]+=1
   # Outcome is observable behavior: equal grades with answer/clarify/limit
   # variation are not a stable verdict. Agreement still does not prove quality.
   patterns[r['case_id']].append((v['outcome'], *(v[d] for d in DIMENSIONS)))
   if r.get('effects_verified') is True:workflow+=1
  if len({r['case_id'] for r in rows})>planned_cases:raise ValueError('More cases than planned')
  replicated=[p for p in patterns.values() if len(p)==planned_replicates]
  result.append({'dataset_hash':dataset,'manifest_hash':manifest,'execution_kind':kind,'recorded_executions':len(rows),'planned_executions':planned_cases*planned_replicates,'missing_executions':planned_cases*planned_replicates-len(rows),'assessed_executions':len(rows)-inconclusive,'inconclusive_executions':inconclusive,'dimensions':{d:dict(dimensions[d]) for d in DIMENSIONS},'fully_replicated_assessed_cases':len(replicated),'stable_verdict_cases':sum(len(set(p))==1 for p in replicated),'effects_verification_claimed_records':workflow,'provenance':'imported_unverified_until_manifest_and_provider_receipts_reviewed','semantic_certification':False,'case_results':case_results})
 return {'groups':result,'policy':'No overall grade. Repeated agreement is not evidence of correctness. Text review cannot prove side effects, authorization or human participation.'}


def bind_report(records,frozen):
 """Verify artifact linkage, not provider execution or the truth of imported verdicts."""
 if digest(frozen['files'])!=frozen['manifest_hash']:raise ValueError('Frozen manifest altered')
 if digest(frozen['dataset'])!=frozen['dataset_hash']:raise ValueError('Frozen dataset altered')
 cases=frozen['dataset']['cases']
 if len(cases)!=40 or len({c['id'] for c in cases})!=40 or frozen['case_ids']!=[c['id'] for c in cases] or frozen['case_questions']!={c['id']:c['turns'][-1]['message'] for c in cases} or frozen['case_annotations']!={c['id']:{'split':c['split'],'tags':c['tags']} for c in cases}:raise ValueError('Invalid frozen catalog')
 for r in records:
  if r['case_id'] not in frozen['case_ids'] or r['dataset_hash']!=frozen['dataset_hash'] or r['manifest_hash']!=frozen['manifest_hash']:raise ValueError('Run not bound to frozen artifacts')
  if r.get('packet',{}).get('question')!=frozen['case_questions'][r['case_id']]:raise ValueError('Question/case mismatch')
 result=quality_report(records,planned_cases=frozen['planned_cases'],planned_replicates=frozen['planned_replicates'])
 result.update(artifact_binding_verified=True,provider_receipts_verified=False,case_annotations=frozen['case_annotations'])
 return result
