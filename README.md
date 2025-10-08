# Sprint-Bot для тренера по плаванию

Sprint-Bot помогает тренерам, спортсменам и плавательным клубам планировать спринты, держать связь с командой и не терять результаты. Бот напоминает о стартах, собирает времена и превращает данные в понятные отчёты — вы сосредотачиваетесь на дорожке, а не на таблицах.

## Как это работает

1. **Создайте спринт в пару касаний.** Тренер запускает команду `/newsprint`, указывает дистанцию (например, 6×50 м кроль) и выбирает группу. Бот тут же открывает регистрацию и шлёт приглашение всей команде.
2. **Используйте шаблоны по стилям.** Сохраните любимые раскладки ("4×25 баттерфляй", "3×100 комбинированный") и вызывайте их командой `/templates`. Участник видит подсказку по каждому отрезку прямо в Telegram и быстрее фиксирует результат.
3. **Отслеживайте прогресс.** Команда `/progress` строит график времени для выбранного спортсмена: видно, как меняется скорость по дорожкам, где ускориться и над чем работать. Итоговое изображение приходит в чат и сохраняется в отчётах.
4. **Автоматизируйте рутину.** Напоминания о контрольных стартах, уведомления об обновлении личных рекордов, тихие часы, чтобы не будить детей поздними сообщениями — всё настраивается переменными в `.env`.

![Пример рабочего экрана](screenshot.png)

## Установка и запуск

1. Склонируйте репозиторий или распакуйте релиз в удобную папку.
2. Запустите установку одной командой:  
   ```bash
   ./install.sh
   ```
   Скрипт проверит Docker, создаст `.env`, попросит ввести токен бота и ID администраторов, затем соберёт контейнер и запустит Sprint-Bot.
3. После первого запуска откройте Telegram, найдите своего бота и отправьте `/start`.

> **Важно.** Перед запуском `docker compose up` скопируйте `.env.example` в `.env` и заполните значения. Docker Compose подхватит этот файл автоматически и остановит развёртывание, если обязательные переменные не указаны.

## Бэкапы, чат и отчёты

- **Резервные копии.** Бот автоматически архивирует базу SQLite в S3-совместимое хранилище. Вы задаёте период в часах, а администратор может запустить резервное копирование вручную командой `/backup_now`.
- **Чат тренера и спортсмена.** Встроенные диалоги помогают оперативно уточнять задания и комментировать попытки прямо из Telegram.
- **Отчёты.** Бот формирует изображения с прогрессом и сохраняет логи попыток — удобно показывать родителям или заносить данные в сезонный план.

Преимущества для разных групп:
- **Дети и любители:** напоминания о тренировках, простая запись результатов, мотивация через личные рекорды.
- **Профики:** контроль темпа, шаблоны по стилям, точная аналитика для подготовки к стартам.

## Под капотом

- Python 3.11
- Docker и docker-compose
- Telegram Bot API (aiogram 3)
- SQLite для базы данных
- Sentry для отслеживания ошибок
- S3-совместимое хранилище для резервных копий
- CI/CD через GitHub Actions

## Советы по использованию

- **Групповые тренировки:** создайте один спринт для всей группы, используйте напоминания и общий чат для обратной связи сразу после заплыва.
- **Индивидуальные занятия:** заведите отдельный шаблон на спортсмена и задавайте персональные цели, отмечайте комментарии прямо в боте.
- **Челленджи и внутренняя лига:** запускайте еженедельные спринты, делитесь графиками прогресса и фиксируйте победителей в отчётах.
- **Статистика за сезон:** выгружайте CSV из меню экспорта, чтобы свести динамику времени по стилям и дистанциям.

## FAQ

**Тестовый запуск в Docker не стартует.**  
Убедитесь, что порты 8443 свободны и команда `docker-compose up -d --build` выполнилась без ошибок. Проверьте логи: `docker compose logs -f sprint-bot`.

**Где взять токен бота?**  
Напишите @BotFather, создайте нового бота и скопируйте выданный токен в `BOT_TOKEN`.

**Как добавить спортсменов списком?**  
Используйте CSV из папки `examples/`. Отправьте файл через команду `/import_athletes`, бот подскажет, если ID отсутствуют.

**Нужны ли Google Sheets?**  
Нет, но если хотите синхронизировать список спортсменов с таблицей клуба, создайте сервисный аккаунт, добавьте файл `creds.json` и заполните `SPREADSHEET_KEY`.

Готово! Настраивайте Sprint-Bot под свой бассейн и экономьте время на бумажной работе.

## Идеи улучшений Sprint-Bot

### 1. Усилить логирование с ротацией файлов

**Что происходит.** Общий хелпер `utils.logger.get_logger` настраивает только JSON-поток в stdout, поэтому в проде нет ротации файлов и разделения уровней, а отдельные сервисы (например, `turn_service`) дублируют настройку `RotatingFileHandler` вручную.

**Что сделать.** Доработать `get_logger`, чтобы он один раз создавал `RotatingFileHandler` (`logs/bot.log`, 5 МБ, 3 архива) для INFO+ и `StreamHandler` на `stderr` для WARNING+, сохранив текущий формат JSON. После этого убрать локальную инициализацию логов из `services/turn_service.py`.

