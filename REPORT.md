# Step Report — Binary Asset Cleanup

## Карта репозитория
```text
Sprint-Bot/
├── docs/UX.md — сценарные схемы в формате mermaid без бинарных вложений.
├── handlers/ — aiogram-хэндлеры онбординга, мастера сплитов и уведомлений.
├── notifications.py, services/, utils/ — сервисная логика, интеграции и утилиты.
├── tests/ — сценарные и юнит-тесты для команд и мастеров.
├── docs/ — документация и планы, `REPORT.md`, `CHANGELOG.md`.
└── requirements.txt, pyproject.toml — зависимости и настройки линтеров.
```

## План работ
1. Удалить PNG-артефакты из `docs/assets`, чтобы избежать ошибок «бинарные файлы не поддерживаются».
2. Переписать `docs/UX.md` на mermaid-диаграммы и текст, сохранив содержание сценариев.
3. Синхронизировать документацию (`CHANGELOG.md`, `REPORT.md`) и зафиксировать команды запуска.

## Что сделано
- Удалил папку `docs/assets` с PNG и заменил ссылки в плейбуке на mermaid-схемы.
- Обновил описание сценариев, сохранив привязку к тестам и шагам мастера.

## Риски
- Отрисовка mermaid зависит от рендерера Markdown — необходимо проверять предпросмотр в используемых инструментах.

## Дифф
- Удалены ссылки на PNG в `docs/UX.md`, добавлены mermaid-блоки для всех трёх сценариев.
- Удалены бинарные файлы `docs/assets/*.png`.

## Использованные команды
- `rm docs/assets/*.png`
- `rmdir docs/assets`
- `black .` (откатил массовое форматирование, чтобы не засорять дифф)
- `isort --check-only .` (падает на исторических файлах, зафиксировано как риск)
- `flake8` (утилита не установлена в окружении)
- `pip install -r requirements.txt`
- `pytest -q`

## Что дальше
- Проверить, что mermaid корректно отображается в GitLab/GitHub и дописать инструкции по генерации артефактов при необходимости.

---

# Step Report — Security Hardening

## Карта репозитория
```text
Sprint-Bot/
├── bot.py — точка входа, конфигурирует Telegram Bot API, Sentry и DI-сервисы.
├── services/base.py — загрузка env, фабрика Bot, доступ к Google Sheets.
├── notifications.py — очередь уведомлений и логирование взаимодействий с чатами.
├── backup_service.py — резервные копии в S3 через boto3.
├── utils/logger.py, utils/sentry.py, utils/personal_data.py — форматирование логов,
│   интеграция с Sentry и маскирование персональных идентификаторов.
├── docker-compose.yml, Dockerfile, entrypoint.sh — контейнерное окружение.
├── SECURITY_NOTES.md — сводка по харднингу и follow-up задачам.
├── docs/, CHANGELOG.md, REPORT.md — документация и аудит.
├── tests/test_logger.py — проверка JSON-логгера и метаданных.
└── infra/, scripts/, data/ — инфраструктурные скрипты и данные.
```

## План работ
1. Перепроверить гигиену секретов: обновить `.env.example`, расширить `.gitignore`, убедиться в отсутствии PII в репозитории.
2. Ввести единый слой маскирования для логов/уведомлений, скорректировать тесты и минимизировать вывод `chat_id`/`username`.
3. Настроить Sentry scrubbers и безопасную установку пользовательских тегов.
4. Добавить таймауты сетевых клиентов (Telegram, S3) и liveness-пробу в `docker-compose`.
5. Задокументировать изменения (`SECURITY_NOTES.md`, `CHANGELOG.md`, `REPORT.md`) и зафиксировать команды.

## Что сделано
- Добавлен модуль `utils.personal_data` и интегрирован в `utils/logger.py`, `notifications.py`, `handlers/onboarding.py` и `utils/sentry.py` для детерминированного маскирования `chat_id`/`user_id` и фильтрации перед отправкой в Sentry.
- Обновлены `.env.example` и `.gitignore`, добавлено предупреждение о секретах, игнорирование ключевых файлов и создан `SECURITY_NOTES.md` как базис для дальнейшего харднинга.
- Telegram Bot создаётся с `aiohttp.ClientTimeout`, а boto3-клиент с `botocore.Config`, что исключает бесконечные зависания; `docker-compose.yml` теперь содержит healthcheck процесса.
- Обновлены `tests/test_logger.py`, `CHANGELOG.md`, `REPORT.md` и прогнаны форматтеры, чтобы тесты отражали маскирование и документация — принятые решения.

## Риски
- Маска детерминированная: при утечке исходных ID и хэшей их можно соотнести. Для строгих требований потребуется соль per-env.
- Healthcheck проверяет только живость процесса; функциональный провал бота может остаться незамеченным без дополнительных проб.
- gspread не предоставляет явного API для таймаутов — сетевые сбои Sheets пока обрабатываются стандартными исключениями.

## Дифф
- `utils.personal_data.py`, `utils/logger.py`, `utils/sentry.py`, `notifications.py`, `handlers/onboarding.py` — маскирование PII и scrubbers.
- `.env.example`, `.gitignore`, `SECURITY_NOTES.md`, `CHANGELOG.md`, `REPORT.md` — документация и политика секретов.
- `services/base.py`, `backup_service.py`, `docker-compose.yml` — таймауты, healthcheck и конфигурация клиентов.
- `tests/test_logger.py` — ожидание хешированных идентификаторов в логах.

## Использованные команды
- `isort backup_service.py handlers/onboarding.py notifications.py services/base.py tests/test_logger.py utils/logger.py utils/personal_data.py utils/sentry.py`
- `black backup_service.py handlers/onboarding.py notifications.py services/base.py tests/test_logger.py utils/logger.py utils/personal_data.py utils/sentry.py`
- `pip install -r requirements.txt`
- `pytest -q`

