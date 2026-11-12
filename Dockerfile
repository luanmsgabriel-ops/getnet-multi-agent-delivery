FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYDANTIC_AI_NO_BANNER=1
WORKDIR /app
COPY requirements.txt constraints-tested.txt ./
RUN pip install --no-cache-dir -r requirements.txt -c constraints-tested.txt
RUN useradd --uid 10001 --create-home appuser
COPY app/ ./app/
COPY corpus_publico/ ./corpus_publico/
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2)"
CMD ["python", "-m", "uvicorn", "app.context_api:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--limit-concurrency", "16", "--timeout-keep-alive", "5"]
