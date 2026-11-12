# Getnet Brasil — atendimento multiagente

Protótipo de atendimento para produtos e serviços **Getnet Brasil**, desenvolvido para o desafio *AI Hardcore Engineer — Multi-Agent Support System*. Três agentes cooperam via **LangGraph**, com API **FastAPI**, contratos **Pydantic**, RAG e uso opcional de modelo pelo OpenRouter.

As ferramentas de suporte usam **dados fictícios**. A aplicação não é um canal oficial da Getnet, não acessa contas bancárias reais e não realiza operações financeiras.

## Arquitetura e agentes

```text
HTTP → privacidade e escopo → Router → Support e/ou Knowledge → resposta JSON
                                  ↑
/context/chat → interpretação opcional → contexto validado por sessão/entidade
```

- **Router:** identifica os pedidos, define a sequência dos especialistas e preserva as partes válidas de pedidos mistos.
- **Knowledge:** recupera fontes pertinentes, verifica condições e compõe respostas fundamentadas; pode complementar a base com busca externa.
- **Support:** utiliza `consultar_recebiveis` e `consultar_terminal`, ferramentas de leitura com contratos e fixtures sintéticas. Eventos indicam quais ferramentas foram acionadas.

O grafo passa contratos Pydantic entre os agentes e retorna fontes, rota, status e duração. O contexto opcional valida fatos por entidade/incidente antes de persistir em SQLite; uma proposta do modelo não autoriza ações. Veja a [arquitetura detalhada](docs/ARQUITETURA.md).

### Comunicação, estado e apresentação

A comunicação é **síncrona e local, por chamadas de funções coordenadas pelo LangGraph**; não usa fila distribuída, broker ou troca de mensagens entre serviços independentes. O Router devolve um `Plano`; cada especialista recebe uma `Entrada` e um contexto de respostas anteriores, e devolve uma `RespostaEspecialista`. Esses contratos Pydantic validam a forma dos dados. O estado do grafo acumula respostas, eventos, rota e sinalização de falha.

Os caminhos são `Router → Knowledge`, `Router → Support` ou `Router → Support → Knowledge`; pedidos que exigem esclarecimento ou encerramento por política podem terminar após o Router. Por exemplo, quando uma orientação pública depende de dados sintéticos de suporte, o Support pode executar sua ferramenta e o Knowledge recebe as respostas anteriores. Quando há uma pergunta pública independente em um pedido misto, a implementação separa as entradas e não repassa esse contexto privado ao Knowledge. Recusas e limites interrompem a sequência, salvo a exceção explícita da pergunta pública independente de uma identidade demo desconhecida. Veja [o grafo e suas condições](app/orchestration.py).

O bloco **Personality** do diagrama do desafio não foi implementado como um quarto agente ou nó separado. Nesta solução, a apresentação está incorporada à composição da resposta no servidor e aos textos revisados dos especialistas: reúne blocos, preserva fontes e adiciona avisos explícitos de privacidade/limitação sem duplicá-los. Não há um LLM de personalidade reescrevendo livremente evidências ou dados das ferramentas. A identificação como demonstração é aplicada na API; essa camada não autoriza operações. Veja [composição de avisos](app/response_notices.py).

## RAG, busca e escopo

O fluxo é **ingestão HTTPS → extração e revisão → snapshots JSON com origem/data/hash → recuperação lexical por pedido → apresentação extrativa ou revisada**. Não usa embeddings, banco vetorial ou GraphRAG. Fontes sem evidência suficiente resultam em limitação explícita.

`GETNET_WEB_SEARCH=1` habilita busca complementar com filtros de pertinência e fontes oficiais brasileiras. O catálogo de apoio cobre Link de Pagamento e antecipação; a descoberta de outros assuntos pode ser insuficiente. A ingestão offline está disponível em `python -m app.rag.cli --corpus PASTA_NOVA capture URL_PERMITIDA`. Capturas ficam com `reviewed=false` e exigem revisão antes de entrar no corpus ativo. A captura pendente da FAQ Pix não substitui a fonte aprovada. Fontes globais preservadas para proveniência não habilitam suporte internacional.

Assuntos fora de Getnet Brasil recebem redirecionamento educado. Clima segue essa política; euro sem contexto recebe esclarecimento, sem cotação genérica. Conversão em venda Getnet Brasil só é explicada com fonte pertinente. Pedidos mistos preservam a parte atendível; ambiguidades relevantes pedem esclarecimento.

### Fontes de conhecimento e busca web

