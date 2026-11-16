"""OpenRouter opt-in: reserva transacional, sem conteúdo no ledger e sem retries."""
import asyncio
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import httpx
from app.context_client import strict_schema
from app.observability import emit_event

class ModelUnavailable(RuntimeError): pass
class BudgetExhausted(ModelUnavailable): pass

class Budget:
    """Configuração imutável; reservas incertas bloqueiam novas chamadas."""
    def __init__(self, path, *, max_calls, max_cost, initialize=False):
        self.path = Path(path).resolve()
        self.max_calls = int(max_calls)
        self.max_cost = Decimal(str(max_cost))
        if type(initialize) is not bool or not 1 <= self.max_calls <= 100 or not self.max_cost.is_finite() or not 0 < self.max_cost <= 5:
            raise ValueError('Invalid budget')
        if initialize:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open('xb'):
                    pass
                with self.db(validate=False) as db:
                    db.execute('CREATE TABLE budget(calls INTEGER NOT NULL, cap TEXT NOT NULL)')
                    db.execute('CREATE TABLE calls(id INTEGER PRIMARY KEY, model TEXT NOT NULL, reserved TEXT NOT NULL, cost TEXT, status TEXT NOT NULL, created TEXT NOT NULL, input_tokens INTEGER, output_tokens INTEGER)')
                    db.execute('INSERT INTO budget VALUES(?,?)',(self.max_calls,str(self.max_cost)))
            except (OSError, sqlite3.Error):
                raise ModelUnavailable('Ledger initialization unavailable; existing evidence preserved') from None
        with self.db():
            pass

    def _validate(self, db):
        expected = {'budget':['calls','cap'], 'calls':['id','model','reserved','cost','status','created','input_tokens','output_tokens']}
        for table, columns in expected.items():
            if [r[1] for r in db.execute('PRAGMA table_info('+table+')')] != columns:
                raise ModelUnavailable('Ledger schema unavailable')
        config=db.execute('SELECT calls,cap FROM budget').fetchall()
        if config != [(self.max_calls,str(self.max_cost))]:
            raise ModelUnavailable('Budget configuration changed')
        for reserved,cost,status in db.execute('SELECT reserved,cost,status FROM calls'):
            try:
                amount=Decimal(reserved)
                if not amount.is_finite() or amount<=0 or status not in ('reserved','billed','unexpected_cost'):
                    raise ValueError()
                if status=='reserved':
                    if cost is not None:raise ValueError()
                else:
                    charged=Decimal(cost)
                    if not charged.is_finite() or charged<0 or (status=='billed' and charged>amount):raise ValueError()
            except Exception:
                raise ModelUnavailable('Ledger integrity unavailable') from None

    @contextmanager
    def db(self, *, validate=True):
        db=None
        try:
            db=sqlite3.connect(self.path.as_uri()+'?mode=rw', uri=True, timeout=1, isolation_level=None)
            db.execute('BEGIN IMMEDIATE')
            if validate:self._validate(db)
            yield db
            db.execute('COMMIT')
        except BaseException as error:
            if db is not None and db.in_transaction:db.rollback()
            if isinstance(error,(sqlite3.Error,OSError)):
                raise ModelUnavailable('Ledger unavailable') from None
            raise
        finally:
            if db is not None:db.close()

    def reserve(self, model, amount):
        amount = Decimal(str(amount))
        if not amount.is_finite() or amount <= 0: raise ModelUnavailable('Invalid reservation')
        with self.db() as db:
            rows = db.execute('SELECT reserved,cost,status FROM calls').fetchall()
            if any(s != 'billed' for _, _, s in rows): raise ModelUnavailable('Unreconciled reservation')
            total = sum((Decimal(c) for _, c, _ in rows), Decimal(0))
            if len(rows) >= self.max_calls or total + amount > self.max_cost: raise BudgetExhausted('Budget exhausted')
            return db.execute('INSERT INTO calls(model,reserved,status,created) VALUES(?,?,?,?)',
                (model, str(amount), 'reserved', datetime.now(timezone.utc).isoformat())).lastrowid

    def reconcile(self, call, usage):
        try:
            cost = Decimal(str(usage.get('cost')))
            if not cost.is_finite() or cost < 0:raise ValueError()
        except Exception:
            raise ModelUnavailable('Unknown cost') from None
        with self.db() as db:
            row = db.execute('SELECT reserved,status FROM calls WHERE id=?', (call,)).fetchone()
            if row is None or row[1] != 'reserved': raise ModelUnavailable('Ledger conflict')
            status = 'billed' if cost <= Decimal(row[0]) else 'unexpected_cost'
            counts = [usage.get(k) for k in ('prompt_tokens', 'completion_tokens')]
            counts = [v if type(v) is int and v >= 0 else None for v in counts]
            db.execute('UPDATE calls SET cost=?,status=?,input_tokens=?,output_tokens=? WHERE id=?',
                       (str(cost), status, *counts, call))
        if status != 'billed': raise ModelUnavailable('Unexpected cost')

