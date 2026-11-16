"""Offline evaluation utilities. No implicit model, search or service calls."""
import argparse,json,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from evals.quality import catalog,freeze,read_json,write_new,retrieval_metrics,quality_report,source_references,bind_report

def output(path,data):
 p=Path(path).resolve()
 if p==ROOT or ROOT in p.parents:raise ValueError('Evaluation results must be outside the repository')
 write_new(p,data)

def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['validate','freeze','retrieval','report','blind'])
 p.add_argument('--input');p.add_argument('--freeze');p.add_argument('--output');p.add_argument('--case');p.add_argument('--mapping');p.add_argument('--k',type=int,default=3)
 args=p.parse_args(argv)
 try:
  if args.action=='validate':
   cases,gold=catalog(ROOT)
   for oracle in gold['oracles']:source_references(ROOT,oracle)
   result={'catalog_cases':len(cases['cases']),'splits':{'original':10,'regression':10,'holdout':20},'references_resolved':True,'new_outputs_collected':0,'semantic_validation':False}
  elif args.action=='freeze':result=freeze(ROOT)
  elif args.action in ('retrieval','report'):
   if not args.input:raise ValueError('Input required')
   values=read_json(args.input)
   if args.action=='retrieval':result=retrieval_metrics(values['rows'],args.k)
   else:
    if not args.freeze:raise ValueError('Frozen artifact required for report')
    result=bind_report(values['records'],read_json(args.freeze))
  else:
   if not all((args.input,args.case,args.output,args.mapping)):raise ValueError('Case, input, output and mapping required')
   cases,gold=catalog(ROOT);case=next(c for c in cases['cases'] if c['id']==args.case);oracle=next(o for o in gold['oracles'] if o['case_id']==args.case)
   from evals.judging import make_packet
   opaque=uuid.uuid4().hex;loaded=read_json(args.input)
   if len(case['turns'])==1:
    if case['turns'][0]['action']!='chat':raise ValueError('Reset is not a question')
    visible_case={'message':case['turns'][0]['message']};response=loaded
   else:
    response=loaded['response'];conversation=loaded['conversation']
    if not conversation or len(conversation)%2!=1 or any(t['role']!=('user' if i%2==0 else 'assistant') for i,t in enumerate(conversation)):raise ValueError('Explicit alternating transcript required')
    reset=max([i for i,t in enumerate(case['turns']) if t['action']=='reset'] or [-1])
    expected=[t['message'] for t in case['turns'][reset+1:] if t['action']=='chat']
    if [t['content'] for t in conversation if t['role']=='user']!=expected:raise ValueError('Conversation does not match post-reset case turns')
    visible_case={'turns':conversation}
   result=make_packet(visible_case,response,source_references(ROOT,oracle),opaque_id=opaque)
   # Mapping stays private to audit; never sent to judge or generator.
   # Preflight both exclusive destinations; a crash may still leave one artifact.
   if Path(args.output).exists() or Path(args.mapping).exists() or Path(args.output).resolve()==Path(args.mapping).resolve():raise ValueError('Use two new output paths')
   output(args.mapping,{'opaque_id':opaque,'case_id':case['id'],'dataset_hash':freeze(ROOT)['dataset_hash'],'reference_origin':'reviewed_local_corpus','external_or_private_tool_reference_required':oracle['needs_live_reference'],'effects_proof_required':case['evaluation_scope']!='answer'})
  if args.output:output(args.output,result)
  elif args.action!='validate':raise ValueError('Explicit external output file required')
  print(json.dumps(result if args.action=='validate' else {'created':True,'network_calls':0,'semantic_validation':False},ensure_ascii=False));return 0
 except Exception as exc:
  print(json.dumps({'completed':False,'error_type':type(exc).__name__,'message':'Check schema, frozen references and new output paths. No remote call was made.'}));return 1
if __name__=='__main__':raise SystemExit(main())
