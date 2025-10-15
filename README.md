# Sprint-Bot — ваш тренерський штаб у Telegram

[![Lint](https://github.com/kachalaba/Sprint-Bot/actions/workflows/lint.yml/badge.svg)](https://github.com/kachalaba/Sprint-Bot/actions/workflows/lint.yml)
[![Tests](https://github.com/kachalaba/Sprint-Bot/actions/workflows/tests.yml/badge.svg)](https://github.com/kachalaba/Sprint-Bot/actions/workflows/tests.yml)
[![Docker](https://github.com/kachalaba/Sprint-Bot/actions/workflows/docker.yml/badge.svg)](https://github.com/kachalaba/Sprint-Bot/actions/workflows/docker.yml)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB.svg?logo=python&logoColor=white)

Sprint-Bot допомагає тренерам і командам із плавання позбутися хаотичних таблиць та нескінченних чатів. Бот збирає результати спринтів, генерує звіти та нагадує про тренування, а ви фокусуєтесь на роботі з атлетами.

```mermaid
sequenceDiagram
    autonumber
    participant Тренер
    participant SprintBot as Sprint-Bot
    participant Атлет
    Тренер->>SprintBot: /newsprint
    SprintBot->>Тренер: Обрати дистанції й шаблон
    Атлет->>SprintBot: Надсилає результати спринту
    SprintBot->>Атлет: Повертає спліти та рекомендації
    SprintBot->>Тренер: Готує PDF/CSV з підсумками
```

## Цінність для команди

- **Прозорість прогресу.** Спортсмени бачать персональні рекорди й рекомендації одразу після запливу.
- **Контроль за даними.** Результати, шаблони тренувань і резервні копії синхронізуються між Google Sheets та Postgres.
- **Автоматизація рутини.** Нагадування про старти, тихі години, експорт CSV/зображень — усе робиться ботом.
- **Єдина точка правди.** Більше жодних розрізнених документів: тренер, атлет і батьки отримують інформацію в Telegram.

## Ключові можливості

- 🏁 **Спринти за хвилину.** `/newsprint` відкриває реєстрацію, підтягує шаблон дистанцій та запрошує команду.
- 📊 **Аналітика MyRaceData-рівня.** Автоматичний розрахунок сплітів, дельти, прогнозів та графіків у PDF/PNG.
- 🔔 **Розумні сповіщення.** Тихі години, персональні нагадування, push-повідомлення про рекорди та дедлайни.
- 🧩 **Конструктор шаблонів.** Імпорт із Google Sheets чи CSV, готові макети тренувань для груп і індивідуалок.
- ☁️ **Бекапи без стресу.** S3/MinIO, шифрування, контроль версій і автоматичний restore-скрипт.
- 🔐 **Безпека за замовчуванням.** Маскування персональних даних у логах, Sentry-алерти й healthcheck контейнера.

```mermaid
pie showData
    title Приклад розподілу часу по сплітах (50 м)
    "1-й відрізок" : 28.7
    "2-й відрізок" : 29.1
    "3-й відрізок" : 29.0
    "4-й відрізок" : 28.5
```

## Як стартувати

1. Клонуйте репозиторій та виконайте швидку перевірку залежностей.
2. Заповніть `.env` на основі шаблону.
3. Запустіть бот локально або в Docker.

👉 Детальна інструкція «з нуля до продакшену» — у [SETUP.md](SETUP.md).

## Архітектура та процеси

- [ARCHITECTURE.md](ARCHITECTURE.md) — шарова модель (бот → application → domain → infrastructure), зовнішні інтеграції, події.
- [OPERATIONS.md](OPERATIONS.md) — резервні копії, міграції БД, ротація ключів, оновлення та моніторинг.
- [SECURITY_NOTES.md](SECURITY_NOTES.md) — політика секретів і гайдлайни з харднінгу.
- [docs/UX.md](docs/UX.md) — сценарії онбордингу й роботи з ботом.

## Робочі процеси для розробників

- **Якість коду.** `make format` (isort + black), `make lint` (ruff + mypy), `make test` (pytest із покриттям).
- **CI/CD.** GitHub Actions (`lint`, `tests`, `docker`) збирають образи та перевіряють код при кожному пуші.
- **Залежності.** `requirements.txt` містить runtime і dev-пакети; `pyproject.toml` налаштовує форматери та mypy.
- **Міграції й імпорт.** `make migrate` проганяє Alembic, `make import_sheets` підтягує історичні дані з Google Sheets.

## Дорожня карта

- Health/ready endpoint для продакшен-моніторингу.
- Ліниве підключення Google Sheets і кешування запитів.
- Більше інтеграцій для push-панелей (Slack, e-mail, webhooks).

Sprint-Bot створений тренером для тренерів. Підключайте бот, і кожен спринт працюватиме на медалі.

