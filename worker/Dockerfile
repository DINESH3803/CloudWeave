# Build context is the repository root (see deploy/docker-compose.yml):
#   docker build -f worker/Dockerfile .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    STORAGE_DIR=/data/chunks

WORKDIR /app

COPY worker/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# `shared` is a top-level package; `app` is the worker package.
COPY shared ./shared
COPY worker/app ./app

VOLUME ["/data"]
EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