**Corpus local (RAG).** Os snapshots revisados de [`corpus_publico/`](corpus_publico/) registram URL solicitada, URL final, data de captura, hash e estado de revisão. As URLs abaixo identificam a origem dos documentos versionados; não significam que toda página seja consultada ao vivo a cada atendimento, nem que uma captura represente todo o site.

| Documento | URL de origem |
|---|---|
| Como configurar o Wi-Fi na sua maquininha Getnet? | https://site.getnet.com.br/get-ajuda-configuracoes/como-configurar-o-wi-fi-na-sua-maquininha-getnet/ |
| The Leading AI Payments Company in Latin America and Europe | https://www.getnet.net/en |
| Erro ADQ 1-19: erro de conexão | https://site.getnet.com.br/get-ajuda-erros-maquininha/erro-adq-1-19/ |
| Como habilitar o Pix pelo Portal? | https://site.getnet.com.br/get-ajuda-pix/como-habilitar-pix-pelo-portal/ |
| Descontinuação dos pagamentos via WhatsApp Busines | https://site.getnet.com.br/get-ajuda-whatsapp-business/descontinuacao-whatsapp-business/ |
| The Leading AI Payments Company in Latin America and Europe | https://www.getnet.net/ |
| Get Smart: caracteristicas tecnicas, manual pagina 3 | https://site.getnet.com.br/wp-content/uploads/2025/09/Manul-GetSmart.pdf |
| Crediário: perguntas frequentes | https://site.getnet.com.br/crediario/ |
| Como antecipar suas vendas pelo app? | https://site.getnet.com.br/get-ajuda-antecipacao-de-venda/como-antecipar-sua-vendas-pelo-app/ |
| Receber vendas via Pix: conta bancaria ou conta de pagamento | https://site.getnet.com.br/duvidas/ |
| Quais são os possíveis status das minhas vendas? | https://site.getnet.com.br/get-ajuda-gestao-de-vendas/quais-possiveis-status-das-minhas-vendas/ |
| Get Classica: botoes e conectividade, manual paginas 3, 4 e 9 | https://site.getnet.com.br/wp-content/uploads/2026/06/getnet_12_06-26_Manul_GetClassica_V2.pdf |

As duas entradas globais (`www.getnet.net/` e `www.getnet.net/en`) registram, nas capturas, a mesma URL final `https://www.getnet.net/en/`. São preservadas como proveniência; a política de atendimento continua restrita a Getnet Brasil. A versão capturada, os trechos efetivamente armazenados e as datas devem ser conferidos nos respectivos JSONs, não inferidos apenas pela URL.

