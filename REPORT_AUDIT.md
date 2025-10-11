# Sprint-Bot Technical Audit

## Repository Overview

| Path | Description |
| --- | --- |
| `bot.py` | Entry point configuring aiogram dispatcher, Sentry, and bot commands; includes custom logging middleware and polling retry logic. |
| `handlers/` | Main conversational flows: result entry, history, reports, onboarding, admin tools; heavy use of Google Sheets for persistence. |
| `services/` | Facade over legacy `services.base` (Google Sheets + bot wiring) and new SQLite-backed services for audit, stats, analytics, IO, queries, turns. |
| `utils/` | Shared helpers for FSM states, time parsing, logging, Sentry, and metadata constants. |
| `notifications.py` & `chat_service.py` | Queueing and delivery helpers for asynchronous notifications and chat logging in SQLite. |
| `keyboards.py` & `menu_callbacks.py` | Inline keyboard builders and callback data models used across handlers. |
| `templates/` & `template_service.py` | Sprint template definitions stored in JSON and exposed via service wrappers. |
| `db/migrations/` | Idempotent SQLite migration scripts for audit and turn analytics tables. |
| `tests/` | Extensive pytest suite covering handlers (via localization stubs), services, analytics, and regression cases. |
| `.github/workflows/` | CI pipelines running Ruff, mypy, and pytest (with coverage + targeted suites) on Python 3.11. |
| `Dockerfile` & `docker-compose.yml` | Container build and runtime definitions (python:3.11-slim base, single-stage build, volume mounts for data/logs). |
| `install.sh` | Bootstrap script installing Docker tooling, cloning repo, preparing `.env`, and launching compose stack. |

## Tooling & Dependencies Snapshot

- **Python runtime:** 3.11 (Docker base image `python:3.11-slim`, CI target).  
- **Telegram framework:** `aiogram==3.4.1` (pinned).  
- **Key packages:** `gspread` + `google-auth` for Sheets, `matplotlib`/`numpy` for analytics, `boto3` for backups, `sentry-sdk`.  
- **Development tools:** `pytest`, `mypy` (loose config with `ignore_missing_imports=True`), `ruff` (only `E`, `F` checks), `black`, `isort`, `pyright` available via `pip freeze`.  
- **Docker:** single-stage image, no non-root user, volumes for `/app/data` and `/app/logs`.  
- **CI:** installs deps via `pip`, runs Ruff, mypy on `services utils`, pytest with coverage >=60%, plus focused turn analytics tests.  
- **Pre-commit hooks:** not present.  
- **Dependency lock:** requirements pinned, but no hash checking / lockfile beyond requirements.

`pip freeze` snapshot (trimmed to project-relevant entries):

```
aiofiles==23.2.1
aiogram==3.4.1
aiohttp==3.9.1
boto3==1.34.106
botocore==1.34.106
google-auth==2.22.0
gspread==5.12.0
matplotlib==3.8.2
numpy==1.26.4
openpyxl==3.1.2
pytest==8.4.1
python-dotenv==1.0.1
ruff==0.12.11
sentry-sdk==1.40.6
```

## Issues & Risks

