# Estratégia e execução dos testes

Com dependências instaladas conforme [README](../README.md):

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -B -m scripts.verify_delivery --output _local/http.json
.\.venv\Scripts\python.exe -B -m scripts.verify_docker --image getnet-brasil --output _local/docker-http.json
```

A suíte atual contém 828 testes. Os testes cobrem o comportamento entregue, incluindo política e controles de TLS. As contagens e condições da execução registrada estão em [Validação](../docs/VALIDACAO_ENTREGA.md).

Cobertura: três agentes e LangGraph, contratos de duas ferramentas fictícias, períodos, RAG lexical, integridade/condições/mercado das fontes, HTTP e erros, prompt injection, credenciais, contexto por entidade/incidente, correções, persistência e isolamento. A suíte usa transportes/modelos controlados, não chamadas pagas. O tratamento de 402/timeout é simulado e não comprova um incidente real do provedor.

`test_connectivity_w04_w05.py` mantém 16 métodos com variações: senha no aparelho, suporte após redação, negações, país, fonte ausente/adulterada e canário sintético ausente de payload, estado, resposta e logs. `test_brazil_scope.py`, `test_weather.py` e `test_exchange.py` preservam a política de clima/euro e TLS sem fornecer esses serviços.

`data/delivery_cases.json` congela as dez perguntas literais e regressões conhecidas. O verificador executa 23 contratos e oito controles por TCP; verifica conteúdo mínimo, fontes, ferramentas e simulação, além do HTTP200. Não é um holdout cego nem substitui avaliação semântica. W04/W05 são regressões, não novos casos cegos.

O verificador exige RAG, busca desligada e `context_interpreter_enabled=false` antes de qualquer POST; ausência do campo também bloqueia. Readiness usa prazo monotônico configurável (`--startup-timeout`, 90 s padrão, 1–300 s) e preserva diagnóstico/logs. O wrapper Docker remove somente o contêiner que criou.

Resultados da versão validada: [Validação](../docs/VALIDACAO_ENTREGA.md). Chamadas ao modelo real: [Validação do modelo](../docs/VALIDACAO_MODELO.md). São evidências das execuções identificadas, não CI nem prova universal de ausência de falhas.

## Regressao de consulta de estado do terminal (2026-11-12)

`test_terminal_status_regression.py` acrescenta seis testes para consultas privadas de estado, separacao de perguntas mistas, preservacao de perguntas tecnicas e identidade desconhecida. Validacao da correcao: 828 testes passaram; o verificador TCP manteve 23/23 contratos e 8/8 controles. Execucao em Docker com o codigo corrigido montado somente para leitura, imagem de dependencias existente `getnet-readme:20261111`, rede externa desabilitada e modelos desligados. Nao foi um novo build da imagem nem uma nova validacao com provedor real. As evidencias anteriores continuam vinculadas as respectivas versoes.
