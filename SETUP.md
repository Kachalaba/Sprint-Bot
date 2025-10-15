# SETUP.md — запуск Sprint-Bot з нуля

Документ описує повний шлях розгортання Sprint-Bot: від клонування репозиторію до запуску бота в Docker. Усі приклади наведені для macOS/Linux; для Windows використовуйте PowerShell або WSL.

## Попередні вимоги

| Компонент | Версія | Примітки |
| --- | --- | --- |
| Python | 3.11+ | Рекомендується встановити через `pyenv` або `asdf` |
| pip | 23+ | Оновіть `python -m pip install --upgrade pip` |
| Docker | 24+ | Необов'язково для локального запуску без контейнерів |
| Git | 2.40+ | Для клонування репозиторію |

Також знадобиться **Telegram Bot API токен** (отримайте в @BotFather) та **Google Cloud service account** з доступом до Sheets, якщо плануєте синхронізацію.

## Швидкий старт

1. Клонуйте репозиторій і перейдіть у каталог:
   ```bash
   git clone https://github.com/kachalaba/Sprint-Bot.git
   cd Sprint-Bot
   ```
2. Створіть та активуйте віртуальне середовище (опційно, але бажано):
   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate
   ```
3. Встановіть залежності та перевірте тестовий набір:
   ```bash
   pip install -r requirements.txt
   pytest -q
   ```
4. Скопіюйте та заповніть конфіг:
   ```bash
   cp .env.example .env
   ```
   Після цього відредагуйте `.env`, додавши Telegram токен, список адміністраторів і параметри сховища (Sheets або Postgres).
5. Запустіть бота:
   ```bash
   python bot.py
   ```
6. Перевірте в Telegram команду `/start` — бот має відповісти меню.

## Docker сценарій

1. Переконайтеся, що `.env` налаштований (див. попередній розділ).
2. Запустіть збірку та піднімання сервісів:
   ```bash
   docker compose up --build
   ```
3. Здоров'я контейнера перевіряється healthcheck-ом. Логи доступні командою:
   ```bash
   docker compose logs -f sprint-bot
   ```
4. Для оновлення образу використовуйте `docker compose pull && docker compose up -d`.

## Середовище та змінні

| Змінна | Опис |
| --- | --- |
| `BOT_TOKEN` | Telegram Bot API токен (обов'язково) |
| `ADMIN_IDS` | Список ID адміністраторів через кому |
| `SPREADSHEET_KEY` | Ключ Google Sheets із даними команди |
| `STORAGE_BACKEND` | `sheets` або `postgres` для вибору джерела даних |
| `DB_URL` | Підключення до Postgres, якщо `STORAGE_BACKEND=postgres` |
| `GOOGLE_APPLICATION_CREDENTIALS` | Шлях до JSON ключа service account |
| `S3_*` | Доступ до S3/MinIO для резервних копій |
| `QUIET_*` | Конфігурація «тихих годин» та інтервалів сповіщень |
| `ENV` | Назва середовища (`production`, `staging`, `local`) |

Не зберігайте готовий `.env` у репозиторії; використовуйте секрети CI/CD або менеджер паролів.

## Google Sheets та Google Cloud

1. Увійдіть у Google Cloud Console та створіть **Service Account**.
2. Додайте роль `Editor` або granular-доступ до Google Sheets API.
3. Згенеруйте JSON ключ, збережіть його поза репозиторієм (наприклад, `~/secrets/sprint-bot-creds.json`).
4. Поділіться Google Sheet із адресою service account (`<name>@<project>.iam.gserviceaccount.com`).
5. Встановіть `GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/sprint-bot-creds.json`.

## Міграції та дані

- Створіть/оновіть схему Postgres:
  ```bash
  make migrate
  ```
- Імпортуйте історичні результати із Google Sheets:
  ```bash
  make import_sheets
  ```
- Переконайтеся, що Postgres доступний (локально або в Docker). Значення `DB_URL` має містити коректні креденшили.

## Перевірка якості

```bash
make format   # isort + black
make lint     # ruff + mypy (strict для domain/services)
make test     # pytest з покриттям
```

## Типові проблеми

- **`ModuleNotFoundError` під час запуску.** Переконайтеся, що активоване віртуальне середовище і виконаний `pip install -r requirements.txt`.
- **Docker контейнер завершується.** Перевірте лог `docker compose logs -f sprint-bot` і правильність `BOT_TOKEN`.
- **Sheets не синхронізуються.** Валідуйте шлях до JSON (`GOOGLE_APPLICATION_CREDENTIALS`) і доступ service account до таблиці.
- **Тести не запускаються.** Використайте `pytest -q`, переконайтеся в сумісності версії Python і наявності dev-залежностей.

Після виконання всіх кроків бот готовий до роботи та CI/CD pipeline гарантує стабільність при подальших змінах.