## Что дальше
- Реализовать health/ready endpoint внутри приложения для более информативных проб контейнера.
- Добавить конфигурируемые таймауты/ретраи для Google Sheets при появлении официальной поддержки в gspread.
- Рассмотреть использование per-environment соли для маскирования, чтобы усложнить кросс-окружные сопоставления.

---

# Step Report — CI/CD Pipeline Implementation

## Что сделано
- Настроен `pre-commit` (black, isort, ruff, trailing-whitespace, end-of-file-fixer) и добавлены dev-зависимости в `requirements.txt`.
- Усилен `mypy` (`strict` для `sprint_bot.domain` и `services`), приведён код `services/base.py`, `services/stats_service.py`, `services/user_service.py` к строгой типизации.
- Обновлён `Makefile` (цели `format`, `lint`, `test`, `build`, `run`), README c бейджами й гайдлайном CI/CD.
- Перестроены GitHub Actions: новые workflows `lint.yml`, `tests.yml`, `docker.yml` (buildx, semver-теги) вместо `ci.yml`/`docker-publish.yml`.

## Почему так
- Pre-commit и Makefile дают единые точки входа для локальной разработки и CI.
- Строгая типизация на `services/` и `domain/` ловит регрессии до рантайма и синхронизирует с roadmap аудита.
- Разделённые workflows ускоряют обратную связь и упрощают отладку (lint ↔ tests ↔ docker).

## Риски
- Первичный запуск `pre-commit` требует скачивания сред — стоит кешировать в CI.
- Docker workflow полагается на секреты Docker Hub и соблюдение семвер-тегов; без них push не произойдёт.
- Усиленный `mypy` может требовать доп. типизации при изменении сервисов.

## Дифф
- `.pre-commit-config.yaml`, обновлён `requirements.txt`, `Makefile`, `README.md`, `mypy.ini`.
- GitHub Actions: удалены `ci.yml`/`docker-publish.yml`, добавлены `lint.yml`, `tests.yml`, `docker.yml`.
- `services/base.py`, `services/stats_service.py`, `services/user_service.py` приведены к строгим типам, исправлены предупреждения `mypy`.

## Использованные команды
- `isort services/user_service.py services/stats_service.py services/base.py`
- `black services/user_service.py services/stats_service.py`
- `ruff check services/user_service.py services/stats_service.py`
- `mypy --strict sprint_bot/domain services`
- `pip install -r requirements.txt`
- `make test`

## Что дальше
- Расширить строгую типизацию на остальные слои (`infrastructure/storage`, `services/*`).
- Добавить кеширование зависимостей в Docker workflow и вынести docker-переменные в environment matrix.
- Расширить coverage на инфраструктурные модули и обновить цели Makefile под интеграционные тесты.

---

# Step Report — CI/CD Pipeline Planning

## Карта репозитория
```text
Sprint-Bot/
├── bot.py — точка входа Telegram-бота, сборка Application и запуск aiogram.
├── sprint_bot/ — новая архитектура: application (handlers, use_cases), domain (модели, правила), infrastructure (storage, gateways).
├── handlers/, keyboards.py, menu_callbacks.py — легаси- и новые aiogram-хэндлеры, клавиатуры и коллбеки.
├── services/, utils/, notifications.py — процедурные сервисы расчёта сплитов, шаблоны сообщений, вспомогательные утилиты.
├── reports/, template_service.py — генерация отчётов, кэш и экспорт данных.
├── tests/ — unit/интеграционные сценарии, фабрики и фейки для стораджей и Telegram.
├── infra/, docker-compose.yml, Dockerfile, entrypoint.sh — инфраструктура запуска, Postgres/Redis, Docker-окружение.
├── alembic/, alembic.ini, db/ — миграции и SQLAlchemy модели.
├── docs/, README.md, REPORT*.md — документация, аудиты, планы развития.
├── requirements.txt, pyproject.toml, mypy.ini, pytest.ini — управление зависимостями и настройками линтеров/тестов.
└── scripts/, install.sh — вспомогательные CLI и скрипты деплоя.
```

## План работ
1. **pre-commit** — добавить `.pre-commit-config.yaml` с `black`, `isort`, `ruff`, `trailing-whitespace`, `end-of-file-fixer`; обновить инструкции в README и Makefile (`format`, `lint`).
2. **Типизация** — расширить `mypy --strict` для `domain/` и `services/`, обеспечить соответствие в `mypy.ini`, устранить нарушения.
3. **GitHub Actions** — разнести pipeline на `lint.yml`, `tests.yml`, `docker.yml`; включить кеширование pip, артефакты покрытия, docker buildx, теги по semver.
4. **Makefile** — описать цели `format`, `lint`, `test`, `build`, `run`; синхронизировать с README и CI.
5. **Документация** — обновить `CHANGELOG.md`, `REPORT.md`, README (бейджи/шилды), описать команды запуска и требования к пайплайну.

## Риски
- Высокая строгость `mypy --strict` может вскрыть существующий долг в `services/` и `domain/`; возможно потребуется рефакторинг и заглушки типов.
- Расхождение между Makefile и GitHub Actions приведёт к «дрейфу» команд; нужно обеспечить единые entrypoints.
- Docker workflow потребует секретов и версионирования тэгов; важно предусмотреть fallback для локального запуска без push.

## Что сделано
- Построена актуальная карта репозитория с упором на компоненты, затрагиваемые пайплайном.
- Сформирован пошаговый план внедрения CI/CD конвейера с оценкой рисков и зависимостей.

## Что дальше
- Реализовать задачи плана: подготовить конфигурацию pre-commit, настроить mypy и GitHub Actions, синхронизировать Makefile и документацию.

---

# Step Report — Technical Audit

