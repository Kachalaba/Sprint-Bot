.PHONY: migrate import_sheets

migrate:
	alembic upgrade head

import_sheets:
	python -m scripts.import_sheets
