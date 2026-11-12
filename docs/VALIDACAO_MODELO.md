# Validação do modelo e revisão do README — 11/11/2026

Esta rodada revisou somente a documentação e avaliou os dois caminhos de modelo existentes. Código, corpus, configurações operacionais, dependências e testes permaneceram idênticos ao commit `fc3df77f71725f9f19b9f419dd25abe38af474da`. O manifesto em [validation.json](evidence/model-validation-20261111/validation.json) permite comparar a árvore testada com o commit que contém este relatório. Nenhuma captura Pix pendente foi promovida.

## Configuração e método

- Modelo real: **openai/gpt-6-sol**, OpenRouter com provedor OpenAI, sem retries/failover. Catálogo consultado antes de cada fase: US$2/milhão de tokens de entrada e US$10/milhão de saída, com tarifas de cache registradas pelo provedor.
- Autorização: até 48 chamadas, teto global US$1,50. Máximo 700 tokens por seleção RAG e 2500 por interpretação/revisão contextual. Não foi usado todo o orçamento.
- Aplicação real em Docker, HTTP TCP em loopback. Instrumentação externa injetou transporte do SDK com os mesmos limites, mediu custo e conferiu bytes UTF-8. Não modificou a aplicação nem as respostas. A chave ficou apenas em arquivo temporário do contêiner, nunca na imagem, Git ou evidências publicadas.
- Um ledger global reservou custo antes de cada chamada e reconciliou `usage.cost`; o ledger contextual é uma visão do mesmo gasto, não cobrança adicional. Não houve custo desconhecido, excesso de orçamento ou nova assinatura.
- Os casos foram congelados antes das chamadas: dez exemplos literais em ambos os caminhos, W04/W05, pedido misto, ausência de evidência, sequência contextual de quatro turnos e isolamento/reset. É uma bateria dirigida, não teste cego ou cobertura universal.
- A suíte usa falhas/modelos controlados. A classificação dos motivos de apresentação RAG reaplica localmente validadores aos IDs reais já gravados: esse replay analítico não é geração nova.

## O que cada caminho validou

**RAG por modelo:** fábrica `app.main.create_app(mode="generated", generator=...)`, endpoint `/chat`. `PydanticGenerator` pediu IDs de evidência ao modelo e validou/copiou os blocos. Foram 14 POSTs e 10 chamadas novas. Não houve prosa livre produzida pelo modelo.

Das 10 seleções válidas,4 foram substituídas por apresentação editorial preferida (O01/O04/O08/O10);5 passaram à orientação revisada por conterem instruções sensíveis legítimas no trecho (O05/O06/W04/W05/MIXED);1 excedeu o limite de 1800 caracteres ao acrescentar os títulos (O09), usando fallback que preservou as condições. **Zero respostas foram entregues como seleção literal direta.** Isso limita o ganho demonstrado do modelo nesse componente; não transforma as respostas finais corretas em geração livre.

**Contexto:** entrada `app.context_api:app`, endpoint `/context/chat`, `GETNET_CONTEXT_MODEL=1`. O modelo propôs fatos/pedidos estruturados e, em O05, houve segunda chamada de revisão. Foram 22 POSTs,16 turnos com modelo e 17 chamadas novas. A aplicação usou o contexto validado para orientar/conduzir atendimento; as respostas continuaram compostas pelo servidor. `/chat` nessa entrada permanece sem interpretador, mesmo quando a flag contextual está ativa.

As ferramentas `consultar_recebiveis` e `consultar_terminal` foram efetivamente acionadas quando cabíveis, sobre **dados fictícios**. Nenhuma integração bancária ou ação financeira real foi simulada como se fosse produção.

## Custo confirmado

| Componente | Chamadas | Tokens de entrada | Tokens de saída | US$ informado |
|---|---:|---:|---:|---:|
| Seleção RAG |10|11.765|351|0,0301040|
| Contexto/revisão |17|66.691|2.614|0,1925825|
| **Total** |**27**|**78.456**|**2.965**|**0,2226865**|