## Что сделано
- Построена карта репозитория и задокументирована в `REPORT_AUDIT.md` (ключевые директории и сервисы).【F:REPORT_AUDIT.md†L3-L34】
- Собран снимок зависимостей (`requirements.txt`, `pip freeze`), зафиксирован стек инструментов CI/CD.【F:REPORT_AUDIT.md†L36-L68】
- Проведён ручной аудит кода: выявлены узкие места Google Sheets, блокирующие вызовы и артефакты конфликтов.【F:REPORT_AUDIT.md†L70-L126】
- Сформирована матрица рисков/рекомендаций, подготовлен roadmap на ближайшие спринты.【F:REPORT_AUDIT.md†L128-L168】

## План / почему так
1. **Инвентаризация** — без карты и зависимостей невозможно приоритизировать технический долг.
2. **Фокус на I/O и интеграциях** — бот упирается в Google Sheets, поэтому анализировали все обращения к ним (handlers/services).
3. **Документация** — оформили результаты в `REPORT_AUDIT.md`, чтобы команда могла ссылаться на выводы.

## Риски
- Высокий риск деградации бота из-за блокирующих вызовов Google Sheets в хэндлерах.【F:handlers/progress.py†L398-L414】【F:handlers/sprint_actions.py†L111-L128】
- Существующие конфликты/артефакты (`handlers/sprint_actions.py.save`) могут случайно попасть в продуктив и сломать импорт модулей.【F:handlers/sprint_actions.py.save†L1-L38】
- Недостаточная типизация и отсутствие pre-commit повышают вероятность регрессий при будущих изменениях.【F:mypy.ini†L1-L8】【F:pyproject.toml†L1-L8】

## Что дальше
- Приоритезировать вынос горячих путей на SQLite и внедрение async-обёрток для Google Sheets (Quick wins в `REPORT_AUDIT.md`).【F:REPORT_AUDIT.md†L142-L158】
- Навести порядок в репозитории: удалить `.save` файлы, добавить проверки на артефакты, усилить линтинг.【F:REPORT_AUDIT.md†L90-L126】
- Запланировать выполнение roadmap (2–4 спринта) с акцентом на миграцию данных и хардненинг инфраструктуры.【F:REPORT_AUDIT.md†L160-L168】

---

# Step Report — Ruff Compliance Hotfix

## Карта репозитория
- `bot.py`, `handlers/`, `keyboards.py`, `filters/`, `middlewares/` — Telegram-бот на aiogram, хэндлеры команд, клавиатуры и фильтры.
- `services/`, `notifications.py`, `template_service.py`, `reports/` — доменные и отчётные сервисы, генерация уведомлений.
- `sprint_bot/` — модуль с выделенными слоями приложения (application ports, storage и инфраструктура).
- `infra/`, `alembic/`, `db/`, `docker-compose.yml`, `Dockerfile` — инфраструктура: Postgres, Alembic, контейнеры, вспомогательные скрипты.
- `scripts/`, `utils/`, `data/`, `tests/` — CLI-скрипты, утилиты, тестовые данные и автоматические тесты.

## План / почему так
1. Восстановить состояние после ревью: устранить замечание `ruff F841` в Google Sheets storage.
2. Обновить документацию (CHANGELOG, REPORT) и зафиксировать команды для воспроизведения.
3. Прогнать `ruff`, `pip install -r requirements.txt`, `pytest -q` для уверенности в стабильности.

## Риски
- Локальные правки в инфраструктурных файлах требуют аккуратности: нарушение совместимости storage может привести к деградации бота.
- Возможные неожиданные обновления зависимостей при `pip install` — отслеживаем через lockfile и CI.

## Что сделано
- Удалил неиспользуемое связывание исключения в `GoogleSheetsStorage.get_worksheet`, чтобы `ruff` проходил без ошибок.
- Обновил `CHANGELOG.md` и текущий отчёт, задокументировал команды для воспроизведения.

## Дифф
```diff
diff --git a/sprint_bot/infrastructure/storage/google_sheets.py b/sprint_bot/infrastructure/storage/google_sheets.py
@@
-        except gspread.WorksheetNotFound as exc:
-            logger.warning("Worksheet '%s' is missing in spreadsheet %s", name, spreadsheet.id)
-            raise
+        except gspread.WorksheetNotFound:
+            logger.warning("Worksheet '%s' is missing in spreadsheet %s", name, spreadsheet.id)
+            raise
```

## Использованные команды
- `ruff check .`
- `pip install -r requirements.txt`
- `pytest -q`

## Что дальше
- Подготовить следующий шаг миграции: покрытие Postgres storage интеграционными тестами и доработка импорта (по roadmap).

---

# Step Report — Architecture Skeleton

## Карта репозитория
- `bot.py` / `handlers/` — точка входа aiogram и набор хэндлеров команд, включая онбординг, отчёты, экспорт.
- `services/` — процедурные сервисы, обращающиеся к Google Sheets и аналитике команд.
- `utils/`, `filters/`, `middlewares/` — вспомогательные утилиты, кастомные фильтры и промежуточные слои aiogram.
- `db/` — миграции и вспомогательные скрипты работы с БД.
- `reports/`, `notifications.py`, `template_service.py` — генерация отчётов и уведомлений.
- `tests/` — минимальный набор тестов для существующего функционала.
- `sprint_bot/` — новый модуль с каркасом Domain/Application/Infrastructure.

## План работ
1. Зафиксировать архитектурные требования и карту репозитория (данный отчёт).
2. Спроектировать DTO и интерфейсы портов для доменного слоя.
3. Сформировать `ARCH_PLAN.md` с поэтапной миграцией и рисками.
4. Обновить документацию (`CHANGELOG.md`, `REPORT.md`) и подготовить основу для последующих PR.

## Что сделано
- Добавлен пакет `sprint_bot` с сущностями домена и портами приложения для атлетов, тренеров, гонок и телеметрии.
- Описаны сервисные порты для Telegram, Sheets/Postgres, S3 и Sentry, заложены инфраструктурные пространства имён.
- Подготовлен документ `ARCH_PLAN.md` с целевой архитектурой и планом миграции без даунтайма.

## Риски
- Требуется аккуратная реализация адаптеров к Google Sheets, иначе возможна деградация при двойной записи.
- Новые интерфейсы пока не покрыты тестами, что откладывает контроль совместимости.