| # | Severity | Description | Impact | Location | Recommendation |
| - | - | - | - | - | - |
| 1 | High | Blocking Google Sheets calls (`get_all_values`, `update_cell`, `append_row`) executed inline in handlers without `await asyncio.to_thread` or batching. | Freezes the event loop under latency, risks hitting Sheets quotas; bot becomes unresponsive under load. | `handlers/progress.py` lines 399-414; `handlers/sprint_actions.py` lines 111-128, 183-216, 870-975; `handlers/reports.py` lines 122-177; `handlers/results.py` lines 37-86. | Introduce async wrappers that delegate to thread executors, add caching and incremental reads, and persist critical data in SQLite instead of Sheets for hot paths. |
| 2 | High | Legacy worksheet access duplicates data fetches per request; no caching of athlete roster (`get_registered_athletes`) so every lookup hits Sheets. | Amplifies quota usage and latency, making autocomplete flows sluggish and error-prone. | `services/base.py` lines 158-191. | Cache roster snapshots in Redis/SQLite with TTL, refresh asynchronously, and invalidate on imports. |
| 3 | High | Leftover `handlers/sprint_actions.py.save` contains obsolete handlers relying on removed service APIs. | Risk of accidental import or merge conflict, increases maintenance overhead, confuses contributors. | `handlers/sprint_actions.py.save` entire file. | Delete the `.save` artefact and enforce lint/test to fail on stray merge leftovers. |
| 4 | Medium | Module import side-effects (`load_dotenv`, gspread client creation) happen at import time; missing credentials raise runtime errors during startup, blocking tests and tooling. | Reduces ability to run partial unit tests without external creds; complicates dependency injection. | `services/base.py` lines 15-55. | Move environment loading to dedicated config module, lazily construct gspread client with explicit error propagation, allow dependency overrides in tests. |
| 5 | Medium | Long-running CPU-bound Matplotlib rendering invoked directly in handlers. | Large plots block event loop, degrade responsiveness for concurrent updates. | `handlers/progress.py` lines 171-205. | Render plots via `asyncio.to_thread` or pre-generate analytics asynchronously; consider caching generated images. |
| 6 | Medium | `Dockerfile` ships as root, lacks multi-stage build and runtime user hardening; `.env` auto-copy in entrypoint may duplicate secrets unexpectedly. | Increases security surface in production deployments. | `Dockerfile` lines 1-17; `entrypoint.sh` lines 1-20. | Add non-root user, separate builder stage, rely on env injection instead of copying `.env` inside container. |
| 7 | Low | mypy configured with `ignore_missing_imports=True` globally; ruff ignores formatting lint; pre-commit absent. | Type coverage limited; regressions slip past CI. | `mypy.ini` lines 1-8; `pyproject.toml` lines 1-8. | Tighten type checking scope, enable broader Ruff rules, add pre-commit pipeline. |
| 8 | Low | README references `screenshot.png` which is absent. | Broken documentation reduces onboarding clarity. | `README.md` lines 27-28. | Provide actual screenshot or remove reference. |

## Google Sheets Bottlenecks

- **Full-sheet scans** for every request across handlers (`get_all_values` on results/pr/log sheets) lead to high read volumes and latency spikes once the sheet grows beyond ~5k rows.【F:handlers/progress.py†L399-L405】【F:handlers/sprint_actions.py†L111-L128】【F:handlers/reports.py†L122-L177】
- **Per-cell updates** (`update_cell`) incur separate API calls; batch updates are not used, so comment edits scale poorly.【F:handlers/sprint_actions.py†L122-L128】
- **Roster fetches** rebuild athlete caches on each call, multiplying quota usage during menus and wizards.【F:services/base.py†L158-L191】
- **No exponential backoff / retry strategy** beyond basic exception logging, so transient quota errors bubble up as user-facing failures.【F:handlers/progress.py†L398-L414】
- **Consistency gaps** because Sheets is the source of truth while SQLite (analytics) diverges; imports into SQLite (`services/io_service.py`) do not sync back to Sheets automatically.【F:services/io_service.py†L56-L139】

## Quick Wins (0-1 Sprint)

- Wrap all Sheets interactions in async executors with structured retries and timeout budgets.【F:handlers/progress.py†L398-L414】
- Remove stale `handlers/sprint_actions.py.save` file and add CI check preventing `.save` remnants.【F:handlers/sprint_actions.py.save†L1-L38】
- Improve caching for athlete roster and frequently used lookups to cut Sheets traffic.【F:services/base.py†L158-L191】
- Update README assets and document required credentials to reduce onboarding friction.【F:README.md†L27-L45】

## Roadmap (2-4 Sprints)

1. **Data Layer Migration:** Move hot paths (results, PRs, audit) from Google Sheets to SQLite/PostgreSQL, and sync Sheets via background jobs for reporting parity.【F:handlers/sprint_actions.py†L108-L189】【F:services/query_service.py†L34-L120】
2. **Resilient Integrations:** Introduce retry/backoff policy and batching for Sheets via a dedicated gateway service; monitor quotas via logging/metrics.【F:handlers/progress.py†L398-L414】
3. **Observability & Tooling:** Expand lint/type coverage, add pre-commit, enforce docstring standards, and integrate pytest coverage gate aligned with CI.【F:mypy.ini†L1-L8】【F:pyproject.toml†L1-L8】
4. **Container Hardening:** Add non-root runtime user, pinned OS packages, healthcheck, and secrets management via Docker secrets or env injection.【F:Dockerfile†L1-L17】【F:docker-compose.yml†L1-L16】
5. **Performance Analytics:** Offload Matplotlib rendering to worker tasks and pre-compute analytics snapshots stored alongside results for quick retrieval.【F:handlers/progress.py†L171-L205】【F:services/team_analytics_service.py†L1-L99】

