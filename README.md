# Getnet Brasil: protótipo de atendimento multiagente

API FastAPI para atendimento demonstrativo sobre produtos Getnet Brasil, consultas sintéticas de suporte e perguntas públicas. A aplicação não é um canal oficial da Getnet e não realiza operações financeiras.

## Arquitetura atual

```text
HTTP + autenticação → sessão e privacidade → supervisor LLM
                                              ↓ escolhe capacidade
                     Knowledge / Support / informação pública / handoff
                                              ↓ observação
                              supervisor decide continuar ou finalizar
```

- **Supervisor** (`app/agentic.py`): quando habilitado, escolhe capacidades e decide novamente após observar seus resultados. Contratos Pydantic, limites e autorização continuam no servidor.
- **Knowledge**: recupera snapshots públicos revisados, com URL, data e hash. O adaptador documental faz seleção por demanda. A geração validada opcional usa planejamento, redação fundamentada e checagem; não é a apresentação editorial legada por cenário.
- **Support**: consulta recebíveis e terminal de demonstração. Identidade e permissões limitam acesso; dados são fictícios, não extratos ou diagnósticos bancários reais.
- **Informação pública**: clima por Open-Meteo e câmbio de referência datado por BCB/PTAX. Não promete cotação negociável nem disponibilidade contínua de provedores.
- **Memória e intervenção humana**: contexto persistido em SQLite, isolamento por sessão e reset; fila humana local com confirmação, resposta de operador e retorno à conversa. Nada é enviado à Getnet.

O caminho canônico é `python -m app.run`, que inicia `app.challenge_api:app`. Módulos legados permanecem no repositório, mas não são o caminho indicado para avaliar o supervisor atual.

### RAG e busca

Ingestão HTTPS → extração → snapshot JSON revisado em `corpus_publico/` → recuperação → resposta com fontes. Novas capturas exigem revisão antes do uso. A recuperação lexical é padrão; o modo semântico é opcional e exige dependências de `requirements-semantic.txt` e modelo local provisionado em `GETNET_LOCAL_EMBEDDING_DIR`.

A busca pública geral não equivale à consulta de clima/câmbio: `GETNET_PUBLIC_SEARCH=disabled` é o padrão; `mwmbl` é uma alternativa experimental com contador local. Brave real é bloqueado e Tavily está pausado nesta configuração. `GETNET_WEB_SEARCH` controla a busca complementar documental. Falha ou ausência de evidência deve aparecer como limitação, não como fato inventado.

## Execução local

Requer Python 3.11+; o Docker usa Python 3.14. Instale as versões fixadas:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt -c constraints-tested.txt
pip check
```

No PowerShell, ative com `.\.venv\Scripts\Activate.ps1`. Guarde credenciais e bancos fora do repositório e de pastas sincronizadas.

### Demonstração sem modelo pago

```bash
export GETNET_AUTH_MODE=demo
export GETNET_CONTEXT_DB=/tmp/getnet-demo/state.db
python -m app.run --preflight
python -m app.run --host 127.0.0.1 --port 8000
```

No PowerShell, use `$env:GETNET_AUTH_MODE='demo'` e defina `GETNET_CONTEXT_DB` em uma pasta local gravável fora do checkout. Esse modo é explicitamente anônimo e sintético. **Não comprova raciocínio de modelo real.** O preflight verifica configuração local sem chamar provedores; não certifica conectividade ou qualidade.

```bash
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"cliente1988","message":"Como funciona a antecipação de recebíveis?"}'
```

A interface interativa de contratos está em `/docs`. `/context/chat` oferece contexto; `/configuration` informa a configuração efetiva conforme as permissões. A API é o produto entregue, não uma interface gráfica de chat.

### Autenticação local

O padrão é `GETNET_AUTH_MODE=required`. Inicialize um cadastro externo e emita uma credencial local:

```bash
python -m app.access_admin --db /caminho/privado/access.db init
python -m app.access_admin --db /caminho/privado/access.db issue \
  --subject cliente1988 --tenant demo --scope chat:use \
  --scope context:reset --scope recebiveis:read --scope terminal:read \
  --ttl 3600 --output /caminho/privado/token.txt