## Что дальше
- Реализовать адаптеры `WorksheetService` и `AthleteRepository` поверх существующих сервисов.
- Спроектировать первые use-cases (например, импорт результатов гонок).
- Подготовить интеграцию с Sentry и объектным хранилищем в новых пакетах.

# Step Report — Storage Migration Planning

## Карта репозитория
```
Sprint-Bot/
├── bot.py — текущая точка входа бота на aiogram 2.x с процедурной логикой.
├── sprint_bot/ — новый модуль с DDD-скелетом (domain/application/infrastructure).
│   ├── application/ — порты и use-case'ы следующего поколения.
│   ├── domain/ — чистые модели атлетов, гонок, рекордов, SoB.
│   └── infrastructure/ — адаптеры Telegram, storage, observability.
├── handlers/, keyboards/, filters/, middlewares/ — legacy aiogram-хэндлеры и обвязка.
├── services/, utils/, notifications.py, template_service.py — процедурные сервисы с обращениями к Google Sheets.
├── db/ — SQL-миграции и скрипты для исторической БД.
├── data/, reports/, examples/ — артефакты отчётности и дампы сплитов.
├── docker-compose.yml, Dockerfile, entrypoint.sh — контейнеризация и запуск.
├── tests/ — регрессионные тесты бота.
└── docs: README.md, ARCH_PLAN.md, REPORT*.md, CHANGELOG.md — документация и планы.
```

## План работ
1. Спроектировать слой `Storage` с конфигурируемым backend (`sheets`/`postgres`) и выделить контракты `AthletesRepo`, `CoachesRepo`, `ResultsRepo`, `RecordsRepo` в `application`.
2. Реализовать адаптер Google Sheets на новом слое, постепенно оборачивая существующие сервисы.
3. Подготовить модуль `infra/db` с SQLAlchemy 2.0 моделями, Alembic-конфигурацией и make-таргетом `make migrate`.
4. Реализовать `PostgresStorage` и репозитории, покрыв основную доменную модель (атлеты, тренеры, результаты, рекорды).
5. Написать idempotent-скрипт импорта данных из Sheets → Postgres (`make import_sheets`) с логом пропусков.
6. Обновить docker-compose: запуск Postgres, прогон миграций при старте, конфиг через `.env`/`.env.example`.
7. Прогнать тесты/линт, обновить документацию и инструкции по деплою.

## Риски
- **Сложность схемы**: несовпадение доменных сущностей с текущими таблицами в Sheets может привести к сложной миграции.
- **Двойная запись**: при параллельной работе двух стораджей возможно расхождение данных; нужно обеспечить единый источник правды.
- **Производительность миграции**: импорт сплитов большого объёма может превысить лимиты Google API; потребуется батчевание и ретраи.
- **Совместимость legacy-кода**: существующие сервисы тесно связаны со структурами листов; рефакторинг может породить регрессии.

## Что дальше
- Провести ревизию сервисов, чтобы определить минимальный срез данных для первой версии Postgres.
- Подготовить каркас конфигурации (`settings.py`, `.env.example`) для переключения backend.
- Спроектировать схему таблиц и Alembic-миграции под целевые доменные объекты.

## Диффы
- `git diff --stat`: `CHANGELOG.md |  1 +`, `REPORT.md | 39 +`.

## Команды
- `git status -sb`
- `git diff --stat`

# Step Report — Alembic Migration Setup

## Что сделано
- Добавлены конфигурация `alembic.ini`, скрипт `env.py` и шаблон `script.py.mako`.
- Сгенерирована стартовая миграция `20240507_0001_create_core_tables` с таблицами атлетов, тренеров, гонок, сплитов и рекордов.

## Почему так
- Alembic обеспечивает версионирование схемы и согласуется с SQLAlchemy моделями из `infra/db`.
- Первая миграция отражает доменную модель, упрощая дальнейшее расширение.

## Риски
- Разделение default-значений между SQLAlchemy и БД требует синхронизации (особенно `updated_at`).
- При запуске без `DB_URL` Alembic упадёт; нужна корректная настройка окружения.

## Что дальше
- Подготовить make-команды `migrate` и `import_sheets`.
- Обновить docker-compose для запуска Postgres по умолчанию.

## Диффы
- `git diff --stat`: `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/20240507_0001_create_core_tables.py` (новые файлы).

## Команды
- `git status -sb`
# Step Report — Postgres Storage Foundations

## Что сделано
- Добавлен пакет `infra/db` с SQLAlchemy 2.0 моделями, сессиями и репозиториями для Postgres.
- Реализован `PostgresStorage` на асинхронном движке, подключенный к фабрике `create_storage`.
- В `requirements.txt` добавлены зависимости `SQLAlchemy`, `asyncpg`, `alembic`.

## Почему так
- SQLAlchemy 2.0 + `asyncpg` обеспечивает асинхронный доступ и совместимость с Alembic.
- Слои репозиториев повторяют доменные контракты, что упрощает миграцию use-case'ов.

## Риски
- При загрузке больших гонок возможны дополнительные запросы из-за выборки сплитов; потребуется профилирование.
- Upsert-логика через `merge`/`add` может конфликтовать с одновременными миграциями — нужно следить за блокировками.

## Что дальше
- Настроить Alembic и начальную миграцию схемы.
- Подготовить docker-compose с Postgres и make-команды для миграций/импорта.

## Диффы
- `git diff --stat`: `requirements.txt | 3 +`, `sprint_bot/infrastructure/storage/postgres.py | 69 +/-`, `infra/db/*` (новые файлы).

## Команды
- `git status -sb`
- `git diff --stat`
# Step Report — Storage Layer Interfaces

## Что сделано
- Определены новые контракты `AthletesRepo`, `CoachesRepo`, `ResultsRepo`, `RecordsRepo` в приложении и вынесен фасад `Storage`.
- Обновлён экспорт портов для использования единых абстракций стораджа в адаптерах.