**Busca dinâmica.** Com `GETNET_WEB_SEARCH=1`, a implementação consulta [Bing RSS](https://www.bing.com/search?format=rss) com a pergunta filtrada e restrição de domínio `site:site.getnet.com.br`, validando pertinência e origem oficial dos resultados. As URLs encontradas variam por consulta; não há lista fixa de todos os resultados possíveis. Snippets são evidências de descoberta, não garantia de exatidão ou disponibilidade. Veja [`general_web.py`](app/rag/general_web.py).

**Catálogo complementar fixo.** Quando a descoberta não retorna resultados suficientes, o [catálogo oficial](app/rag/official_catalog.py) pode consultar por HTTPS, conforme o assunto:

- Link de Pagamento: https://site.getnet.com.br/link-de-pagamento/
- Antecipação de vendas pelo aplicativo: https://site.getnet.com.br/get-ajuda-antecipacao-de-venda/como-antecipar-sua-vendas-pelo-app/

O catálogo não amplia automaticamente a cobertura para outros assuntos. As fontes usadas na resposta são informadas no campo `sources` da API; isso não comprova, por si só, uma chamada de modelo nem uma nova consulta web.

## Pré-requisitos e instalação

- Python **3.11+** e `pip`; versão efetivamente testada registrada nas [evidências](docs/VALIDACAO_ENTREGA.md).
- Docker para execução em contêiner.
- Chave OpenRouter e orçamento configurado **somente para usar o modelo**.

Na raiz do repositório, em PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -c constraints-tested.txt
.\.venv\Scripts\python.exe -m pip check
$env:GETNET_CONTEXT_MODEL = '0'
$env:GETNET_KNOWLEDGE = 'rag'
$env:GETNET_WEB_SEARCH = '0'
$env:GETNET_CONTEXT_DB = "$env:TEMP/getnet-context-demo/state.db"
.\.venv\Scripts\python.exe -B -m uvicorn app.context_api:app --host 127.0.0.1 --port 8000
```

Em Linux/macOS, use `.venv/bin/python` e `export NOME=valor`. **A API não carrega `.env` automaticamente.** `.env.example` é referência: configure as variáveis no processo. O modo acima não precisa de chave nem faz chamadas ao modelo.

Para executar o mesmo modo local em um shell Linux/macOS, na raiz do repositório:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -c constraints-tested.txt
.venv/bin/python -m pip check
export GETNET_CONTEXT_MODEL=0
export GETNET_KNOWLEDGE=rag
export GETNET_WEB_SEARCH=0
export GETNET_CONTEXT_DB="${TMPDIR:-/tmp}/getnet-context-demo/state.db"
.venv/bin/python -B -m uvicorn app.context_api:app --host 127.0.0.1 --port 8000
```

Mantenha o servidor nesse terminal e use outro para as requisições. `Ctrl+C` encerra o servidor local. Isso inicia a API, não uma interface de chat: envie JSON aos endpoints abaixo.

## Modos e configuração do modelo

| Caminho | Comportamento |
|---|---|
| `app.context_api:app`, `POST /chat` | Atendimento stateless com RAG extrativo/revisado; não chama o interpretador contextual. |
| `app.context_api:app`, `POST /context/chat`, modelo desligado | Responde pedidos autocontidos; memória semântica completa não está disponível. |
| `app.context_api:app`, `POST /context/chat`, `GETNET_CONTEXT_MODEL=1` | Modelo propõe fatos/pedidos estruturados e pode revisar ambiguidades; servidor valida contexto e compõe a resposta com fontes. |
| `app.main:app`, `GETNET_KNOWLEDGE=generated`, `POST /chat` | Componente PydanticAI usa modelo para selecionar IDs de evidências. A aplicação copia/verifica os trechos e pode usar apresentação revisada ou fallback. |

**Nenhum desses modos promete redação comercial livre por LLM.** Uma resposta extrativa pode ocorrer após seleção real pelo modelo; fontes e resposta final, sozinhas, não comprovam uma chamada.

### Modelo escolhido e responsabilidades

A arquitetura não atribui um LLM diferente a cada agente. **GPT-6 Sol** (`openai/gpt-6-sol`) é o modelo usado na validação real documentada, acessado via **OpenRouter**; OpenRouter é o intermediário, não o modelo. O uso de ChatGPT/Codex para desenvolver o projeto é uma atividade distinta, descrita adiante.

| Componente | Uso de modelo na aplicação | Motivo da separação |
|---|---|---|
| Router | Sem chamada própria de LLM: regras determinísticas definem o plano e o LangGraph executa a sequência. | Manter o encaminhamento explícito e verificável, sem gerar uma decisão livre a cada etapa. |
| Support | Sem LLM próprio: executa ferramentas de leitura sobre fixtures sintéticas, com contratos e validações. | Não delegar ao modelo autorização, consulta bancária real ou execução de operações financeiras. |
| Knowledge padrão | Recuperação lexical e apresentação extrativa/revisada, sem chamada de LLM. | Responder a partir de evidências disponíveis e preservar condições e limites das fontes. |
| Knowledge opcional em `app.main` | GPT-6 Sol, quando configurado, seleciona IDs de evidências; o servidor copia, verifica e apresenta os trechos ou usa fallback. | Usar o modelo na seleção, sem permitir síntese comercial livre ou afirmações sem suporte. |
| Interpretação contextual em `/context/chat` | GPT-6 Sol propõe entidades, fatos e pedidos estruturados; pode haver revisão seletiva pelo mesmo modelo. | Apoiar interpretação de linguagem e contexto, mantendo validação e persistência sob controle do servidor. Não é um quarto agente do grafo. |

A escolha arquitetural é reservar chamadas de modelo para interpretação e seleção, usando regras onde contratos e procedimentos explícitos são suficientes. Isso evita chamadas desnecessárias e limita a variabilidade dessas etapas; não constitui prova de menor latência ou custo em relação a todas as alternativas. **Não foi demonstrado um benchmark comparativo que permita afirmar que GPT-6 Sol é o melhor, mais rápido ou mais barato modelo.** Sua adequação foi examinada nos cenários da [validação real](docs/VALIDACAO_MODELO.md), com resultados e limitações registrados.

O modelo é configurável por `GETNET_MODEL`: o caminho contextual usa `openai/gpt-6-sol` como padrão quando habilitado, e o caminho PydanticAI separado exige a configuração com prefixo `openrouter:` (por exemplo, `openrouter:openai/gpt-6-sol`). Trocar o identificador não comprova compatibilidade: é preciso conferir disponibilidade, preços, suporte à saída estruturada e repetir a validação pertinente. A configuração padrão de demonstração não habilita chamadas pagas.

No contexto, `GETNET_MAX_CALLS` e `GETNET_COST_CAP` controlam o orçamento do ledger configurado, não uma promessa de custo por atendimento; preços devem corresponder ao modelo. O limite de tokens e as condições de uso do caminho RAG separado são diferentes, e esse caminho **não recebe automaticamente a proteção do ledger contextual**. Consulte [configuração e limites de cada caminho](docs/MODELO_E_FONTES.md) antes de habilitar rede/modelo.

### Por que manter três agentes

A solução mantém três responsabilidades distintas: encaminhar o pedido, consultar conhecimento público e consultar ferramentas de suporte. O quarto agente personalizado é um bônus do desafio e não foi implementado; a decisão de escopo evita adicionar um componente sem uma responsabilidade operacional demonstrável. Isso não significa que um agente de escalonamento seja inútil: seria uma evolução pertinente com integração, autorização e confirmação de recebimento pelo canal humano.

Na demonstração atual, o sistema explicita limitações e orienta canais oficiais quando cabível; **não abre ticket nem transfere a conversa para um operador**. A apresentação associada ao bloco *Personality* permanece na composição da resposta, não conta como quarto agente e não exige outro modelo.

Para contexto com modelo, configure `OPENROUTER_API_KEY` privadamente e:

```powershell
$env:GETNET_KNOWLEDGE = 'rag'
$env:GETNET_MODEL = 'openai/gpt-6-sol'
$env:GETNET_PRICE_FILE = "$PWD/_local/prices.json"
$env:GETNET_COST_LEDGER = "$PWD/_local/cost.json"
$env:GETNET_MAX_CALLS = '6'
$env:GETNET_COST_CAP = '0.40'
$env:GETNET_CONTEXT_MODEL = '1'
.\.venv\Scripts\python.exe -B -m uvicorn app.context_api:app --host 127.0.0.1 --port 8000
```

Crie `prices.json` com o preço vigente e use um ledger novo conforme [configuração do modelo](docs/MODELO_E_FONTES.md). Esse caminho limita chamadas/custo e registra consumo; pode fazer interpretação e revisão no mesmo turno, sem retries/failover. **Esses limites de ledger não se aplicam ao componente RAG separado de `app.main`.** Sua ativação e necessidade de monitoramento externo estão no mesmo documento. Nunca publique a chave ou o ledger.

## Docker

```powershell
docker build -t getnet-brasil .
docker run --rm --read-only --tmpfs /tmp:size=64m,noexec,nosuid -p 127.0.0.1:8000:8000 -e GETNET_CONTEXT_MODEL=0 -e GETNET_WEB_SEARCH=0 getnet-brasil
```

Alternativa gratuita: `docker compose up --build`. O contêiner usa usuário não-root e inclui apenas código e corpus permitidos por `.dockerignore`; não incorpora `.env`, credenciais, testes ou relatórios. O comando padrão inicia `app.context_api:app`. Ativar o modelo exige fornecer variáveis e arquivos de preço/ledger no runtime, nunca no build.

Sessões no tmpfs desaparecem ao remover o contêiner. Para persistência demonstrativa, configure volume gravável em `GETNET_CONTEXT_DB` e preserve também a chave `.key` adjacente. Mantenha esta API de demonstração restrita ao ambiente local.

### Sequência de conferência do contêiner

1. Execute `docker build -t getnet-brasil .` na raiz do repositório. O Dockerfile instala as dependências da aplicação; não há compilação separada do código Python.
2. Inicie pelo `docker run` acima **ou** por `docker compose up --build`, não ambos na mesma porta. No comando `docker run`, modelo e busca online estão explicitamente desligados; no Compose fornecido, permanecem desligados pelos padrões da aplicação.
3. Em outro terminal, confira `http://127.0.0.1:8000/health` antes de enviar um pedido. No modo gratuito, espere `knowledge: "rag"`, `web_search_enabled: false` e `context_interpreter_enabled: false`.
4. Envie o exemplo de `POST /chat` da próxima seção e confira resposta, fontes, rota e indicação de dados fictícios. O health confirma configuração/inicialização, não disponibilidade do provedor nem qualidade de todas as respostas.
5. Encerre o `docker run` com `Ctrl+C`; para o Compose, use `Ctrl+C` e `docker compose down`. Os comandos não publicam a aplicação externamente.

No PowerShell, a conferência do health é:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Em Linux/macOS com curl:

```bash
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  --data '{"message":"Compare Get Clássica e Get Smart no Brasil","user_id":"cliente1988"}'
```

Para ativar a busca pública sem modelo, recrie o contêiner trocando apenas `GETNET_WEB_SEARCH=0` por `GETNET_WEB_SEARCH=1` no `docker run`; isso passa a permitir consultas HTTPS externas e não deve ser confundido com o modo gratuito offline dos verificadores. Para modelo, siga [os dois caminhos de configuração e seus limites distintos](docs/MODELO_E_FONTES.md): não basta inserir uma chave, nem o Compose fornecido repassa automaticamente as variáveis do seu shell. Arquivos de configuração/ledger precisam de caminhos e permissões válidos dentro do contêiner. Não monte credenciais na imagem nem publique a API demo em produção.

## API e exemplos

| Endpoint | Entrada e resultado |
|---|---|
| `GET /health` | Estado, modo de conhecimento, busca e `context_interpreter_enabled` efetivos; não consulta a disponibilidade do provedor. |
| `POST /chat` | `message` e `user_id`; resposta stateless. |
| `POST /context/chat` | Mesmos campos e `session_id` opcional; devolve ID opaco para continuar a sessão. |
| `POST /context/reset` | `message: "reset"`, `user_id` e `session_id`; limpa a sessão correspondente. |

Exemplo em outro PowerShell:

```powershell
$body = @{ message = 'Compare Get Clássica e Get Smart no Brasil'; user_id = 'cliente1988' } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/chat -Method Post -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body))
```

Para continuar uma conversa, envie a `/context/chat` o `session_id` recebido, com o mesmo identificador sintético. `/chat` retorna `answer`, `sources`, `route`, `status`, `modo`, `simulated_data`, `eventos` e `request_id`; o endpoint contextual inclui sessão, modo, validação e `traces`, sem expor o estado completo.

Entradas inválidas recebem 422; identidade de sessão incompatível, 403; conflito de versão, 409; capacidade ocupada, 429; indisponibilidade, 503. `user_id` **não é autenticação real**. As fixtures de suporte são acessíveis apenas pelas identidades de demonstração `cliente1988`/`demo_A`.


### Identidades de demonstração e sessões

Para testar **dados fictícios de suporte**, use `user_id: "cliente1988"` ou `user_id: "demo_A"`. Os dois identificadores selecionam **a mesma loja fictícia**, não dois clientes diferentes:

| Identificadores aceitos | Cenário de suporte |
|---|---|
| `cliente1988` ou `demo_A` | Recebíveis fictícios de R$ 1.250,00 e terminal `DEMO-A-001`, estado `online`. |

Esses valores são fixtures de demonstração, não informações obtidas de uma conta Getnet. Outros IDs não habilitam essas consultas; perguntas públicas podem ser atendidas conforme o escopo. Não use CPF, credenciais ou dados reais.

- **`user_id`:** identificador sintético fornecido pelo testador. Não comprova quem está fazendo a requisição.
- **`session_id`:** identifica uma conversa. Omita no primeiro `POST /context/chat`; o servidor gera e devolve o valor. Nos próximos turnos, reutilize-o com **o mesmo `user_id`**, inclusive sem trocar entre os dois aliases.
- **`request_id`:** identifica uma execução para rastreamento, não o cliente nem a conversa. Não deve ser enviado como `session_id`.

O vínculo entre sessão e identificador rejeita combinações incompatíveis, mas **não é autenticação**: alguém que conheça ambos ainda não passa por login. Em produção, a identidade teria de vir de autenticação e autorização no servidor. `POST /chat` é stateless e não cria continuidade de conversa.

**Três fontes de informação diferentes:** o RAG recupera documentos públicos; o Support consulta fixtures por ferramentas de leitura; o contexto em SQLite guarda o estado conversacional validado. O RAG não contém contas de clientes, e uma informação relatada na conversa não se transforma em operação bancária confirmada.

#### 1. Consultar o suporte fictício

Com a API local iniciada, em PowerShell:

```powershell
$body = @{ message = 'Qual o total dos meus recebiveis?'; user_id = 'cliente1988' } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/chat -Method Post -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body))
```

Em Linux/macOS:

```bash
curl --fail http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  --data '{"message":"Qual o total dos meus recebiveis?","user_id":"cliente1988"}'
```

Confira o aviso de simulação, o total fictício e o evento da ferramenta `consultar_recebiveis`. Não interprete a resposta como saldo real ou promessa de depósito.

#### 2. Criar e reutilizar uma sessão em dois turnos

No mesmo PowerShell, o primeiro pedido não envia sessão; o segundo usa a devolvida pelo servidor:

```powershell
$body1 = @{ message = 'Qual o total dos meus recebiveis?'; user_id = 'cliente1988' } | ConvertTo-Json
$turno1 = Invoke-RestMethod http://127.0.0.1:8000/context/chat -Method Post -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body1))
$turno1 | ConvertTo-Json -Depth 20

$body2 = @{ message = 'Meu terminal esta online?'; user_id = 'cliente1988'; session_id = $turno1.session_id } | ConvertTo-Json
$turno2 = Invoke-RestMethod http://127.0.0.1:8000/context/chat -Method Post -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body2))
$turno2 | ConvertTo-Json -Depth 20
$turno1.session_id -eq $turno2.session_id
```

A última comparação deve retornar `True`. O segundo pedido consulta o terminal fictício. As duas perguntas são autocontidas de propósito: funcionam no modo sem modelo e demonstram **reutilização da sessão**, não compreensão semântica do histórico por LLM.

Sem `GETNET_CONTEXT_MODEL=1` e sua configuração completa, o interpretador contextual está desligado; o sistema informa a limitação e não deve ser avaliado como se resolvesse referências como “e aquele de antes?” pela memória. Para avaliar continuidade semântica, habilite o caminho contextual conforme [Modelo e fontes](docs/MODELO_E_FONTES.md), com orçamento explícito, e confira validação/traces. Reutilizar um ID, por si só, não comprova entendimento do contexto.

## Testes

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -B -m scripts.verify_delivery --output _local/http.json
.\.venv\Scripts\python.exe -B -m scripts.verify_docker --image getnet-brasil --output _local/docker-http.json
.\.venv\Scripts\python.exe -B -m scripts.examples.demo_grafo_rag
```

Os verificadores iniciam e encerram suas instâncias e exigem modelo/busca desligados antes de enviar mensagens. Use `verify_delivery --url http://127.0.0.1:8000` para uma instância já iniciada. A suíte cobre contratos, grafo, RAG, contexto, falhas controladas, privacidade e conectividade. Mocks/replays não comprovam novas gerações; HTTP 200 não comprova resposta correta. Consulte a [estratégia de testes](tests/README.md) e as [evidências por versão](docs/VALIDACAO_ENTREGA.md) e a [validação com modelo real](docs/VALIDACAO_MODELO.md).

### O que executar e o que cada resultado comprova

- **Suíte Python:** execute no host com as dependências instaladas. Cobre unidades e integrações com modelos/transportes controlados; não consome geração paga.
- **HTTP local:** `verify_delivery` sem `--url` inicia uma instância isolada, configura RAG sem modelo/busca, verifica os contratos e encerra somente seu processo. Para testar uma instância existente, use `--url http://127.0.0.1:8000 --output _local/http.json`; nesse caso ela não é encerrada pelo verificador. O health deve confirmar os modos desligados antes de qualquer POST.
- **HTTP no Docker:** construa primeiro a imagem `getnet-brasil`. Execute `verify_docker` **no host**, com Python/dependências e Docker disponíveis; testes e scripts não estão na imagem de produção. O wrapper cria seu próprio contêiner e porta local, registra diagnóstico e remove apenas o contêiner que criou.
- **Grafo demonstrativo:** `scripts.examples.demo_grafo_rag` ajuda a inspecionar a sequência e o resultado; não substitui os testes de HTTP, contexto ou modelo real.

Em Linux/macOS, os mesmos verificadores usam:

```bash
.venv/bin/python -B -m unittest discover -s tests -v
.venv/bin/python -B -m scripts.verify_delivery --output _local/http.json
.venv/bin/python -B -m scripts.verify_docker --image getnet-brasil --output _local/docker-http.json
.venv/bin/python -B -m scripts.examples.demo_grafo_rag
```

Use o código de saída e os arquivos JSON/logs para distinguir aprovação, falha e teste não executado. Falhas de dependência, inicialização ou Docker não devem ser registradas como sucesso. Para a integração, confronte não só o HTTP, mas também a rota esperada, as ferramentas realmente acionadas, as fontes, os estados de recusa/limitação e o isolamento entre sessões. Testes com modelo/rede reais são uma etapa separada, com configuração explícita, orçamento e evidências; os comandos gratuitos acima não comprovam novas chamadas ao modelo.

## Avaliação, confiabilidade e observabilidade

### O que já foi implementado e exercitado

A avaliação distingue **funcionamento técnico** (contratos, sequência, isolamento e HTTP) de **qualidade da resposta** (interpretação, fundamentação, utilidade e transparência). Receber HTTP 200, uma URL ou uma resposta fluente não é critério suficiente de aprovação.

- **Testes em camadas:** unidades e contratos de agentes/ferramentas; integração do grafo e passagem de contexto; RAG, integridade e condições das fontes; sessões, privacidade, erros e concorrência; verificadores HTTP locais e no Docker. Na integração, são conferidos caminho esperado, ferramentas acionadas, fontes, recusas/limitações e isolamento. A [estratégia de testes](tests/README.md) descreve os comandos e a cobertura.
- **Avaliação de respostas:** os dez exemplos do desafio e cenários adicionais foram examinados por interpretação, fundamentação, utilidade e transparência, preservando a política de escopo Getnet Brasil. A [validação real](docs/VALIDACAO_MODELO.md) registra respostas, julgamentos, chamadas e limitações. É uma bateria dirigida, não um conjunto cego independente; casos usados para corrigir o sistema passam a ser regressões.
- **Confiabilidade e proteção:** contratos e limites de entrada, validação das propostas do modelo, revisão/integridade das fontes, tratamento de credenciais das classes testadas, isolamento de contexto e respostas explícitas de limitação ou indisponibilidade. Fallback não é apresentado como nova geração. Falhas de provedor e timeouts também são exercitados por transportes controlados; isso não comprova uma queda real do provedor. Não há garantia universal de segurança, qualidade ou disponibilidade.
- **Evidência por versão:** os relatórios registram 822 testes aprovados por ambiente e, separadamente, 27 chamadas reais de modelo com custo informado de US$ 0,2226865. São resultados das execuções identificadas, não um teste contínuo, SLA ou custo previsto por usuário. Não somamos replays, testes controlados e chamadas reais como se fossem uma única população independente. A rubrica e a nota são internas, não avaliação oficial.

### Sinais disponíveis hoje e seus limites

| Sinal | Onde aparece | O que permite observar |
|---|---|---|
| `request_id`, `route`, `status`, `sources`, `modo` e `simulated_data` | Contrato JSON de `/chat` | Relacionar uma resposta ao caminho executado e distinguir evidência, simulação e limitação. Nem toda resposta HTTP de erro possui esse contrato completo. |
| Agente/ferramenta, status e `duracao_ms` | `eventos` e contratos de trace | Inspecionar os componentes acionados e seus tempos; não é um serviço de tracing distribuído. |
| Sessão, validação e `traces` | Resposta de `/context/chat` | Inspecionar o processamento contextual sem expor o estado completo. Identificadores demo não substituem autenticação. |
| Chamadas, reservas, tokens e custo | Ledger contextual local; artefatos da validação real | Conferir consumo informado e orçamento da rodada. O ledger pode conter payloads sintéticos, não é apagado pelo reset e não deve ser publicado. |
| Configuração e inicialização | `GET /health` | Conferir os modos efetivos. Não mede qualidade nem consulta a disponibilidade do provedor. |

Os sinais acima são instrumentação e artefatos da demonstração. **Não há coletor central de logs, painel, alertas operacionais ou monitoramento de produção implantados.** A validação real usou instrumentação externa para medir ambos os caminhos de modelo; isso não transforma o componente RAG separado em um caminho protegido pelo ledger contextual. Os limites e requisitos distintos estão em [Modelo e fontes](docs/MODELO_E_FONTES.md).

### Estratégia proposta para uma operação em produção — ainda não implementada

Antes de expor a aplicação a clientes reais, seria necessário implementar autenticação/autorização, gestão de segredos, política de retenção e controles de acesso, além de validar as integrações reais. A proposta de monitoramento abaixo não significa que a demo já está pronta para produção.

| Dimensão | Métricas e painel propostos | Alerta e ação propostos |
|---|---|---|
| Qualidade | Conjunto de avaliação versionado, taxa de fundamentação correta, preservação de condições, utilidade e adequação de recusa/esclarecimento, por assunto e versão. Revisão humana de amostras e casos críticos. | Queda sustentada frente à linha de base ou resposta crítica sem fundamento: revisão pelo responsável de produto/conteúdo e responsável técnico; bloquear promoção ou reverter a versão afetada. |
| Confiabilidade | Taxas de erro por endpoint/componente, indisponibilidade de fonte/provedor, respostas sem evidência e frequência de fallback. Separar falha técnica de recusa legítima de escopo. | Aumento sustentado de erro/fallback ou fonte essencial indisponível: notificar operação técnica, investigar pela correlação da requisição e limitar a funcionalidade afetada. |
| Desempenho | Latência ponta a ponta e por etapa (p50/p95), volume, concorrência e respostas 429. Medir sob carga representativa; o tempo de uma amostra não é SLA. | Desvio persistente da linha de base e do objetivo de serviço definido: investigar gargalo/capacidade; não remover proteções para reduzir latência. |
| Custo | Chamadas, tokens, custo informado e reservas pendentes por caminho/modelo/versão; agregação por atendimento quando houver correlação adequada. | Aproximação do orçamento aprovado ou custo desconhecido: suspender novas chamadas pagas conforme política, reconciliar consumo e exigir revisão do responsável técnico/orçamentário antes de retomar. |
| Segurança e dados | Violações de contrato, acessos indevidos e falhas das proteções em testes/amostras autorizadas, sem registrar credenciais ou conteúdo sensível desnecessário. | Suspeita de exposição ou quebra de isolamento: encaminhar imediatamente ao responsável de segurança, conter o acesso e aplicar o procedimento de incidente. |

Os responsáveis são **papéis a designar**, não uma equipe de plantão existente. Cada alerta precisaria de destinatário, janela de avaliação, severidade, procedimento de resposta e registro de resolução. Limiares numéricos e objetivos de serviço devem ser definidos após medir uma linha de base e aprovar orçamento e risco; não foram inferidos dos poucos testes reais.

Para correlação, a evolução proposta é emitir logs estruturados com identificador da requisição, versão, componente, status, duração e referência de fonte, com minimização de dados e acesso restrito. Não copiar mensagens, chaves ou payloads do ledger indiscriminadamente para um painel. Definir retenção, expurgo e auditoria de acesso antes da coleta em produção.

Para cada mudança funcional, a proposta é executar regressões pertinentes e integração, avaliar uma amostra nova não usada no ajuste e comparar qualidade, latência e custo com a versão anterior. Mudanças em modelo, prompt ou corpus exigem avaliação correspondente; alterações apenas documentais não justificam automaticamente nova bateria paga. Violações críticas de segurança ou afirmações sem fonte impediriam promoção; limitações conhecidas devem continuar documentadas. Painéis e alertas complementam, mas não substituem, testes e revisão humana.

## Uso de IA durante o desenvolvimento

Este projeto foi desenvolvido com apoio de ferramentas de inteligência artificial nas etapas de planejamento, implementação e revisão.

Utilizei o ChatGPT para discutir o enunciado, organizar os requisitos em um PRD, estruturar o roadmap e registrar decisões. A ferramenta também apoiou a análise de alternativas de arquitetura, riscos de segurança e critérios de validação.

Na implementação, utilizei o Codex como apoio para desenvolver e revisar o código, executar testes e realizar correções. O trabalho foi iterativo: os requisitos e as decisões eram discutidos, as alterações eram implementadas e os resultados eram confrontados com o enunciado e com as evidências disponíveis.

Ao longo do processo, direcionei o escopo, as prioridades de qualidade e custo e as verificações adicionais, incluindo segurança, comportamento das respostas e execução com o modelo. As respostas das ferramentas de IA não foram tratadas, por si só, como prova de que a solução estava correta: foram complementadas por testes e análise dos resultados.

Esse uso de IA no desenvolvimento é distinto do papel do modelo de linguagem durante a execução da aplicação, descrito na seção de arquitetura.

## Limitações e documentos

- Suporte fictício: sem integração bancária, diagnóstico remoto real, transação financeira ou transferência humana.
- Fontes datadas e cobertura limitada; taxas, elegibilidade e condições individuais podem exigir confirmação em canal oficial.
- Modelo e busca são falíveis. Sem intérprete, a continuidade é limitada; validação de contexto e privacidade não garantem todas as entradas possíveis.
- Credenciais são tratadas pelas proteções implementadas, mas os testes e a demonstração devem usar somente dados sintéticos. Não envie senhas reais.

[Arquitetura](docs/ARQUITETURA.md) · [Matriz de requisitos](docs/MATRIZ_ENTREGA.md) · [Limitações detalhadas](docs/LIMITACOES.md) · [Validação da entrega](docs/VALIDACAO_ENTREGA.md) · [Validação com modelo real](docs/VALIDACAO_MODELO.md)
