# Validação da versão final

Rodada documental e validação com modelo real: [resultados de 11/11/2026](VALIDACAO_MODELO.md). Código operacional preservado; 27 chamadas reais, custos e achados discriminados. Os resultados abaixo pertencem à rodada registrada no recibo de validação da entrega.

A suíte corrente contém 822 testes; W04/W05, privacidade, ferramentas e contexto permanecem cobertos. As verificações abaixo pertencem à versão identificada no recibo. Alterações posteriores de documentação e comentários não representam uma nova execução da suíte.

## Verificações da versão registrada

| Verificação | Resultado | Evidência / modo |
|---|---:|---|
| Instalação nova Windows | `pip check` aprovado | Python 3.14.8; requirements + constraints; sem `.env` |
| Suíte Windows limpa | **822/822**, 25.329 s | Modelos/falhas controlados; corpus aprovado |
| Build e suíte Docker | **822/822**, 21.613 s | Suíte sem rede, montagem de testes somente leitura |
| HTTP Windows / Docker | **23/23 + 8/8** por ambiente | TCP real; inclui dez exemplos originais; modelo/busca desligados |
| Conectividade/privacidade HTTP | **30/30** por ambiente | W04/W05 e fronteiras nos dois endpoints; regressões, não holdout novo |
| Revisão independente | Imports e asserções preservados | Leitura estática; nenhum código restante do runtime alterado |
| Chamadas pagas | **0; US$ 0,00** | Não foram autorizadas novas gerações |

[Recibo com hashes, modos e tempos](evidence/delivery-final-20261111/validation.json). Naquela rodada, os 56 arquivos restantes de aplicação/corpus eram byte a byte iguais à baseline e à imagem `sha256:1b6d2b832e9e09d762c4c17bf0faca892ac3ce7c00eccaedaa1e18eaa1969429`. Corpus, DCC e Pix pendente preservados. Não somamos resultados de versões diferentes.

Comandos executados em cópia limpa: `python -m venv .venv`, `python -m pip install -r requirements.txt -c constraints-tested.txt`, `python -m pip check`, `python -B -m unittest discover -s tests -v`, `docker build -t getnet-delivery:final-20261111 .`, `python -B -m scripts.verify_delivery --output _local/http.json` e `python -B -m scripts.verify_docker --image getnet-delivery:final-20261111 --output _local/docker-http.json`.

## Modos e limites

A suíte usa mocks de modelo/rede e dados fictícios. HTTP TCP usa a aplicação real com RAG do corpus aprovado e modelo/busca desligados. Falhas 402/timeout são controladas. Não houve novas chamadas pagas; nenhuma disponibilidade real do modelo ou operação bancária é alegada. A memória semântica completa exige intérprete configurado, distinta do fallback gratuito.

## Interpretação dos resultados

As notas são internas, não oficiais. A avaliação final usa o enunciado e a rubrica congelada antes da pontuação, exclui vídeo/acesso e considera a política de clima/euro aceita segundo relato de Luan. Não exige banco de produção nem incidente real do provedor. A avaliação final é realizada somente sobre a main remota confirmada após publicação.