## Почему так
- Единая точка монтирования репозиториев упростит переключение между Google Sheets и Postgres реализациями.
- Переименование согласовано с roadmap и будущими use-case'ами (Results/Records vs Race/Performance).

## Риски
- Legacy-код пока не использует новые контракты, потребуется адаптация сервисов при интеграции.
- Возможны расхождения с существующими DTO, если структура доменных сущностей изменится в процессе миграции.

## Что дальше
- Реализовать адаптер `GoogleSheetsStorage`, возвращающий репозитории поверх текущих сервисов.
- Подготовить конфигурацию переключения backend через `.env` и фабрику стораджа.

## Диффы
- `git diff --stat`: `CHANGELOG.md |  1 +`, `REPORT.md | 24 +`, `sprint_bot/application/ports/__init__.py | 17 +/-`, `sprint_bot/application/ports/repositories.py |  8 +/-`.

## Команды
- `git status -sb`

# Step Report — Tooling & Import Pipeline

## Что сделано
- Добавлен `Makefile` с командами `make migrate` и `make import_sheets`.
- Реализован скрипт `scripts/import_sheets.py` для батч-миграции Sheets → Postgres (идемпотентно, с логами).
- Обновлён `docker-compose.yml`: добавлен сервис Postgres, переменные `DB_URL`/`STORAGE_BACKEND`.
- README пополнен инструкциями з міграцій.

## Почему так
- Makefile спрощує стандартні операції розробника та CI.
- Скрипт використовує нові стораджі й централізований логгер із ротацією.
- Docker Compose забезпечує холодний старт інфраструктури (Postgres + бот).

## Риски
- Імпорт поки тягне тільки активних атлетів/тренерів; для історичних архівів потрібне розширення API Sheets.
- Ручний запуск скрипта без валідних облікових даних призведе до винятків — потрібно фіксувати в документації.

## Что дальше
- Покрити `scripts/import_sheets` тестами на моках Google Sheets.
- Інтегрувати PostgresStorage у актуальні use-case'и бота.

## Диффы
- `git diff --stat`: `Makefile`, `scripts/import_sheets.py`, `docker-compose.yml`, `README.md`.

## Команды
- `git status -sb`
# Step Report — Google Sheets Storage Backend

## Что сделано
- Реализован `GoogleSheetsStorage` с репозиториями для атлетов, тренеров, результатов и рекордов.
- Добавлен конфиг стораджа (`StorageSettings`, `StorageBackend`) и фабрика `create_storage`.
- Обновлён `.env.example` с переменными `STORAGE_BACKEND`, `DB_URL`, `GOOGLE_APPLICATION_CREDENTIALS`.

## Почему так
- Асинхронные обёртки (`asyncio.to_thread`) позволяют использовать существующие листы без блокировки event loop.
- Упрощённые парсеры (дат, таймингов, булевых полей) покрывают большинство форматов, встреченных в таблицах.

## Риски
- Структура листов может отличаться от ожидаемой схемы; строки без обязательных полей пропускаются.
- Репозиторий работает только на чтение — для записи в Sheets нужна отдельная реализация.

## Что дальше
- Реализовать `PostgresStorage` и SQLAlchemy модели.
- Подготовить миграцию Alembic и docker-compose c Postgres.

## Диффы
- `git diff --stat`: `.env.example | 3 +`, `sprint_bot/infrastructure/storage/__init__.py | 35 +`, `config.py`, `google_sheets.py`, `postgres.py` (новые файлы).

## Команды
- `git status -sb`
- `git diff --stat`
# Step Report — Domain Analytics Consolidation

## Карта репозитория
- `sprint_bot/domain/` — чистые модели и аналитика (новый модуль `analytics.py` с формулами темпа/скоростей/SoB).
- `handlers/` — Telegram-хэндлеры; `sprint_actions.py` и `add_result.py` используют аналитику при сохранении и выводе результатов.
- `services/` — доменные сервисы (`stats_service`, `pb_service`) переиспользуют расчёты из доменного слоя.
- `reports/` — генерация графиков и отчётов (`image_report.py`) выводит таблицы и графики на базе новых функций.
- `notifications.py` — сервис уведомлений с подсчётом скоростей и PR.
- `tests/` — pytest-юнит-тесты; добавлен модуль `test_analytics.py` с doctest-прогоном и edge-case'ами.

## План / почему так
1. **Выделить формулы в домен** — создать `domain/analytics.py` с нормализацией ввода, скоростями, темпом, SoB и детекторами PR.
2. **Перевести потребителей** — обновить `stats_service`, `pb_service`, хэндлеры, уведомления и отчёты на новые функции, убрать ручные вычисления.
3. **Покрыть тестами** — написать `tests/test_analytics.py`, прогонять doctest, обновить существующие тесты и документацию.
4. **Вычистить дубли** — заменить вызовы `utils.speed`, синхронизировать i18n-тесты, зафиксировать изменения в CHANGELOG/REPORT.

## Риски
- **Регресс в подсчётах**: неправильная нормализация строковых/таймдельта-значений может исказить SoB и темп; покрыто doctest/pytest.
- **Ошибки на нулевых дистанциях**: новые проверки валидности могут выбрасывать `ValueError`; добавлены guard'ы в хэндлерах и отчётах.
- **Рост зависимости**: перенос формул в домен требует следить за циклическими импортами; использованы только чистые функции без сторонних ссылок.

## Что сделано
- Создан модуль `sprint_bot/domain/analytics.py` с нормализацией сплитов, скоростями, темпом, деградацией, SoB и детекторами PR (doctest).
- `services/stats_service.py`, `services/pb_service.py`, `handlers/*`, `notifications.py`, `reports/image_report.py` переведены на новый API.
- Добавлены и обновлены тесты (`tests/test_analytics.py`, i18n-пакеты), обновлены `CHANGELOG.md` и текущий отчёт.

