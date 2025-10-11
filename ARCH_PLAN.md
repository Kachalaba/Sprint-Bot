# Architecture Migration Plan

## Контекст
Монорепозиторий бота управляет онбордингом и аналитикой спортсменов через
Aiogram 3.x. Текущая логика опирается на Google Sheets и процедурные сервисы,
что усложняет развитие и перенос данных. Цель — перейти к модульной
архитектуре со слоями **Domain / Application / Infrastructure**, сохранив
обратную совместимость во время миграции.

## Архитектурные слои
### Domain
- `sprint_bot.domain.models.Athlete` — сущность атлета с базовыми данными и
  персональными рекордами.
- `sprint_bot.domain.models.Coach` — профиль тренера с контактами и статусом.
- `sprint_bot.domain.models.Race` — агрегат гонки со сплитами и метаданными.
- `sprint_bot.domain.models.Split` — элемент гоночного сплита с телеметрией.
- `sprint_bot.domain.models.SegmentPR` — персональный рекорд по сегменту.
- `sprint_bot.domain.models.SoB` — Sum-of-Bests с ссылкой на сегментные PR.

### Application
- `sprint_bot.application.use_cases` — точка входа для интеракторов; каждый
  use-case управляет транзакцией и orchestration.
- `sprint_bot.application.ports.repositories` — контракты работы с
  Postgres/Sheets (слой хранения).
- `sprint_bot.application.ports.services` — контракты интеграций Telegram,
  S3/объектное хранилище и Sentry.

### Infrastructure
- `sprint_bot.infrastructure.telegram` — адаптеры поверх aiogram для
  `NotificationService`.
- `sprint_bot.infrastructure.storage` — клиент S3/MinIO для `StorageService`.
- `sprint_bot.infrastructure.observability` — биндинги логгера и Sentry к
  `ObservabilityService`.
- Google Sheets будет постепенно заменяться Postgres (через репозитории), но
  до миграции предоставляется адаптер `WorksheetService`.

## Порты и адаптеры
| Порт | Ответственность | Адаптеры (первый этап) |
| --- | --- | --- |
| `AthleteRepository` | CRUD атлетов, выборки по тренеру/Telegram | Google Sheets (текущий), Postgres (target) |
| `CoachRepository` | CRUD тренеров | Google Sheets → Postgres |
| `RaceRepository` | Хранение гонок и сплитов | Google Sheets экспорт → Postgres + файлы JSON |
| `PerformanceRepository` | Segment PR и SoB | Sheets вычисления → Postgres materialized views |
| `WorksheetService` | Чтение/запись в Sheets | gspread/Google API |
| `StorageService` | Хранение экспортов/бэкапов | AWS S3/MinIO |
| `NotificationService` | Исходящие Telegram уведомления | aiogram бот |
| `ObservabilityService` | Метрики, ошибки | Sentry SDK + Prometheus push |

## План рефакторинга без даунтайма
1. **Каркас и контракт** — ввести пакеты domain/application/infrastructure и
   описать DTO + порты (текущий шаг). Интеграция legacy-кода не тронута.
2. **Анти-коррапшн слой для Sheets** — реализовать адаптеры `WorksheetService`
   и `AthleteRepository` поверх текущих сервисов, прокрыть типами.
3. **Use-case фасады** — обернуть ключевые хэндлеры (онбординг, сплиты,
   отчётность) в use-case интерпретаторы, инжектируя новые порты. Legacy
   сервисы продолжают вызываться через адаптеры.
4. **Дублирование данных в Postgres** — поднять ETL, синхронизирующий Sheets →
   Postgres по расписанию. Хэндлеры читают из Postgres, запись ещё в Sheets.
5. **Переключение записи на Postgres** — после выравнивания данных перевести
   запись на Postgres и оставить Sheets как read-only бэкап.
6. **Оптимизация телеметрии** — настроить централизованный логгер, Sentry и
   метрики, используя `ObservabilityService`.
7. **Декомпозиция монолитных сервисов** — перенос статистики и отчётов в
   отдельные use-cases и фоновые задания (Celery/APS), при этом Telegram
   командный интерфейс не меняется.

## Риски и меры
- **Несогласованность данных** — при параллельной записи в Sheets/Postgres
  требуется двунаправленная валидация и алерты (`ObservabilityService`).
- **Рост сложности интеграций** — необходимо покрыть адаптеры тестами и
  контрактами (pytest + pytest-asyncio, моки портов).
- **Регрессии Telegram** — постепенная миграция хэндлеров через фасадные
  use-cases обеспечит совместимость; fallback остаётся доступным.

## Следующие шаги
- Реализовать адаптер `WorksheetService` поверх существующих `services.*`.
- Описать use-case для импорта результатов гонок, используя `RaceRepository`.
- Настроить инфраструктурные пакеты (S3, Sentry) и внедрить DI-контейнер.
