# Manutenção do protótipo

## Caminho atual e compatibilidade

O caminho de entrega é `app.run` / `challenge_factory`, supervisor e geração documental validada. Os entrypoints anteriores são mantidos por compatibilidade e regressão; não devem ser apresentados como implementações adicionais para o desafio. A configuração efetiva, não o nome do arquivo, identifica a rota usada.

## Simplificação aplicada nesta revisão

O juiz tinha duas representações produzidas pelo modelo para a mesma prova: `segment_audit` e `claim_checks`. Elas podiam divergir, além de a segunda limitar o número de alegações a 12. Agora o contrato de rede usa somente IDs de segmentos no audit. `judge_evidence.checks_from_audit` reconstrói todas as citações literais, preserva propriedade das fontes, contradições e limite explícito de 192 checagens. Não escolhe notas, não contém respostas esperadas e falha de modo inconclusivo se exceder capacidade. O restaurador ainda valida artefatos antigos, sem alterar seus resultados históricos.

Identidade do avaliador é relatada por `RemoteJudge.provenance`. Chamada separada ao mesmo modelo não demonstra independência de família nem revisão humana. Não há seleção automática de outro modelo ou nova despesa.

## Testes a manter e candidatos a consolidar

- `test_structured_judge_wire`: compatibilidade histórica e guardas de privacidade/temporalidade.
- `test_judge_single_evidence`: novo contrato único, texto longo, múltiplas fontes e rejeição de evidência inventada.
- `test_execution_observations`: proveniência operacional, não julgamento semântico.
- Testes de contexto: manter isolamento, reset, restart, falha combinada e paráfrases separados, pois cobrem riscos diferentes.
- Famílias históricas `test_audit_*`, `test_weights*` e `test_delivery*` são candidatas a consolidar por mecanismo. Antes de remover qualquer teste: mapear assertions/fixtures cobertas e comparar cobertura e mutantes; nome parecido não prova redundância. Nada foi removido por contagem.

## Limite de escopo

Não adicionar outra camada de agentes, banco ou painel para subir nota. Reutilizar `quality_report`, `aggregate_file` e o CLI offline do runbook. Resultados controlados provam contratos; generalização semântica, estabilidade e independência exigem evidência real separada. As ferramentas offline aqui descritas não executam chamadas pagas nem publicam alterações.
