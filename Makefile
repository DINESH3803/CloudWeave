COMPOSE = docker compose --env-file .env -f deploy/docker-compose.yml

.PHONY: help env build up down restart logs ps clean

help:
	@echo "Targets: env build up down restart logs ps clean"

env:  ## create .env from the template if missing
	@test -f .env || cp .env.example .env

build: env
	$(COMPOSE) build

up: env
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

restart: down up

logs:
	$(COMPOSE) logs -f --tail=100

ps:
	$(COMPOSE) ps

clean:  ## stop and DELETE all volumes (chunks + database)
	$(COMPOSE) down -v