**Codex prompt**
```
You are working in the Sprint-Bot repository.
Goal: update utils/logger.py so that get_logger() configures both a RotatingFileHandler (logs/bot.log, 5 MB, 3 backups, UTF-8) for INFO+ messages and a StreamHandler to stderr for WARNING+ messages while keeping JSON formatting for structured output. Make sure handlers are created only once per logger, reuse the JSON payload we already emit, and ensure log directories exist. After enhancing the helper, remove the bespoke logging bootstrap in services/turn_service.py so it simply imports and uses get_logger().
Requirements:
1. Update utils/logger.py to initialise RotatingFileHandler with JSON output mirroring the current format and add a separate StreamHandler targeting sys.stderr for WARNING+ levels.
2. Ensure handler deduplication works when get_logger() is called multiple times.
3. Remove the manual logging configuration block in services/turn_service.py and replace it with a module-level logger obtained via utils.logger.get_logger.
4. Update or add tests if necessary to reflect the new logging behaviour.
Validation:
- python -m pytest tests/test_logger.py
- python -m pytest tests/test_turn_service.py
```

### 2. Отложить инициализацию Google Sheets в `services/base`

**Что происходит.** Импорт `services.base` сразу валидирует переменные окружения, создаёт Telegram-бота и ходит в Google Sheets. Отсутствующие секреты приводят к ошибкам ещё до запуска тестов или CLI.

**Что сделать.** Перенести создание внешних зависимостей в ленивые хелперы: `get_bot()`, `get_spreadsheet()`, `get_worksheet(name)` и т.д., чтобы тесты могли подменять зависимости без I/O при импорте.

**Codex prompt**
```
You are assisting with Sprint-Bot.
Goal: refactor services/base.py to remove import-time side effects when loading Google Sheets or the Telegram bot. Environment variables should be validated lazily, and helper functions should create clients only when called.
Steps:
1. Move BOT_TOKEN validation and Bot construction into a new get_bot() function that caches the instance.
2. Wrap gspread initialisation into lazy helpers (e.g., get_spreadsheet(), get_worksheet(name)) that load creds.json only on first use and raise descriptive RuntimeError messages instead of import-time failures.
3. Update existing helpers (get_all_sportsmen, get_registered_athletes, get_athlete_name) to rely on the lazy accessors.
4. Provide sensible error handling so tests can monkeypatch the helpers without needing real Google credentials.
Validation:
- python -m pytest tests/test_query_service_i18n.py
- python -m pytest tests/test_leaderboard.py
```

### 3. Сохранять подписки на уведомления между перезапусками

**Что происходит.** `NotificationService` хранит chat_id подписчиков только в памяти, поэтому после деплоя или рестарта все подписки теряются и пользователям нужно подписываться заново.

**Что сделать.** Добавить простое хранилище (например, SQLite `data/notifications.db`), загружать подписчиков при старте и синхронно обновлять базу при subscribe/unsubscribe. Дополнить тесты сценарием повторного старта сервиса.

**Codex prompt**
```
Repository: Sprint-Bot
Task: make NotificationService remember subscribers between restarts.
Implementation plan:
1. Introduce a lightweight SQLite-backed repository (data/notifications.db) that stores chat_id and subscription timestamp. Provide async helpers similar to ChatService/UserService using asyncio.to_thread.
2. Load persisted subscribers during NotificationService.startup() and populate the in-memory set.
3. Update subscribe()/unsubscribe() to write through to the database before mutating the in-memory cache.
4. Cover the behaviour with unit tests (tests/test_notifications.py) verifying that subscriptions survive a new instance initialised against the same database file.
Validation:
- python -m pytest tests/test_notifications.py
- python -m pytest tests/test_notifications_i18n.py
```

### 4. Протестировать S3-бэкапы

**Что происходит.** `BackupService` содержит много логики по расписанию, выгрузке и восстановлению, но покрытие тестами минимальное и не проверяет обработку ошибок S3.

**Что сделать.** Написать интеграционные тесты с подменой клиента boto3 (fake или moto), которые проверяют `backup_now()`, `restore_backup()`, `list_backups()` и уведомления об ошибках.

**Codex prompt**
```
Project: Sprint-Bot
Goal: add comprehensive tests for BackupService upload/list/restore flows using a fake boto3 client.
Work items:
1. Create a FakeS3Client inside tests that records uploads, supports head_object/list_objects_v2/get_object, and raises simulated ClientError for negative scenarios.
2. Refactor BackupService slightly if needed to allow dependency injection of the client (e.g., optional client_factory parameter).
3. Write pytest cases under tests/test_backup_service.py covering successful backup_now(), restore_backup(), list_backups(), and failure notifications when client methods raise.
4. Ensure tests clean up any temporary files created during the run.
Validation:
- python -m pytest tests/test_backup_service.py
```

### 5. Централизовать парсинг конфигурации

**Что происходит.** Переменные окружения читаются во многих файлах (`bot.py`, `notifications.py`, `backup_service.py`), что ведёт к дублированию проверок и расхождению дефолтов.

**Что сделать.** Создать модуль `config.py` с dataclass-структурами для настроек бота, уведомлений, бэкапов и шаблонов, а также функцию `load_config()` с единой валидацией. Модули должны получать готовый конфиг вместо прямых `os.getenv`.

**Codex prompt**
```
Context: Sprint-Bot Telegram assistant.
Objective: create a config.py module that centralises all environment variable parsing and expose a load_config() helper returning a dataclass with sections for bot, backup, notifications, templates, etc.
Actions:
1. Implement Config dataclasses capturing fields currently read in bot.py (_backup_interval_from_env), notifications.py (_load_quiet_hours_from_env, _queue_interval_from_env), and backup_service.py (bucket, prefix, storage_class, endpoint).
2. Replace direct os.getenv calls in those modules with values supplied by the loaded config, wiring through parameters where necessary.
3. Provide defaults identical to the existing behaviour and surface clear ValueError messages when required settings are missing.
4. Add unit tests ensuring load_config() covers positive cases and rejects malformed inputs (e.g., invalid QUIET_HOURS) without relying on global state.
Validation:
- python -m pytest tests/test_notifications.py
- python -m pytest tests/test_backup_service.py
- python -m pytest tests/test_bot_i18n.py
```
