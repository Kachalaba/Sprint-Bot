# OPERATIONS.md — операційні процеси Sprint-Bot

Документ описує, як підтримувати продакшен-інстанс Sprint-Bot: резервні копії, міграції, ротацію ключів та процедуру оновлення.

## Резервні копії

- **Що бекапимо:** Postgres, файли імпорту/експорту, конфіг `.env` (без секретів) та артефакти звітів.
- **Автоматичні бекапи:** `backup_service.py` запускається за розкладом (інтервал `BACKUP_INTERVAL_HOURS`). Результат потрапляє в S3/MinIO з префіксом `S3_BACKUP_PREFIX`.
- **Команда вручну:**
  ```bash
  python -m backup_service --dest s3
  ```
- **Перевірка відновлення:**
  ```bash
  aws s3 cp s3://$S3_BACKUP_BUCKET/sprint-bot/latest.tar.gz - | tar -tz
  ```
- **Локальні бекапи:** для дев-оточення використовуйте `make import_sheets` + `pg_dump` у volume `./backups`.

## Міграції бази даних

- Перед оновленням виконайте:
  ```bash
  pip install -r requirements.txt
  alembic upgrade head
  ```
- Для нових міграцій використовуйте `alembic revision --autogenerate -m "<опис>"` і перевіряйте, що зміни **ідемпотентні**.
- У Docker-середовищі міграції запускаються командою `docker compose run --rm sprint-bot alembic upgrade head`.
- Слідкуйте, щоб схема збігалася з `infra/db/models.py`; тести `tests/test_turn_service.py` і `tests/test_team_analytics.py` виявляють невідповідності.

## Ротація ключів і секретів

- **Telegram `BOT_TOKEN`:** отримайте новий токен у @BotFather, оновіть секрети CI/CD та `.env`, перезапустіть контейнер.
- **S3 доступ:** використовуйте короткоживучі ключі або IAM роль. Після ротації оновіть `S3_ACCESS_KEY`, `S3_SECRET_KEY` і виконайте smoke-тест бекапу.
- **Google Service Account:** створіть новий ключ, оновіть файл, зазначений у `GOOGLE_APPLICATION_CREDENTIALS`. Переконайтеся, що новий ключ має доступ до таблиць.
- **Postgres пароль:** оберіть `ALTER USER postgres WITH PASSWORD '<новий>'`, оновіть `DB_URL` та перевірте підключення через `alembic current`.

Усі секрети зберігайте у менеджері секретів (GitHub Actions secrets, AWS Secrets Manager тощо). Заборонено комітити їх у репозиторій.

## Оновлення продакшену

1. Створіть нову гілку `codex/<feature>-<date>` та реалізуйте зміни з тестами.
2. Перед пушем виконайте:
   ```bash
   pip install -r requirements.txt
   pytest -q
   ```
3. Після мержа оновіть продакшен:
   ```bash
   docker compose pull
   docker compose up -d
   docker compose run --rm sprint-bot alembic upgrade head
   ```
4. Переконайтеся, що healthcheck зелений (`docker compose ps`) і бот відповідає на `/ping`.
5. Оновіть `CHANGELOG.md` і зафіксуйте зміни в `REPORT.md`.

## Моніторинг і алерти

- **Логи:** `utils/logger.py` пише у файл `logs/bot.log` та в stderr для попереджень. Використовуйте `docker compose logs` або централізований збір (ELK).
- **Sentry:** заповніть `SENTRY_DSN`, щоб отримувати помилки й таймаути з aiogram та зовнішніх сервісів.
- **Метрики:** наразі покриваємо функціональними тестами (`pytest -q`). Планується додати Prometheus-ендпоїнт.

## Runbook інцидентів

1. **Бот не відповідає:** перевірте healthcheck, логи й наявність підключення до Telegram (`getUpdates`). Перезапустіть контейнер.
2. **Не приходять сповіщення:** переконайтеся, що `QUIET_HOURS` не перекриває час доби, і черга `quiet_queue` обробляється (`notifications.py`).
3. **Помилки аналізу сплітів:** перевірте останні імпорти з Sheets, протестуйте `make import_sheets` на staging.
4. **Втрачений бекап:** виконайте відновлення з останнього архіву, перевірте контрольну суму та повторно запустіть `backup_service`.

