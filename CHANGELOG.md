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
### Fixed
- Suppressed unused exception binding in Google Sheets storage to satisfy `ruff` static checks.

