.PHONY: format lint test build run migrate import_sheets

format:
	isort .
	black .

lint:
	ruff check .
	mypy --config-file mypy.ini sprint_bot/domain services

test:
	pytest --cov=sprint_bot --cov=services --cov-report=term-missing --cov-report=xml

build:
	docker build -t sprint-bot:local .

run:
	docker compose up --build

migrate:
	alembic upgrade head

import_sheets:
	python -m scripts.import_sheets
