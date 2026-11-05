FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PORT=8080

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY public_feed_server.py .
COPY xaus_readonly_api.py .
COPY xaus_readonly_feed.py .

RUN useradd --system --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import os,urllib.request; p=os.getenv('PORT','8080'); urllib.request.urlopen('http://127.0.0.1:'+p+'/health', timeout=3)"]

CMD ["sh", "-c", "exec uvicorn public_feed_server:app --host 0.0.0.0 --port ${PORT:-8080}"]
