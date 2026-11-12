# Limitações verificadas

Esta é uma demonstração com dados fictícios. Não é canal oficial, não autentica clientes reais e não executa contratação, cancelamento, transferência financeira, configuração remota ou handoff humano. Um quarto agente e handoff são bônus não implementados, não requisitos obrigatórios omitidos.

## Utilidade e contexto

- O modo sem intérprete responde perguntas autocontidas, mas não extrai memória semântica completa. Na matriz Brasil anterior à organização, BRI28/3 perdeu a retomada de uma recusa; BRI27/3 esclareceu honestamente o problema, sem recuperá-lo sozinho. As propostas simuladas passaram, mas isso não prova extração correta por qualquer modelo.
- A amostra real Brasil teve nove turnos completos e um parcial: a fonte não confirmou aceitação/moeda de cobrança de cartão específico. Há cobertura parcial para taxas por modalidade, condições Smart/Pix e custos do Link. Ausência de fonte não autoriza inventar informação.
- O parsing de país/intenção é finito. Negação, múltiplas entidades, ambiguidades e paráfrases possuem regressões, sem garantia para todas as entradas possíveis.
- Algumas respostas extrativas são extensas. A fixture de terminal pode ser dispensável em orientação pública; seu status fictício não diagnostica o terminal do usuário.

## Fontes, operação e privacidade

- Snapshots são evidências datadas, não garantia de vigência comercial. Condições individuais exigiriam integração real autorizada. Catálogo oficial é limitado e o RSS já teve resultados insuficientes; TLS/timeouts podem indisponibilizar fonte.
- Modelo e revisão seletiva podem falhar. O fallback é identificado. Falha com custo desconhecido interrompe o ledger, sem retry; a reserva deve ser reconciliada antes de continuar.
- Ledger pode conter payloads sintéticos e não é apagado pelo reset da sessão. Nunca usar dados reais. Sem volume, o Docker perde sessões ao ser removido. Autenticação, retenção, gestão de segredos e monitoramento de produção estão fora desta demonstração.
- Filtros de credenciais e instruções hostis não são defesa universal. DCC, fontes revisadas e dados por entidade têm controles testados; administrador comprometido com acesso a arquivos/chaves está fora dessa proteção.

## Escopo escolhido

Atendimento somente Getnet Brasil. Fora do assunto ou país: redirecionar; mistos: responder a parte válida; país/intenções relevantes incertos: esclarecer. Clima e cotação genérica não são oferecidos. A aceitação dessa escolha foi relatada por Luan após consultar o avaliador; não é nota oficial. **Atendimento internacional não é uma pendência.** Fontes globais do desafio permanecem como proveniência offline.

Resultados e versões: [validação da entrega](VALIDACAO_ENTREGA.md) e [validação com modelo real](VALIDACAO_MODELO.md). Vídeo e configuração do acesso do avaliador são etapas finais separadas e não foram incluídos nas notas técnicas históricas.

## Limites de composição e validação

Algumas composições legadas de texto livre ainda podem repetir ressalvas. O compositor não apaga trechos de fontes por semelhança. Depósito bancário real e falha externa real do provedor continuam não observados; testes controlados não equivalem a essas operações. Os cenários de conectividade W04/W05 são cobertos como regressões na [validação da entrega](VALIDACAO_ENTREGA.md), sem alegar diagnóstico de equipamento real.
