.DEFAULT_GOAL := help
COMPOSE := docker compose

.PHONY: help setup up demo down logs build install dev test clean

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

setup: ## Create .env from .env.example (never overwrites)
	@test -f .env || cp .env.example .env

up: setup ## Build and start the app in Docker (http://localhost:8501)
	$(COMPOSE) up --build -d
	@echo "App running at http://localhost:8501"

demo: setup ## Start the app plus the demo PostgreSQL database
	$(COMPOSE) --profile demo up --build -d
	@echo "App running at http://localhost:8501 (demo DB: host postgres-demo, user leitor/leitor)"

down: ## Stop all containers
	$(COMPOSE) --profile demo down

logs: ## Follow the app logs
	$(COMPOSE) logs -f app

build: ## Build the Docker image
	$(COMPOSE) build

install: ## Install dependencies locally with uv
	uv sync

dev: install setup ## Run the app locally without Docker
	uv run streamlit run src/app.py

test: install ## Run unit tests with coverage (minimum 60%)
	uv run pytest

clean: ## Remove caches and coverage files
	rm -rf .pytest_cache .coverage htmlcov
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