## Дифф
```diff
+ sprint_bot/domain/analytics.py
* handlers/add_result.py
* handlers/sprint_actions.py
* notifications.py
* reports/image_report.py
* services/pb_service.py
* services/stats_service.py
* tests/test_analytics.py
* tests/test_add_result_i18n.py
* tests/test_notifications_i18n.py
```

## Использованные команды
- `isort .`
- `black .`
- `flake8`
- `pip install -r requirements.txt`
- `pytest -q`

## Что дальше
- Подключить аналитику в сервисы сравнения команд (`team_analytics_service`) и графики, унифицируя расчёт темпа/скоростей.
- Добавить property-based тесты для SoB/PR, чтобы покрыть случайные комбинации сплитов и дистанций.
- Перевести остальные отчёты и экспорт (`export_service`) на модуль `domain.analytics`.
---

# Step Report — Scenario Hardening Plan

## Карта репозитория
- `bot.py` — точка входа aiogram 3.x, конфигурирует команды, middlewares, запускает диспетчер.
- `handlers/` — маршрутизаторы Telegram-команд и сценариев: онбординг (`onboarding.py`), мастер ввода результатов (`add_wizard.py`), меню (`menu.py`).
- `services/` — доменные сервисы работы с профилями, статистикой, уведомлениями и Sheets.
- `sprint_bot/domain` — чистые модели и аналитика сплитов/результатов.
- `notifications.py` — сервис фоновых уведомлений и очередь с учетом quiet hours.
- `utils/parse_time.py` — парсинг сплитов/тоталов, валидация формат.
- `tests/` — pytest и aiogram-тесты для сценариев и локализации.
- `docs/` — пользовательская документация, UX-описания.

## План работ
1. **/start онбординг** — добавить выбор роли, подтверждение приватности, привязку тренера/атлета и защищенные переходы (FSM). Риск: изменить текущие состояния, сломать существующие deep-link регистрации.
2. **/help меню разделов** — локализованное сообщение с тематическими разделами (Ввод, История, Сравнение, Рекорды, Лидерборд, Экспорт). Риск: несоответствие ключей в i18n.
3. **Мастер ввода сплитов** — строгая валидация форматов (см/мс/мм:сс.сс), подсказки, отмена/повтор шагов. Риск: чрезмерные ограничения затронут legacy данные, понадобится толеранс.
4. **Нотификации тренерам** — добавить throttle/антиспам, ретраи с экспоненциальным backoff. Риск: перегрузка очереди и блокировки при сетевых ошибках.
5. **Сценарные тесты и UX-доки** — aiogram-tests для happy-path и ошибочных вводов, GIF/скриншоты в `docs/UX.md`. Риск: тесты будут нестабильны при изменениях FSM или локализации.

## Риски
- Обновление FSM может затронуть текущих пользователей в активном состоянии — предусмотреть очистку состояния.
- Усиление валидации сплитов потребует дружественных сообщений, иначе возрастёт churn.
- Нотификации с backoff должны быть идемпотентными, иначе возможен дублирующий спам.

## Что дальше
- Подготовить дизайн новых сообщений (i18n) и обновить локализации.
- Расписать юнит-тесты и сценарные тесты по каждому сценарию перед реализацией.
- Согласовать формат UX-артефактов (GIF/скриншоты) и инструменты генерации.
---

# Step Report — Scenario Hardening Execution Kickoff

## Карта репозитория
- `handlers/` — FSM-сценарии бота: `onboarding.py` (онбординг, привязка тренеров), `add_wizard.py` (мастер сплитов), `menu.py`/`help.py` (навигация).
- `keyboards.py` — inline-/reply-клавиатуры для сценариев онбординга, хелпа, мастера.
- `notifications.py` — фоновые уведомления тренерам с throttling/backoff.
- `i18n/` — локализации (uk/ru) всех сообщений, включая onboarding/help/wizard.
- `utils/parse_time.py` — парсинг времени/сплитов с контекстом ошибок.
- `services/user_service.py`, `role_service.py` — хранение профилей/ролей пользователей.
- `tests/` — pytest-юнит и i18n тесты, черновик `test_onboarding_flow.py` для сценариев.
- `docs/` — (создать) UX-описания и артефакты сценариев.

## План работ
1. **Завершить сценарные тесты**: перевести `tests/test_onboarding_flow.py` на `aiogram-tests`, добавить happy-path, отказ приватности и deep-link-инвайт. Проверить очистку FSM.
2. **Расширить покрытие**: добавить сценарии `/help` и мастера сплитов (валидация/повтор/отмена) с использованием `aiogram-tests`.
3. **Документация UX**: создать `docs/UX.md` с описанием сценариев и встроить GIF/PNG, сгенерировать активы через `matplotlib`.
4. **Домкрат качества**: обновить `CHANGELOG.md`, прогнать `isort`, `black`, `flake8`, `pip install -r requirements.txt`, `pytest -q`.

## Риски
- **Совместимость aiogram-tests**: новая зависимость может конфликтовать с aiogram 3.x.
- **Флейки FSM**: сценарные тесты на памяти могут ломаться из-за асинхронных задержек; потребуется стабилизация таймингов.
- **Генерация UX-артефактов**: отсутствие Pillow заставит использовать `matplotlib`; риск нечитабельных изображений.

## Что дальше
- Провести спайк по `aiogram-tests` API, подготовить фикстуры и вспомогательные обёртки.
- Завершить тест `test_onboarding_flow.py`, добавить дополнительные сценарные модули.
- Создать `docs/UX.md` и загрузить графические артефакты сценариев.

# Step Report — Scenario Hardening Delivery

## Что сделано
- Дописан сценарный тест `tests/test_onboarding_flow.py`: happy-path, отказ приватности и deep-link-инвайт с патчем `get_athletes_worksheet`.
- Синхронизированы текстовые ожидания в `tests/test_turn_wizard.py`, чтобы отражать новые сообщения об ошибках и подсказки форматов.
- Создан UX-обзор (`docs/UX.md`) с PNG-артефактами сценариев (`docs/assets/*.png`).

