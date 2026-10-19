# Build context is the repository root (see deploy/docker-compose.yml):
#   docker build -f controller/Dockerfile .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY controller/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# `shared` is a top-level package; `app` is the controller package.
COPY shared ./shared
COPY controller/app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
