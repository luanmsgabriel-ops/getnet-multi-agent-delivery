# syntax=docker/dockerfile:1

# ---- build: resolve the locked environment --------------------------------
FROM python:3.12-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
RUN pip install --no-cache-dir uv==0.13.9
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app
COPY corpus ./corpus
# Download the embedding model and embed the knowledge base at build time (offline runtime).
ENV EMBED_MODEL_DIR=/app/models HF_HUB_DISABLE_TELEMETRY=1
RUN .venv/bin/python -m app.rag.store build && chmod -R a+rX /app/models

# ---- runtime: non-root, read-only friendly --------------------------------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    DATA_DIR=/state \
    EMBED_MODEL_DIR=/app/models \
    HF_HUB_OFFLINE=1
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app \
    && mkdir /state && chown 10001:10001 /state
WORKDIR /app
COPY --from=builder /app /app
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
