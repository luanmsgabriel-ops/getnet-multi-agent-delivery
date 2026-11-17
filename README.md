# Getnet Multi-Agent Support

Atendimento a lojistas Getnet com um supervisor LLM que coordena agentes especialistas (Knowledge com RAG e web search, Support com ferramentas sobre dados do lojista, e Escalation para atendimento humano).

> Versão 3 em construção. Este README é reescrito ao fim da construção, com arquitetura, resultados de avaliação e decisões.

## Quickstart

Requisitos: Docker com Compose v2.

```bash
make setup                 # cria .env com JWT_SECRET aleatório (sem make: python scripts/setup_env.py)
# edite .env e preencha ANTHROPIC_API_KEY
make up                    # docker compose up --build -d
TOKEN=$(make -s token)     # token do lojista fictício cliente1988
curl -s http://127.0.0.1:8000/me -H "Authorization: Bearer $TOKEN"
```

Sem `make`: `docker compose up --build -d` e `docker compose exec -T api python -m app.security.tokens issue --sub cliente1988`.

Documentação interativa da API: <http://127.0.0.1:8000/docs>.

## Desenvolvimento

```bash
uv sync           # Python 3.12 + dependências travadas em uv.lock
uv run pytest     # suíte offline
make lint         # ruff + mypy
```