class SupervisorClient:
    mode = 'model_supervisor'
    def __init__(self, *, key, model, prices, budget, max_output=1500, transport=None, reasoning_effort="low", stage_reasoning=None):
        if not key or not model or not 128 <= max_output <= 3500: raise ValueError('Missing model configuration')
        if reasoning_effort not in ('low','medium'):raise ValueError('Invalid reasoning effort')
        self.reasoning_effort=reasoning_effort
        self.stage_reasoning=dict(stage_reasoning or {})
        if (set(self.stage_reasoning)-{'RequestPlan','Draft','Verdict','Decision'}
            or any(value not in ('low','medium') for value in self.stage_reasoning.values())):
            raise ValueError('Invalid per-stage reasoning configuration')
        self.key, self.model, self.budget = key, model, budget
        self.prices = {k: Decimal(str(prices[k])) for k in ('prompt', 'completion')}
        if any(not v.is_finite() or v <= 0 for v in self.prices.values()): raise ValueError('Invalid prices')
        self.max_output, self.transport = max_output, transport

    async def _http(self, body, timeout):
        async with httpx.AsyncClient(timeout=timeout, trust_env=False, follow_redirects=False,
                transport=self.transport or httpx.AsyncHTTPTransport(retries=0)) as client:
            async with client.stream('POST', 'https://openrouter.ai/api/v1/chat/completions',
                    headers={'Authorization': 'Bearer '+self.key, 'Content-Type': 'application/json'}, content=body) as response:
                if response.status_code != 200:
                    # Keep the HTTP fact, never provider bodies/headers or guesses
                    # about quota/balance. The caller retains the uncertain reserve.
                    emit_event('provider_http_error', stage='model',
                               outcome='limited' if response.status_code == 429 else 'unavailable',
                               http_status=response.status_code,
                               mode='controlled' if isinstance(self.transport,httpx.MockTransport) else 'remote')
                    raise ModelUnavailable('Provider unavailable')
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 150000: raise ModelUnavailable('Provider response too large')
                return json.loads(raw)

    def decide(self, system, payload, schema, *, timeout, deadline=None):
        body = {'model': self.model, 'messages': [{'role':'system','content':system},
            {'role':'user','content':json.dumps(payload,ensure_ascii=False)}],
            'response_format': {'type':'json_schema','json_schema':{'name':'supervisor_decision','strict':True,'schema':strict_schema(schema)}},
            'max_tokens':self.max_output, 'reasoning':{'effort':self.stage_reasoning.get(schema.get('title'),self.reasoning_effort),'exclude':True},
            'provider':{'only':['OpenAI'],'allow_fallbacks':False,'require_parameters':True,
                'max_price':{k:float(self.prices[v]*1_000_000) for k,v in (('prompt','prompt'),('completion','completion'))}}}
        encoded = json.dumps(body,ensure_ascii=False,separators=(',',':')).encode('utf-8')
        if len(encoded)>50000 or timeout<=0: raise ModelUnavailable('Request limit')
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

def configured_client(env=None):
    env = os.environ if env is None else env
    if env.get('GETNET_ORCHESTRATION','deterministic') != 'supervisor': return None
    required = ('OPENROUTER_API_KEY','GETNET_SUPERVISOR_MODEL','GETNET_SUPERVISOR_PRICES','GETNET_SUPERVISOR_LEDGER','GETNET_SUPERVISOR_MAX_CALLS','GETNET_SUPERVISOR_COST_CAP')
    if any(not env.get(k) for k in required) or env.get('GETNET_ALLOW_MODEL_NETWORK') != '1':
        raise ValueError('Supervisor requires explicit model, authorization, prices, key and budget')
    meta=json.loads(Path(env['GETNET_SUPERVISOR_PRICES']).read_text('utf-8'))
    model=env['GETNET_SUPERVISOR_MODEL'].removeprefix('openrouter:')
    stamp=datetime.fromisoformat(meta['checked_at'])
    age=(datetime.now(timezone.utc)-stamp).total_seconds()
    if meta['model']['id'] != model or not 0 <= age <= 86400 or 'structured_outputs' not in meta['model']['supported_parameters']:
        raise ValueError('Refresh public pricing and model capabilities')
    return SupervisorClient(key=env['OPENROUTER_API_KEY'], model=model, prices=meta['model']['pricing'],
        budget=Budget(env['GETNET_SUPERVISOR_LEDGER'],max_calls=env['GETNET_SUPERVISOR_MAX_CALLS'],max_cost=env['GETNET_SUPERVISOR_COST_CAP']),
        max_output=int(env.get('GETNET_SUPERVISOR_MAX_OUTPUT','1500')),reasoning_effort=env.get('GETNET_SUPERVISOR_REASONING','low'),
        stage_reasoning=json.loads(env.get('GETNET_SUPERVISOR_STAGE_REASONING','{}')))
