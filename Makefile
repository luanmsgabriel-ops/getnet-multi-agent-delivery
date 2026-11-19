.DEFAULT_GOAL := help
MERCHANT ?= cliente1988
OPERATOR ?= operador1
UV ?= uv

help:  ## Show targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

setup:  ## Create .env with a random JWT secret (then add ANTHROPIC_API_KEY)
	python3 scripts/setup_env.py

up:  ## Build and start the API on http://127.0.0.1:8000
	docker compose up --build -d
	@echo "API: http://127.0.0.1:8000/docs"

down:  ## Stop the stack
	docker compose --profile obs down

obs:  ## Start API + Prometheus, Grafana (:3000) and Jaeger (:16686) with tracing on
	OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318 docker compose --profile obs up --build -d
	@echo "Grafana: http://127.0.0.1:3000  Jaeger: http://127.0.0.1:16686  Prometheus: http://127.0.0.1:9090"

load:  ## 10 concurrent merchants for 5 min against the running stack (real model, about US$ 5)
	$(UV) run python -m evals.load.run --users 10 --minutes 5

logs:  ## Follow API logs
	docker compose logs -f api

token:  ## Print a merchant token (MERCHANT=cliente1988)
	@docker compose exec -T api python -m app.security.tokens issue --sub $(MERCHANT)

operator-token:  ## Print an operator token (OPERATOR=operador1)
	@docker compose exec -T api python -m app.security.tokens issue --sub $(OPERATOR) --scopes operator

install:  ## Install the dev environment locally (Python 3.12 via uv)
	$(UV) sync

lint:  ## Ruff + mypy
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run mypy

test:  ## Run the offline test suite
	$(UV) run pytest

.PHONY: help setup up down obs load logs token operator-token install lint test