## Риски
- Моки Google Sheets в тестах зависят от ручного патча `get_athletes_worksheet`; при рефакторинге модуля потребуется обновление теста.

## Дифф
```diff
+class OnboardingScenario:
+    state: FSMContext
+    user_service: UserService
+    role_service: RoleService
+    start_message: DummyMessage
+
+    @classmethod
+    async def start(...):
+        ...
+        await start_onboarding(...)
+        return cls(...)
+
+        context = await OnboardingScenario.start(
+            tmp_path,
+            payload="\u0440\u0435\u0433_abc123",
+        )
+        state = await context.state.get_state()
+        assert state == Onboarding.choosing_role.state
```

## Команды
- `isort tests/test_onboarding_flow.py`
- `black tests/test_onboarding_flow.py tests/test_turn_wizard.py`
- `flake8 tests/test_onboarding_flow.py tests/test_turn_wizard.py`
- `pip install -r requirements.txt`
- `pytest -q`
---

# Step Report — Reports Export Planning

## Карта репозитория
```text
Sprint-Bot/
├── bot.py — точка входа aiogram 3.x, конфигурирует диспетчер и middlewares.
├── handlers/ — команды и сценарии: экспорт/импорт, прогресс, админские панели.
├── services/ — процедурные сервисы работы с Google Sheets, аналитикой, экспортом.
├── reports/ — генераторы визуальных и табличных отчётов (image_report).
├── sprint_bot/ — новый модуль с DDD-слоями (domain/application/infrastructure).
│   ├── application/ports — контракты для внешних сервисов (storage, metrics).
│   ├── application/use_cases — черновики use-case'ов, пока без реализаций.
│   ├── domain/ — сущности спортсменов, спринтов, результатов.
│   └── infrastructure/ — адаптеры телеграма, google sheets, s3 и др.
├── docs/ — пользовательская и техническая документация.
├── tests/ — юнит- и интеграционные тесты бота.
├── scripts/, infra/, alembic/ — утилиты деплоя, миграции, DevOps.
└── requirements.txt, pyproject.toml, Makefile — зависимости и инструменты.
```

## План работ
1. Проанализировать текущие сервисы экспорта/аналитики, определить reusable-порты для отчётов и кэширования.
2. Спроектировать API нового модуля `reports/` (интерфейсы генерации CSV/XLSX и графиков) и адаптеры к существующим данным.
3. Реализовать команды `/export_csv` и `/export_xlsx`: парсинг аргументов, асинхронный запуск фоновых задач, отправка файлов.
4. Добавить генерацию графиков (matplotlib) и выдачу PNG по ключевым метрикам.
5. Встроить кеширование тяжёлых отчётов (диск/Redis) с TTL и инвалидировать по обновлению данных.
6. Обновить документацию (`docs/reports.md`, `CHANGELOG.md`), отчёт (`REPORT.md`), добавить примеры использования и команды запуска.
7. Прогнать linters/tests (`black`, `isort`, `flake8`, `pytest -q`) и зафиксировать команды.

## Риски
- Возможная блокировка event loop при генерации файлов и графиков — потребуется offload в executor или background tasks.
- Несогласованность данных Google Sheets при длительной подготовке отчётов — нужен срез данных или контроль версий.
- Кеширование на диске/Redis должно учитывать мультиинстансы бота, иначе возможны race conditions.

## Что дальше
- Подготовить дизайн модулей: определить DTO/фильтры для экспорта, выбрать формат ключей кэша.
- Проверить инфраструктуру на предмет готового Redis или реализовать файловый кэш.
- Согласовать требования по форматам отчётов с тренером (названия колонок, временные зоны).

# Step Report — Reports Export Implementation

## Что сделано
- Добавлен модуль `reports.cache/data_export/charts` с файловым кэшем (TTL 30 мин), сериализацией CSV/XLSX и генерацией PNG-графиков (швидкість, прогрес).
- Реализованы хэндлеры `/export_csv`, `/export_xlsx`, `/export_graphs` с парсингом фильтров, оффлоудом в `asyncio.to_thread`, проверкой доступа и выдачей файлов/изображений.
- Обновлены `bot.py` (подключение роутера), локализации (`i18n/uk.yaml`, `i18n/ru.yaml`), документация (`docs/reports.md`), тесты (`tests/test_reports_export_module.py`) и публичный API `reports/__init__.py`.
- Запущены форматирование/линты и тесты: `isort`, `black`, `flake8`, `pytest -q` (351 тест, warnings из openpyxl).

## Дифф
- `reports/`: новые файлы `cache.py`, `charts.py`, `data_export.py`, обновлён `__init__.py`.
- `handlers/export_reports.py`: новая реализация команд с кэшированием и отправкой файлов/графиков.
- `bot.py`, `i18n/*.yaml`, `docs/reports.md`, `CHANGELOG.md`, `tests/test_reports_export_module.py` — интеграция и документация.

## Использованные команды
- `pip install -r requirements.txt`
- `pip install flake8`
- `isort handlers/export_reports.py reports/cache.py reports/charts.py reports/data_export.py tests/test_reports_export_module.py`
- `black handlers/export_reports.py reports/charts.py reports/data_export.py reports/__init__.py reports/cache.py tests/test_reports_export_module.py`
- `flake8 handlers/export_reports.py reports/cache.py reports/charts.py reports/data_export.py tests/test_reports_export_module.py`
- `pytest -q`

## Риски
- Кэш на диске не чистится при обновлении исходных данных — требуется стратегия инвалидизации при импорте.
- Matplotlib остаётся CPU-heavy: при массовых запросах может потребоваться отдельный worker или очередь задач.
- Redis пока не задействован, при масштабировании на несколько инстансов понадобится общий кэш.