```

Configure `GETNET_AUTH_DB` e envie `Authorization: Bearer <token local>` nas requisições. O token é salvo em arquivo, não impresso. A identidade efetiva vem da credencial; isto não verifica identidade perante a Getnet. Existem limites de taxa por usuário e globais. Nunca reutilize a chave OpenRouter como token da API.

### Supervisor com modelo real

A ativação é explícita. `python -m app.run --env-file /caminho/privado/config.env` carrega somente o arquivo solicitado, sem sobrescrever variáveis já definidas no processo.

| Variável | Finalidade |
|---|---|
| `GETNET_ORCHESTRATION=supervisor` | Ativa o ciclo de decisão do LLM |
| `GETNET_ALLOW_MODEL_NETWORK=1` | Libera transporte de modelo configurado |
| `OPENROUTER_API_KEY` | Credencial privada do provedor |
| `GETNET_SUPERVISOR_MODEL` | Identificador do modelo; template usa `openai/gpt-6-sol` |
| `GETNET_SUPERVISOR_PRICES` | Arquivo de metadados públicos de preço e capacidades atualizado |
| `GETNET_SUPERVISOR_LEDGER` | Banco de orçamento previamente inicializado |
| `GETNET_SUPERVISOR_MAX_CALLS`, `GETNET_SUPERVISOR_COST_CAP` | Limites explicitamente aprovados |
| `GETNET_RAG_GENERATION=validated` | Geração documental validada, também consome o orçamento |

O arquivo de preços exige `checked_at` ISO UTC com menos de 24 horas e `model` com `id`, `supported_parameters` incluindo `structured_outputs`, e `pricing.prompt`/`pricing.completion` em USD por token. Confirme preços e suporte atuais no provedor antes de provisionar; números antigos não são autorização de gasto.

`python -m app.budget_admin --ledger CAMINHO --max-calls LIMITE --max-cost TETO_USD` cria um **novo** ledger; não reseta um existente. Inicializá-lo não autoriza gasto. Cada atendimento pode precisar de várias chamadas. Reservas incertas continuam bloqueadas; não há retry ou troca automática de provedor para contornar falhas.

## Docker

```bash
docker compose build
```

O Compose mantém autenticação obrigatória, volume persistente `/state`, usuário não-root, filesystem somente leitura e modelo desligado. Antes de iniciar, provisione o cadastro no volume:

```bash
docker compose run --rm atendimento python -m app.access_admin --db /state/local/access.db init
docker compose run --rm atendimento python -m app.access_admin --db /state/local/access.db issue --subject cliente1988 --tenant demo --scope chat:use --scope recebiveis:read --scope terminal:read --output /state/local/client-token.txt
docker compose up
```

Recupere o token por um canal local seguro, sem colocá-lo no Git. Compose não passa automaticamente o `.env` ao servidor; para modelo real, forneça explicitamente variáveis, arquivos privados de preço/ledger e mounts necessários. Não exponha a porta publicamente para demonstrar o protótipo.

## Handoff e observabilidade

Rotas `/demo/handoff/propose`, `/demo/handoff/confirm` e `/demo/handoff/status` mantêm o fluxo local. Um operador com escopo apropriado usa `/demo/operator/queue` e `/demo/operator/reply`; `/context/human/updates` permite obter o retorno. Confirmação de protocolo não significa resolução ou contato com uma equipe externa.

`app/observability.py` emite eventos estruturados minimizados; `app/observability_report.py` agrega registros offline. Há identificação de requisição, etapas, duração, chamadas e estados de orçamento. Não há painel de produção, plantão ou SLA. Logs operacionais não substituem avaliação semântica.

## Testes e avaliação

Testes controlados usam mocks e fixtures: comprovam contratos, não qualidade de respostas de um LLM. Execute os testes focais publicados:

```bash
GETNET_AUTH_MODE=demo GETNET_CONTEXT_DB=/tmp/getnet-tests/state.db PYTHONPATH=.:tests python -m unittest test_original_request_boundaries test_eval_judging test_remote_judge
```

No PowerShell, defina também GETNET_AUTH_MODE=demo e GETNET_CONTEXT_DB fora do checkout. Use: `$env:PYTHONPATH='.;tests'` e o mesmo comando Python. A suíte histórica completa contém testes de interfaces anteriores; não use seu volume como nota de qualidade. A publicação de testes não implica CI aprovado.

**Juiz independente opcional:** `evals/judging.py` monta um pacote cego com pergunta, resposta visível, conversa permitida e referências independentes. O contrato exclui resposta esperada, nota anterior e identidade do gerador. `judge(packet)` sem transporte retorna inconclusivo e não faz rede. `evals/remote_judge.py` fornece `RemoteJudge`, adaptador explícito para `openai/gpt-5-mini` via OpenRouter, com chave e ledger fornecidos pelo chamador, sem fallback ou retry. Não roda ao iniciar o servidor.

Para uma avaliação autorizada, monte o pacote com `make_packet(case, response, references, opaque_id=...)`, construa `RemoteJudge(key=..., budget=...)` e chame `judge(packet, transport=adaptador)`. Referências devem ser verificadas separadamente, não copiadas cegamente das citações da resposta. O adaptador tem preços/modelo fixados no código: revise disponibilidade e valores antes de nova utilização real. Não envie dados pessoais ou segredos ao juiz.

O juiz classifica correção, relevância, completude, fundamentação e utilidade; **não calcula sozinho a nota ponderada dos onze critérios V4**, nem comprova autenticação, HITL, implantação ou execução real. Esses critérios exigem evidência de código/execução própria. Para o escopo das dez perguntas originais, avalie as respostas atuais e confronte os itens do feedback, sem usar ausência de campanhas antigas como falha da resposta atual. A recomendação do feedback de ampliar dataset/repetições não é uma campanha automática deste repositório.

## Limites e decisões

- Protótipo: suporte, identidades de exemplo e fila humana são locais/sintéticos; sem integração financeira ou atendimento oficial.
- Fontes são datadas e podem estar incompletas. Modelo, retrieval e APIs externas podem falhar; status de limitação não equivale a sucesso.
- O modo determinístico é para uso controlado sem LLM; validar o supervisor exige configuração e execução reais, explicitamente autorizadas.
- Guardrails, autenticação local e testes reduzem riscos, mas não certificam uso em produção.
- Documentos históricos em `docs/` podem descrever versões anteriores. Este README descreve o caminho de execução atual, sem atribuir nota ou declarar aprovação ainda não comprovada.

ChatGPT apoiou planejamento e discussão de arquitetura; Codex apoiou implementação e testes. Esse apoio ao desenvolvimento é distinto do uso de LLM pela aplicação e não substitui revisão dos resultados.

O catálogo estático em evals/ mantém 40 casos e referências para reprodutibilidade; sua presença não dispara execuções nem amplia a rodada autorizada das dez perguntas. `python scripts/evaluate_quality.py validate` valida esse catálogo offline, sem coletar respostas ou pontuar o modelo.