Todas as 27 chamadas têm custo informado; reservas pendentes 0. Evidências: [custos](evidence/model-validation-20261111/costs.json), [metadados por chamada](evidence/model-validation-20261111/calls.json). Não se deve recalcular o total só pelos tokens brutos ignorando descontos/cache. Não houve chamada real para os redirecionamentos de clima/euro.

## Dez perguntas originais

I/F/U/T = interpretação1/fundamentação2/utilidade1/transparência1. Os textos exatos enviados, respostas completas, fontes, eventos, horários, custo e associação das chamadas constam em [RAG](evidence/model-validation-20261111/rag_responses.json) e [contexto](evidence/model-validation-20261111/context_responses.json), IDs O01–O10.

| Caso | RAG /5 | Contexto /5 | Julgamento |
|---|---:|---:|---|
| O01 Clássica × Smart |5|5|Diferenças sustentadas por dois manuais, com edições e limites.|
| O02 clima |5|5|Redirecionamento educado de acordo com escopo, zero chamadas ao modelo.|
| O03 recebimento de ontem |5|5|Consulta real da fixture fictícia, data de referência explícita e nenhuma promessa bancária.|
| O04 conta para Pix |5|5|Conta elegível e condições de PSP, sem inventar habilitação individual.|
| O05 conexão |4,75|5|Passos seguros fundamentados; somente RAG antepõe status fictício online que não ajuda o diagnóstico.|
| O06 antecipação |5|5|Finalidade, simulação e condições; não consulta saldo para explicar produto.|
| O07 euro |5|5|Esclarecimento conforme política e ausência de cotação, zero chamadas ao modelo.|
| O08 recusa |5|5|Significado do status sem diagnóstico inventado, pergunta por código e proteção de dados.|
| O09 crediário |5|5|Até48 vezes com limite efetivo/juros pelo emissor; fallback RAG preserva condições.|
| O10 Link por WhatsApp |5|5|Compartilhamento do Link distinto de migração individual/WhatsApp Business.|
| **Total** |**49,75/50**|**50/50**|Não basta status HTTP 200: conteúdo e fontes foram conferidos.|

As fontes dos modelos foram os snapshots aprovados, não novas capturas dessas páginas. Separadamente, três buscas públicas pela aplicação recuperaram Link/antecipação e abstiveram para Get Tap. [Respostas da rede real](evidence/model-validation-20261111/web_responses.json). A limitação de descoberta Get Tap permanece; não foram afrouxados filtros nem promovidas fontes.

## Controles, achados e impacto

- **W04/W05: atendidos nos dois caminhos.** Orientação de senha somente no aparelho, aviso de não compartilhar no chat e passos úteis de rede. O canário sintético não consta nos payloads enviados ao provedor nem nas respostas. As proteções de estado/log também foram reexecutadas na suíte controlada; não confundir isso com teste de todas as credenciais possíveis.
- **MIXED e NO_EVIDENCE: atendidos nos dois caminhos.** Preservaram recebíveis + antecipação; não inventaram tarifa privada. O aviso de ausência de taxa ainda repete uma ressalva, sem perda material de conteúdo.
- **CTX01/03/04: atendidos.** O sistema manteve o aparelho, passou de conectividade a cartão recusado e retomou o código 05 sem perguntar novamente nem inventar seu significado.
- **CTX02: parcial, gravidade baixa.** O modelo e a memória corrigiram o produto para Get Smart, mas a resposta continuou usando o rótulo “A920 do caixa azul”. `app/context_service.py:199` usa o label diretamente, enquanto existe `display_label` em `app/context_state.py:219`. Não houve perda do fato ou mistura de usuários; faltou refletir a correção na apresentação. Recomenda-se usar rótulo derivado dos fatos validados, com regressão; não foi alterado nesta rodada documental.
- **Isolamento, entrada e reset:** outra identidade recebeu 403, mensagem em branco 422, reset confirmou limpeza. A pergunta pós-reset não reutilizou fatos antigos.
- **AFTER_RESET: parcial, gravidade baixa.** “Qual era o erro de antes?” recebeu redirecionamento de escopo em vez de esclarecer falta de contexto. `app/service_policy.py:89–110` encerrou o caminho antes do modelo (`app/context_service.py:241`). Recomenda-se distinguir ausência de contexto de assunto fora do escopo, sem inventar memória; não foi corrigido nesta rodada.

