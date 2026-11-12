"""Transporte opt-in sem retry; reserva/custo por chamada e UTF-8 exato."""
import json,os,time,hashlib
from decimal import Decimal
from pathlib import Path
import httpx

def strict_schema(value):
    if isinstance(value,list):return [strict_schema(v) for v in value]
    if not isinstance(value,dict):return value
    result={k:strict_schema(v) for k,v in value.items() if k!='default'}
    if result.get('type')=='object':result.update(required=list(result.get('properties',{})),additionalProperties=False)
    return result
class ModelClient:
    def __init__(self,ledger,api_key,prices,*,model='openai/gpt-6-luna',max_calls=50,max_cost='0.25',max_output=2500):
        self.path=Path(ledger);self.api_key=api_key;self.model=model;self.prices=prices;self.max_calls=max_calls;self.max_cost=Decimal(max_cost);self.max_output=max_output
    def complete(self,system,payload,schema):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        lock=self.path.with_suffix('.lock');fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
        try:return self._call(system,payload,schema)
        finally:os.close(fd);lock.unlink()
    def _call(self,system,payload,schema):
        ledger=json.loads(self.path.read_text('utf-8')) if self.path.exists() else {'calls':[],'spent_or_reserved':'0','authorization':'User 2026-11-10: proportional paid validation authorized; operational per-round limits'}
        if ledger.get('halted'):raise RuntimeError('Ledger halted')
        if len(ledger['calls'])>=self.max_calls:raise RuntimeError('Operational call cap')
        content=json.dumps(payload,ensure_ascii=False,separators=(',',':'))
        body={'model':self.model,'messages':[{'role':'system','content':system},{'role':'user','content':content}], 'response_format':{'type':'json_schema','json_schema':{'name':'context_turn','strict':True,'schema':strict_schema(schema)}},'max_tokens':self.max_output,'reasoning':{'effort':'low','exclude':True},'provider':{'only':['OpenAI'],'allow_fallbacks':False,'require_parameters':True,'max_price':{'prompt':float(Decimal(self.prices['prompt'])*1000000),'completion':float(Decimal(self.prices['completion'])*1000000)}}}
        encoded=json.dumps(body,ensure_ascii=False,separators=(',',':')).encode('utf-8')
        if json.loads(json.loads(encoded)['messages'][1]['content'])!=payload:raise ValueError('UTF8 mismatch')
        if len(encoded)>60000:raise ValueError('Input byte bound')
        reserve=Decimal(len(encoded)+1024)*Decimal(self.prices['prompt'])+Decimal(self.max_output)*Decimal(self.prices['completion'])
        spent=Decimal(ledger['spent_or_reserved'])
        if spent+reserve>self.max_cost:raise RuntimeError('Operational cost cap')
        row={'model':self.model,'request_sha256':hashlib.sha256(encoded).hexdigest(),'payload':payload,'reserve':str(reserve),'status':'reserved','max_output':self.max_output,'retries':0,'fallbacks':False}
        ledger['calls'].append(row);ledger['spent_or_reserved']=str(spent+reserve)
        def save():
            tmp=self.path.with_suffix('.tmp');tmp.write_text(json.dumps(ledger,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(tmp,self.path)
        save();start=time.perf_counter()
        try:
            with httpx.Client(timeout=60,transport=httpx.HTTPTransport(retries=0)) as client:
                res=client.post('https://openrouter.ai/api/v1/chat/completions',headers={'Authorization':'Bearer '+self.api_key,'Content-Type':'application/json'},content=encoded)
            row['http_status']=res.status_code
            if res.status_code!=200:raise RuntimeError('Provider HTTP failure; no response body logged')
            data=res.json();usage=data.get('usage',{});row['usage']={k:usage.get(k) for k in ('prompt_tokens','completion_tokens','total_tokens','cost')}
            cost=Decimal(str(usage['cost']))
            if not cost.is_finite() or cost<0 or cost>reserve:raise ValueError('Unexpected provider cost')
            ledger['spent_or_reserved']=str(spent+cost);row['status']='billed'
            choice=data['choices'][0];row['finish_reason']=choice.get('finish_reason');row['output']=choice.get('message',{}).get('content','')
            if choice.get('finish_reason')!='stop':raise ValueError('Incomplete model output')
            result=json.loads(row['output']);row['status']='received';return result
        except Exception as exc:
            row['error']=type(exc).__name__
            if row['status']=='reserved':ledger['halted']='unknown_cost';row['status']='unknown_cost'
            raise
        finally:row['seconds']=time.perf_counter()-start;save()
