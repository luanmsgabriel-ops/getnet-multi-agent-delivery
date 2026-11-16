"""Explicit paid judge adapter; caller supplies authorized shared ledger and key.
No implicit environment lookup, fallback, retry, criteria or generator identity.
"""
import asyncio,json,time,copy
from decimal import Decimal
import httpx
from app.agentic_client import SupervisorClient,ModelUnavailable
from app.context_client import strict_schema
from app.observability import emit_event

class RemoteJudge(SupervisorClient):
    mode='independent_model_judge'
    requires_answer_quotes=True
    def __init__(self,*,key,budget,transport=None):
        super().__init__(key=key,model='openai/gpt-4.1-mini',
            prices={'prompt':'0.0000004','completion':'0.0000016'},budget=budget,
            max_output=2500,transport=transport)
    def decide(self, system, payload, schema, *, timeout=60, deadline=None):
        # Compact wire IDs avoid multiplying long hash enums in the provider's
        # constrained decoder. Canonical hashes and strict local validation stay.
        payload=copy.deepcopy(payload);schema=copy.deepcopy(schema)
        aliases={f'e{i+1}':ref['evidence_id'] for i,ref in enumerate(payload.get('references',[]))}
        for ref,alias in zip(payload.get('references',[]),aliases):ref['evidence_id']=alias
        citations=schema.get('properties',{}).get('citations')
        if citations is not None:
            citations['maxItems']=min(citations.get('maxItems',20),len(aliases))
            if aliases:citations['items']['enum']=list(aliases)
        # Quote selection is restricted to actual visible paragraphs. The model
        # selects IDs, then we restore exact text before canonical validation.
        answer=payload.get('response',{}).get('answer','')
        quotes={f'a{i+1}':part for i,part in enumerate(dict.fromkeys(
            part.strip() for part in answer.split('\n\n') if part.strip() and len(part.strip())<=1000))}
        quote_field=schema.get('properties',{}).get('answer_quotes')
        if quote_field is not None and quotes:
            payload['answer_quote_choices']=[{'id':alias,'text':text} for alias,text in quotes.items()]
            quote_field['items']={'type':'string','enum':list(quotes)}
            quote_field['maxItems']=min(5,len(quotes))
            system+='\nWire format: answer_quotes must select IDs from answer_quote_choices, which contain only exact visible response paragraphs. Do not quote reference text. The caller restores the selected visible text before validation.'
        body = {'model': self.model, 'messages': [{'role':'system','content':system},
            {'role':'user','content':json.dumps(payload,ensure_ascii=False)}],
            'response_format': {'type':'json_schema','json_schema':{'name':'blind_judgment','strict':True,'schema':strict_schema(schema)}},
            'max_tokens':self.max_output,
            'provider':{'only':['OpenAI'],'allow_fallbacks':False,'require_parameters':True,
                'max_price':{k:float(self.prices[v]*1_000_000) for k,v in (('prompt','prompt'),('completion','completion'))}}}
        encoded = json.dumps(body,ensure_ascii=False,separators=(',',':')).encode('utf-8')
        if len(encoded)>80000 or timeout<=0: raise ModelUnavailable('Request limit')
        reserve = Decimal(len(encoded)+1024)*self.prices['prompt'] + self.max_output*self.prices['completion']
        if deadline is not None and time.monotonic()>=deadline:raise ModelUnavailable('Deadline before reservation')
        mode='controlled' if isinstance(self.transport,httpx.MockTransport) else 'remote'
        try:
            call = self.budget.reserve(self.model, reserve)
            # An explicitly provisioned budget may hold more than the estimate.
            # Telemetry reports the authoritative held amount, never a charge.
            with self.budget.db() as db:
                reserve = Decimal(db.execute('SELECT reserved FROM calls WHERE id=?',(call,)).fetchone()[0])
        except Exception:
            emit_event('budget_reservation',stage='budget',outcome='blocked',count=0,
                       cost_state='unknown',mode=mode)
            raise
        emit_event('budget_reservation',stage='budget',outcome='ok',count=1,
                   cost_usd=float(reserve),cost_state='reserved',mode=mode)
        started=time.perf_counter()
        transported=False
        outcome='unavailable'
        # Cancelamento fecha o transporte. Reserva incerta permanece bloqueada;
        # nenhuma exceção/saída bruta/chave/payload é persistida ou devolvida.
        async def limited():
            nonlocal transported
            remaining=min(timeout,deadline-time.monotonic()) if deadline is not None else timeout
            if remaining<=0:raise ModelUnavailable('Deadline before transport')
            transported=True
            return await asyncio.wait_for(self._http(encoded, remaining), remaining)
        try:
            data = asyncio.run(limited())
            self.budget.reconcile(call, data.get('usage', {}))
            choice = data['choices'][0]
            if choice.get('finish_reason') != 'stop': raise ModelUnavailable('Incomplete decision')
            decision=json.loads(choice['message']['content'])
            if isinstance(decision,dict) and isinstance(decision.get('citations'),list):
                decision['citations']=[aliases.get(value,value) for value in decision['citations']]
            if isinstance(decision,dict) and isinstance(decision.get('answer_quotes'),list):
                decision['answer_quotes']=[quotes.get(value,value) for value in decision['answer_quotes']]
            outcome='ok'
            return decision
        except Exception:
            raise ModelUnavailable('Model decision unavailable') from None
        finally:
            # Ledger remains authoritative, not the provider response or logs.
            cost_state='unknown';cost=None;financial_outcome='uncertain'
            try:
                with self.budget.db() as db:
                    row=db.execute('SELECT cost,status FROM calls WHERE id=?',(call,)).fetchone()
                if row and row[1] in ('billed','unexpected_cost'):
                    cost_state='confirmed';cost=float(Decimal(row[0]))
                    financial_outcome='ok' if row[1]=='billed' else 'error'
            except Exception:
                pass
            emit_event('budget_reconciliation',stage='budget',outcome=financial_outcome,
                       cost_state=cost_state,cost_usd=cost,mode=mode,count=1)
            emit_event('model_call',stage='model',outcome=outcome,
                       duration_ms=(time.perf_counter()-started)*1000,count=int(transported),mode=mode)
