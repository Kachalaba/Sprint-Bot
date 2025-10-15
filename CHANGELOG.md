# Changelog

## [Unreleased]
### Added
- Added `/ping` healthcheck handler, pytest-based contract tests, and CI workflow exporting coverage.
- Added тестовые фабрики и фейковые клиенты Sheets/Telegram для unit-тестов.
- Planned тестовую инфраструктуру (фабрики, фейки, pytest/CI) и задокументировано в `REPORT.md`.
- Planned CI/CD pipeline rollout: pre-commit hooks, strict mypy, GitHub Actions раздельные пайплайны и обновление Makefile/README.
- Added `.pre-commit-config.yaml`, dev-зависимости (black, isort, ruff, mypy, pre-commit) и README-бейджі CI/CD.
- Added GitHub Actions workflows `lint.yml`, `tests.yml`, `docker.yml` (buildx + semver-теги) вместо монолитного `ci.yml`/`docker-publish.yml`.
- Technical audit report summarised in `REPORT_AUDIT.md` and `REPORT.md`.
- Added architecture migration plan (`ARCH_PLAN.md`) and domain/application/infrastructure skeleton.
- Repository map and storage migration roadmap documented in `REPORT.md`.
- Defined storage layer contracts (`AthletesRepo`, `CoachesRepo`, `ResultsRepo`, `RecordsRepo`) and `Storage` facade.
- Added Google Sheets storage implementation with configurable backend selection via `.env`.
- Introduced Postgres storage layer (SQLAlchemy models, repositories) and updated dependencies.
- Added Alembic configuration and initial migration for Postgres schema.
- Added migration tooling (`Makefile` targets) and batch import script from Sheets to Postgres.
- Added `sprint_bot.domain.analytics` with canonical swim metrics and dedicated tests.
- Added onboarding scenario tests (`tests/test_onboarding_flow.py`) and UX playbook с mermaid-диаграммами в `docs/UX.md`.
- Added async export module with `/export_csv`, `/export_xlsx`, `/export_graphs`, caching, tests, and docs (`docs/reports.md`).

### Changed
- Reused domain analytics across handlers, reports and notifications to remove duplicated formulas and improve consistency.
- Заменён набор PNG-скриншотов в UX-плейбуке на mermaid-диаграммы, чтобы избежать ограничений на бинарные файлы.
- Reworked Makefile (`format`, `lint`, `test`, `build`, `run`), ужесточён `mypy` (`strict` для `sprint_bot.domain` и `services`), типизированы сервисы (`base`, `stats_service`, `user_service`).
### Fixed
- Suppressed unused exception binding in Google Sheets storage to satisfy `ruff` static checks.

