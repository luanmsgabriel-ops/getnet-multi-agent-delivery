# Matriz técnica da entrega — Getnet Brasil

A versão final e as verificações atuais estão em [Validação](VALIDACAO_ENTREGA.md). A organização documental não altera os contratos abaixo. As evidências de validação identificam a versão testada.

| Requisito / decisão | Implementação e evidência | Limite |
|---|---|---|
| Três papéis de agente e comunicação | Router, Knowledge, Support; contratos em `app/contracts.py`, LangGraph em `app/orchestration.py`; perguntas públicas independentes recebem entrada separada e contexto privado vazio; suíte de roteamento/integração e HTTP | Não exige quarto agente nem framework específico do enunciado |
| RAG de fontes Getnet | Captura HTML/PDF limitada e revisão explícita, JSON/hash, recuperação lexical e apresentação revisada/extrativa; corpus e testes de condições/proveniência | Sem embeddings/GraphRAG; fontes datadas e cobertura comercial parcial |
| Busca complementar | Descoberta filtrada e catálogo oficial Link/antecipação BR, TLS e pertinência | Escopo Getnet Brasil escolhido por Luan; RSS pode ser insuficiente |
| Support com pelo menos duas ferramentas | `consultar_recebiveis`, `consultar_terminal`, contratos e fixtures | Dados fictícios; user_id não autentica cliente real |
| Endpoint POST e JSON útil | `/chat`, `/context/chat`, `/context/reset`, esquema/erros e fontes/eventos | Sem operação bancária ou autenticação de produção |
| Docker e execução | Dockerfile não-root, allowlist, compose e instruções no README | Persistência depende de volume; tmpfs é efêmero |
| Testes e integração | unittest, conjunto portátil dos dez exemplos + regressões e HTTP TCP | HTTP200 e citação não provam resposta completa; modelo real separado |
| README e design | [README](../README.md), [arquitetura](ARQUITETURA.md), [limites](LIMITACOES.md), [modelo/fontes](MODELO_E_FONTES.md) | Vídeo e acesso do avaliador são entregáveis separados |
| Getnet Brasil e pedidos mistos | Política antes de modelo/consulta, país por entidade, esclarecimento e respostas à parte válida | Parsing finito; internacional não é pendência |
| Contexto | Memória por sessão/entidade/incidente, origem/certeza/retração, CAS/MAC e revisão seletiva | Retomada limitada sem intérprete; modelo falível; leitura dos campos pedidos preserva fatos conhecidos e informa os ausentes |
| Guardrails (bônus) | Privacidade, fonte adulterada, injection, ações não suportadas e isolamento | Proteção proporcional ao escopo testado, não segurança universal |
| Observabilidade (diferencial) | Request_id, eventos, rota, fontes, duração, modo e ledger opt-in | Sem dashboard/monitoramento de produção |
| Quarto agente e handoff (bônus) | Não implementados no núcleo | Nenhuma transferência humana é anunciada como realizada |

Clima é redirecionado; euro sem contexto é esclarecido e cotação genérica não é fornecida. A aceitação dessa escolha foi relatada por Luan após consultar o avaliador; não é nota oficial. A fonte DCC permanece íntegra e suas condições não são estendidas a outros mercados.

[Validação atual](VALIDACAO_ENTREGA.md) separa novas execuções, simulações, gerações anteriores e replay. Vídeo e liberação de acesso são etapas finais separadas, não falhas técnicas pontuadas nesta rodada.
