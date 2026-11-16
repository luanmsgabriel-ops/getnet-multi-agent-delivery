# Operação e avaliação offline do protótipo

Este procedimento consulta provas existentes. Não é um monitor hospedado, não dispara alertas, não corrige dados, não chama provedores nem autoriza gastos. Mantenha relatórios, respostas e logs sanitizados fora do Git. Nunca publique chave, token, dados pessoais ou conteúdo de conta real.

## Comandos de consulta (Bash ou PowerShell, na raiz)

```text
python -B scripts/review_offline_evidence.py exposure
python -B scripts/review_offline_evidence.py stability --input /caminho/privado/records.json
python -B scripts/review_offline_evidence.py deviations --input /caminho/privado/events.jsonl
```

Use caminhos locais Windows quando aplicável. `--output /caminho/privado/novo.json` grava somente arquivo novo; nunca sobrescreve. Sem `--output`, imprime resumo. Falha de leitura/validação retorna código 2 sem remediação. Código 0 significa análise concluída, não saúde aprovada: examine `findings`, `missing_executions` e limitações. O arquivo de eventos deve ser JSONL sanitizado produzido por `app.observability`, não um dump de conversas.

## Exposição do catálogo (8.2)

`evals/cases.json` continua com 40 casos: 10 originais, 10 regressões, 20 rotulados historicamente como holdout. `evals/exposure_registry.json` informa que originais e regressões são conhecidos e os 20 restantes **não têm condição de inéditos verificada**. O catálogo é público e parte foi inspecionada no desenvolvimento. Não há alegação de 20 novos testes cegos. Quando um caso for usado para correção, registre como `known_regression` com base factual; preserve o split histórico para rastreabilidade. Nova revisão de código não apaga exposição. Para avaliar generalização inédita futuramente, é preciso conjunto realmente separado, congelado antes de inspeção; isso não foi executado por este patch.

## Réplicas e estabilidade (8.3)

O modo `stability` reutiliza `evals.quality.quality_report`. Entrada é uma lista JSON de registros já coletados no contrato existente: `case_id`, `replicate`(1–3), `execution_kind`, `dataset_hash`, `manifest_hash`, `packet`, `judgment`. Consulte `scripts/evaluate_quality.py` e `evals/examples` para o fluxo de coleta/importação. Não copie notas para preencher réplicas. Recibos de provedor e vínculo de manifesto precisam ser conferidos separadamente; importação estrutural não atesta execução real.

Agrupamento separa dataset, revisão congelada e execução controlada/real. Versões diferentes não completam três réplicas. Duplicata é rejeitada. Parecer inconclusivo e réplica ausente não entram como aprovação. O denominador previsto é 40×3, com faltantes explícitos; isso não inicia uma campanha. A concordância de três falhas continua falha estável, não acurácia. Três observações tampouco certificam estabilidade universal. Qualquer futura chamada paga requer autorização e teto próprios.

## Desvios e ação do operador (9.5)

| Código | Verificação e próximo passo manual |
|---|---|
| NO_USABLE_EVENTS / INCOMPLETE_CAPTURE | Preserve o arquivo. Confira truncamento, rejeições e correlação. Reúna logs sanitizados faltantes; não invente sucesso ou custo de eventos ausentes. |
| PROVIDER_429 | Pause novas chamadas pagas; confira mensagem limitada do provedor e cota/quota vigente. Não suponha falta de saldo nem troque conta/modelo para contornar limite. Não há retry automático. |
| PROVIDER_5XX | Preserve a tentativa e a reserva incerta. Verifique disponibilidade; nova tentativa só dentro de autorização/teto, sem apagar a falha. |
| CLIENT_HTTP_NON_SUCCESS | Confira rota, credencial/escopo e entrada localmente. Nunca exponha token. HTTP do provedor é contado separado do HTTP cliente. |
| BUDGET_UNCERTAIN | Consulte ledger autoritativo somente leitura. Preserve provisão conservadora; não marque pago/conciliado sem recibo. Não derive saldo da soma de logs. Pare antes de ultrapassar teto. |
| FUNCTIONAL_REVIEW | Leia a resposta e o motivo do componente. Esclarecimento necessário pode estar correto; HTTP 200 ou `finish` não bastam para sucesso funcional. Separe erro do juiz de erro da resposta. |

Antes de retomar, registre privadamente: revisão/hash, horário, código do desvio, evidência sanitizada, decisão e limite autorizado. Se precisar corrigir, use nova revisão e testes focais offline; não altere snapshot de avaliação em andamento. Retomada requer resolução concreta ou limitação assumida, não simplesmente ausência de alerta.

## Verificação offline desta ferramenta

```text
python -B -m unittest discover -s tests -p test_offline_readiness.py -v
```

Testes controlados verificam exposição, três réplicas, separação de versões, rejeição de duplicatas e alertas dry-run. Não provam estabilidade semântica, uma campanha 40×3 ou envio real de notificações. Podem rodar em Docker com `--network none` e montagem somente leitura, como os demais testes do projeto.
