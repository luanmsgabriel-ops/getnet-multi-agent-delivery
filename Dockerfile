FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYDANTIC_AI_NO_BANNER=1
WORKDIR /app
ARG ENABLE_SEMANTIC=0
COPY requirements.txt constraints-tested.txt requirements-semantic.txt ./
RUN case "$ENABLE_SEMANTIC" in 0) pip install --no-cache-dir -r requirements.txt -c constraints-tested.txt ;; 1) pip install --no-cache-dir --only-binary=:all: --index-url https://pypi.org/simple -r requirements.txt -r requirements-semantic.txt -c constraints-tested.txt ;; *) echo "ENABLE_SEMANTIC must be 0 or 1"; exit 1 ;; esac && pip check
RUN useradd --uid 10001 --create-home appuser && mkdir /state && chown 10001:10001 /state && chmod 700 /state
COPY app/ ./app/
COPY corpus_publico/ ./corpus_publico/
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2)"
CMD ["python", "-m", "app.run", "--host", "0.0.0.0", "--port", "8000"]

