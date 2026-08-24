.PHONY: up down logs migrate test seed backend-shell frontend-install

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f

migrate:
	docker compose exec backend alembic upgrade head

seed:
	docker compose exec backend python -m app.scripts.seed

test:
	docker compose exec backend pytest -q

backend-shell:
	docker compose exec backend bash

frontend-install:
	cd frontend && npm install