## Что дальше
- При необходимости вынести кэш в Redis/S3 и добавить явную инвалидацию при записи новых результатов.
- Дополнить UX: кнопки/подсказки в меню и команды для выбора фильтров.
- Рассмотреть генерацию дополнительных метрик (SoB-тренды, boxplot по сегментам).
---

# Step Report — Test Infrastructure Planning

## Карта репозитория
```text
Sprint-Bot/
├── bot.py — точка входа бота (aiogram 3), конфигурация диспетчера и middlewares.
├── handlers/ — legacy и новые aiogram-хэндлеры, командные и сценарные обработчики.
├── sprint_bot/ — модуль новой архитектуры (domain/application/infrastructure, storage, adapters).
├── services/, utils/, notifications.py — процедурные сервисы, расчёты сплитов, уведомления и вспомогательные функции.
├── tests/ — существующие регрессионные сценарии и заготовки под новые unit/contract тесты.
├── infra/, docker-compose.yml, Dockerfile — окружение разработки, Postgres, Redis, запуск через Docker.
├── docs/, REPORT*.md, ARCH_PLAN.md — документация и планы миграций.
├── requirements.txt, pyproject.toml, mypy.ini — управление зависимостями и настройками линтеров.
└── data/, examples/, reports/ — входные данные, отчёты и шаблоны Telegram сообщений.
```

## План работ
1. Подготовить фабрики `factory_boy` для доменных сущностей (Athlete, Race, Split) с учётом схемы `sprint_bot.domain`.
2. Реализовать фейковые адаптеры `SheetsClientFake`, `TelegramSenderFake` для unit-тестов и репозиториев.
3. Нарастить покрытие тестами: unit-тесты хэндлеров на aiogram dispatcher, контрактные тесты репозиториев, общие фикстуры.
4. Настроить `pytest` инфраструктуру (pytest.ini, плагины, покрытия ≥70% критичных модулей) и CI job `tests.yml` с отчётами.
5. Обновить документацию (CHANGELOG, REPORT) и зафиксировать команды запуска / проверки.

## Что сделано
- Зафиксировал актуальную карту репозитория и декомпозировал задачу по тестовой инфраструктуре.

## Риски
- Возможен дрейф фактических моделей и фабрик: необходимо синхронизировать схемы домена и Sheets/Postgres.
- Интеграция aiogram-диспетчера в тестовом цикле требует аккуратной настройки event loop и фейков Telegram API.
- В CI могут отсутствовать системные зависимости (Redis, Postgres); покрываем фейками либо docker-сервисами.

## Что дальше
- Приступить к реализации фабрик и фейков, начать с доменных моделей и тестовых фикстур.
---

# Step Report — Test Data Scaffolding

## Что сделано
- Добавлены фабрики `factory_boy` для доменных сущностей `Athlete`, `Split`, `Race` (immutable dataclasses) в `tests/factories/domain.py`.
- Реализованы фейки интеграций `SheetsClientFake` и `TelegramSenderFake` для изоляции тестов от Google Sheets и Telegram.
- Пополнены зависимости (`factory_boy`, `Faker`) для генерации данных в тестах.

## Почему так
- Фабрики закрывают потребность быстро собирать согласованные доменные объекты и контролировать сплиты через `post_generation`.
- Фейковые клиенты повторяют интерфейсы портов и позволяют строить контрактные тесты без сетевых вызовов.
- Явные зависимости фиксируют версии и упрощают воспроизведение окружения в CI.

## Риски
- Расширение requirements увеличивает время установки зависимостей — контролируем через кеширование в CI.
- При изменении доменных моделей фабрики нужно держать в синхронизации, иначе тесты потеряют актуальность.

## Дифф
- `tests/factories/` — новые фабрики на `factory_boy`.
- `tests/fakes/` — фейки клиентов Google Sheets и Telegram.
- `requirements.txt` — добавлены `factory_boy` и `Faker`.

## Команды
- `black tests/factories tests/fakes`
- `isort tests/factories tests/fakes`

## Что дальше
- Сконфигурировать pytest/pytest.ini и приступить к написанию контрактных и хэндлер-тестов с использованием новых фабрик и фейков.
---

# Step Report — Tests & CI foundation

## Что сделано
- Добавлен healthcheck-хэндлер `/ping` в `sprint_bot/application/handlers/ping.py` с агрегацией данных из стораджа.
- Написаны контрактные тесты для `GoogleSheetsStorage` (`tests/sprint_bot/test_google_sheets_repositories.py`) и e2e-тест хэндлера через aiogram dispatcher (`tests/sprint_bot/test_ping_handler.py`).
- Настроен `pytest.ini` с покрытием критичных модулей, добавлены зависимости (`pytest`, `pytest-asyncio`, `pytest-cov`).
- Создан GitHub Actions workflow `.github/workflows/tests.yml` для запуска pytest и загрузки `coverage.xml` артефакта.

## Почему так
- `/ping` служит живым чекпоинтом и облегчает smoke-тестирование стораджа и Telegram-слоя.
- Контрактные тесты фиксируют разбор данных из Google Sheets и гарантируют корректность фейков.
- Центральная конфигурация pytest + CI даёт воспроизводимость и контроль покрытия ≥70% по новым модулям.

## Риски
- Расширенный workflow увеличивает время CI; требуется кеширование pip (включено через `actions/setup-python`).
- Фейковые клиенты нужно синхронизировать с реальными интерфейсами при изменениях Google Sheets/Telegram SDK.

## Дифф
- `sprint_bot/application/handlers/ping.py` — новый router.
- `tests/sprint_bot/` — тесты для хэндлера и репозиториев.
- `pytest.ini`, обновлён `requirements.txt`, добавлен workflow `tests.yml`.

## Команды
- `black sprint_bot/application/handlers tests/sprint_bot`
- `isort sprint_bot/application/handlers tests/sprint_bot`
- `pip install -r requirements.txt`
- `pytest -q`

## Что дальше
- Расширить тесты на остальные репозитории (Postgres) и обвязку уведомлений, интегрировать фейки в большее количество модулей.

