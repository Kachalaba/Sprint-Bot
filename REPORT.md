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
