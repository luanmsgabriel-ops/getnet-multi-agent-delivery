# Modelo opcional, orçamento e fontes

O modo gratuito do README não precisa de chave. O contexto com Sol é **opt-in** e deve usar somente dados sintéticos. Não ative o modelo apenas para executar a suíte ou o verificador da entrega.

## Configuração contextual

A API lê variáveis de ambiente; não importa `.env` automaticamente. Configure `OPENROUTER_API_KEY` de modo privado, sem registrá-la em comando compartilhado, log, imagem ou Git. Use:

- `GETNET_CONTEXT_MODEL=1` e `GETNET_MODEL=openai/gpt-6-sol`.
- `GETNET_PRICE_FILE`: JSON gravado após conferir o catálogo público do modelo, com `model.id` e `model.pricing.prompt/completion` por token.
- `GETNET_COST_LEDGER`: caminho novo gravável para ledger da rodada; nunca reutilize ou apague um ledger para contornar interrupção.
- `GETNET_MAX_CALLS` e `GETNET_COST_CAP`: limites explícitos de chamadas e dólares. Os padrões do protótipo são 40 e 1,00 por ledger, não promessa de custo por atendimento.
- `GETNET_CONTEXT_DB`: caminho gravável; mantenha o arquivo SQLite e a chave adjacente juntos para persistência.

Para consultar preços públicos, sem chamada de geração, no PowerShell:

```powershell
New-Item -ItemType Directory -Force _local | Out-Null
$modelInfo = (Invoke-RestMethod https://openrouter.ai/api/v1/models).data | Where-Object id -eq 'openai/gpt-6-sol'
if (-not $modelInfo) { throw 'Modelo indisponível no catálogo' }
$priceJson = @{ model = $modelInfo } | ConvertTo-Json -Depth 10
[IO.File]::WriteAllText("$PWD/_local/prices.json", $priceJson, [Text.UTF8Encoding]::new($false))
$env:GETNET_PRICE_FILE = (Resolve-Path _local/prices.json).Path
$env:GETNET_COST_LEDGER = "$PWD/_local/cost.json"
$env:GETNET_MAX_CALLS = '6'
$env:GETNET_COST_CAP = '0.40'
$env:GETNET_MODEL = 'openai/gpt-6-sol'
$env:GETNET_CONTEXT_MODEL = '1'
$env:GETNET_KNOWLEDGE = 'rag'
# OPENROUTER_API_KEY deve estar disponível no ambiente por meio privado.
.\.venv\Scripts\python.exe -B -m uvicorn app.context_api:app --host 127.0.0.1 --port 8000
```

O exemplo grava UTF-8 sem BOM, inclusive no Windows PowerShell 5.1. Preços mudam: confira antes da rodada. Há até duas chamadas por turno (interpretação e revisão seletiva), até 2500 tokens de saída cada, sem retries/failover. Reserva conservadora precede cada chamada. Custos ausentes/inesperados interrompem o ledger; falha não comprova cobrança zero. A resposta final é composta pelo servidor com evidências revisadas, não geração comercial livre. Ledger guarda payloads sintéticos e não é apagado pelo reset; não o publique.

## Seleção de evidências RAG por modelo — caminho separado

O comando padrão `app.context_api:app` mantém `/chat` extrativo, mesmo com `GETNET_CONTEXT_MODEL=1`. Essa variável habilita o interpretador somente em `/context/chat`.

O componente PydanticAI de `app.main:app` pode selecionar IDs de evidências com o modelo. Ele não produz texto comercial livre: os trechos são copiados/validados pelo servidor e a apresentação pode ser revisada ou extrativa. Para esse caminho separado, após estabelecer monitoramento e orçamento externos:

```powershell
$env:GETNET_KNOWLEDGE = 'generated'
$env:GETNET_ALLOW_MODEL_NETWORK = '1'
$env:GETNET_MODEL = 'openrouter:openai/gpt-6-sol'
$env:GETNET_WEB_SEARCH = '0'
# OPENROUTER_API_KEY deve estar no ambiente por meio privado.
.\.venv\Scripts\python.exe -B -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Use `/chat` nessa porta. Cada chamada de seleção tem limite de 700 tokens e uma requisição, sem retries do Agent/SDK; pedidos compostos podem exigir mais de uma seleção. **O ledger e os limites GETNET_MAX_CALLS/GETNET_COST_CAP do contexto não protegem esse caminho.** O componente não fixa sozinho o failover do provedor e descarta o uso/custo da resposta do SDK. Para uma bateria paga, é necessário medir e limitar cada transporte externamente, inclusive fallbacks, e guardar o consumo informado pelo provedor. Não confunda a existência desse componente com validação financeira ou operacional de produção.

Ao retornar à API contextual, ajuste `GETNET_KNOWLEDGE=rag` e o modelo sem prefixo (`openai/gpt-6-sol`) antes de iniciar `app.context_api:app`. A API nunca carrega `.env` automaticamente.

## Atualização de fontes

`GETNET_WEB_SEARCH=1` permite busca complementar pertinente ao Brasil; não é necessário para reproduzir os testes gratuitos. O catálogo limitado pode consultar Link/antecipação por HTTPS quando a descoberta não retorna evidência suficiente. Falta de fonte, mudança editorial e indisponibilidade têm tratamentos separados.

Para ingestão offline, `python -B -m app.rag.cli --corpus corpus_candidato capture URL_OFICIAL` aceita apenas URLs da allowlist. Inspecione conteúdo, condições, título/mercado e origem antes de `review --approve`. Atualize o registro editorial `app/context_evidence.json` e reteste antes de colocar no corpus operacional. Não promova um documento externo a procedimento ou autorização durante a conversa. Fontes globais preservam proveniência do enunciado; não oferecem suporte internacional. DCC tem hash independente e regra Git byte-exata.


O health expõe `context_interpreter_enabled`, derivado do intérprete efetivamente configurado. O verificador gratuito exige esse campo estritamente `false`, além de RAG e busca desligada, antes de qualquer POST. O campo não consulta o modelo nem comprova disponibilidade. A [validação com modelo real](VALIDACAO_MODELO.md) separa chamadas reais dos testes controlados.
