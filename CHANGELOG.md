# Changelog

## [Unreleased]
### Added
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
### Fixed
- Suppressed unused exception binding in Google Sheets storage to satisfy `ruff` static checks.

