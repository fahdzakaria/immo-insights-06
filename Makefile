# Raccourcis développeur — tout passe par docker compose.

.PHONY: up down restart logs ps airflow-shell reset

up:            ## Build + démarre tout le stack
	docker compose up -d --build

down:          ## Stoppe le stack (conserve les volumes)
	docker compose down

restart: down up

logs:          ## Suit les logs de tous les services
	docker compose logs -f

ps:            ## État des services
	docker compose ps

airflow-shell: ## Shell dans le scheduler (pour tester ingestion/dbt à la main)
	docker compose exec airflow-scheduler bash

reset:         ## Stoppe tout et supprime les volumes (⚠ efface la DB Airflow)
	docker compose down -v