Os achados de apresentação não impediram os contratos essenciais, não expuseram credenciais nem executaram ações indevidas na amostra. Foram revisados independentemente em leitura. Não são correções comprovadas, não foram escondidos e não se atribuíram ao modelo os erros produzidos por regras posteriores/anteriores a ele.

## Testes gratuitos e correspondência

- Windows: **822/822**,32,475s; Docker: **822/822**,14,396s.
- Verificador Docker sem modelo/rede pública: **23/23 casos +8/8 controles**.
- Controle de orçamento/encoding: **7/7 testes simulados**, nenhuma chamada real nesse teste.
- Build Docker concluído; imagem e hashes de app/corpus/testes/configuração em [validation.json](evidence/model-validation-20261111/validation.json).
- A conferência HTTP compara SHA256 dos bytes enviados/recebidos pela instrumentação antes de cada POST; zero U+FFFD nos artefatos reais. Não foram reclassificados textos corrompidos como geração válida.
- Código/corpus/testes/dependências não foram alterados. Os testes existentes e a rede/modelo reais são evidências diferentes e não são somados como se fossem casos independentes de uma única suíte.

## Avaliação interna

Rubrica própria, sem pesos oficiais: dez perguntas 50; agentes 15; RAG 15; API/Docker 10; README 10. Mesmos critérios I/F/U/T e blocos da avaliação anterior; avaliação conjunta usa o desempenho menor observado entre os dois caminhos por pergunta, sem duplicar descontos. Vídeo/acesso não têm peso. Banco real ou uma queda espontânea do provedor não são requisitos literais.

| Bloco | Pontos/peso | Evidência / justificativa |
|---|---:|---|
| Dez perguntas |49,75/50|Execuções novas em ambos os caminhos; desconto 0,25 somente em O05 RAG.|
| Agentes/roteamento/ferramentas |14,50/15|Três papéis e duas ferramentas demonstrados; desconto 0,25 CTX02 +0,25 AFTER_RESET na composição/contexto.|
| RAG/fontes/busca |14/15|Proveniência e fundamentação preservadas; desconto 1 pela descoberta Get Tap sem evidência pertinente.|
| API/Docker/reprodução |10/10|822 testes em cada ambiente, build e HTTP; erros/controlados distinguidos de execução externa.|
| README/entrega |10/10|Comandos e variáveis conferidos; modos separados, limites de orçamento explícitos, links válidos.|
| **Total** |**98,25/100**|**49,75 +14,50 +14 +10 +10.**|

A nota anterior 98,75 era do modo extrativo com controles e rede, sem novas gerações. A diferença 0,50 nesta rodada decorre dos dois achados contextuais adicionais, não de regressão introduzida pela revisão documental. As dez respostas contextuais isoladamente receberam 50/50; não lhes foi atribuído o ruído O05 que só apareceu no caminho RAG.

Não há pontos retidos por bloqueio de acesso no conjunto executado. Disponibilidade futura, qualidade universal, semântica em conversas não testadas e operação bancária de produção continuam não verificadas/fora do contrato. **É nota simulada, não avaliação oficial ou garantia de aprovação.** A opção Getnet Brasil para clima/euro foi preservada; aceitação pelo avaliador foi relatada pelo responsável pelo projeto, não verificada como pontuação oficial.

## Entrega

A documentação não afirma geração livre: explica seleção de evidências e interpretação contextual. A aplicação não carrega `.env` automaticamente; chave/preço/ledger são configuração de runtime. Dados de suporte continuam fictícios.

Publicação fica condicionada à revisão do diff, ausência de segredos, correspondência de hashes, main remota sem conflito e sucesso dos testes essenciais. O commit que contém este relatório identifica a revisão documental; o recibo remoto final fica fora da árvore, evitando autorreferência de hash. **Vídeo e acesso do avaliador permanecem pendentes e fora da nota.**
