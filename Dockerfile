# TrueAI backend image — the same image runs the API, the worker and the scheduler.
#   docker build -t trueai-backend .
#   docker run --env-file .env -p 8000:8000 trueai-backend                          # API
#   docker run --env-file .env trueai-backend celery -A app.workers.celery_app worker --loglevel=info
#   docker run --env-file .env trueai-backend celery -A app.workers.celery_app beat --loglevel=info

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LOG_DIR=""

WORKDIR /srv

RUN useradd --create-home --uid 10001 trueai

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY main.py .
COPY app ./app

USER trueai
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
