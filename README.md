# Sprint-Bot

Sprint-Bot — Telegram-бот на основе **Python** и **aiogram 3**, позволяющий создавать и проходить спортивные «спринты». Бот подойдет спортсменам и тренерам, которые хотят организовать совместные челленджи и следить за прогрессом участников.

## Основные функции
- создание новых спринтов и выбор дистанции;
- присоединение к уже созданным спринтам;
- фиксация результатов и расчет личных рекордов;
- просмотр истории попыток;
- админ-панель для управления участниками.
- двосторонній чат між тренерами та спортсменами для швидкої комунікації.
- автоматизовані резервні копії SQLite-бази та відновлення з хмарного сховища.

## Шаблони спринтів

Тренери можуть заздалегідь зберегти улюблені розбивки дистанції та швидко
запускати нові спринти за кілька тапів. Меню `/templates` дозволяє створювати,
редагувати та видаляти шаблони з кастомним набором відрізків.

```python
from template_service import TemplateService


async def demo_template_usage() -> None:
    service = TemplateService()
    await service.init()

    template = await service.create_template(
        title="⚡️ 75 м спринт",
        dist=75,
        stroke="freestyle",
        hint="Початок на максимумі, далі рівний темп",
        segments=(25, 25, 25),
    )

    templates = await service.list_templates()
    selected = await service.get_template(template.template_id)

    print(selected.title, selected.segments_or_default())
```

Під час додавання результату бот показує клавіатуру з шаблонами та підказкою по
відрізках, а система зберігає обрані сегменти для аналізу швидкості.

## Технологии
- Python 3;
- библиотека aiogram 3 для работы с Telegram API;
- база данных SQLite для хранения даних (результати, користувачі, повідомлення) через стандартний модуль `sqlite3`.

## Визуализация прогресса спортсмена

Команда `/progress` дозволяє обрати спортсмена та отримати графік зміни часу по
різних дистанціях. Після генерації бот надсилає зображення з лініями для кожної
дистанції та коротку таблицю динаміки (старт, поточний результат і різниця).

Нижче наведено спрощений приклад коду побудови графіка за допомогою
`matplotlib` та відправлення його у чат Telegram:

```python
import io
import matplotlib

from aiogram.types import BufferedInputFile

matplotlib.use("Agg")
import matplotlib.pyplot as plt


async def send_progress_chart(message, dates, values):
    fig, ax = plt.subplots()
    ax.plot(dates, values, marker="o")
    ax.set_title("Прогрес спортсмена")
    ax.set_xlabel("Дата")
    ax.set_ylabel("Час, с")

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=150)
    plt.close(fig)
    buffer.seek(0)

    await message.answer_photo(
        BufferedInputFile(buffer.getvalue(), filename="progress.png"),
        caption="📈 Прогрес за останні тренування",
    )
```

## Система уведомлений

Sprint-Bot надсилає автоматичні нагадування про нові спринти та повідомляє про
додавання результатів. Користувачі можуть керувати підпискою командами
`/notify_on`, `/notify_off` та переглядати розклад `/notify_info`.

Базова логіка побудована на асинхронному сервісі `NotificationService`, який
запускається разом із диспетчером aiogram:

```python
notification_service = NotificationService(bot)

dp.startup.register(notification_service.startup)
dp.shutdown.register(notification_service.shutdown)

await dp.start_polling(bot, notifications=notification_service)
```

Сервіс вміє планувати чергове нагадування, формувати текст розсилки та
розповсюджувати push-повідомлення лише серед підписаних чатів:

```python
next_run = notification_service.next_sprint_run()
await notification_service.broadcast_text(
    f"⏱ Наступний спринт: {next_run:%d.%m о %H:%M}"
)
```

Після збереження нового результату бот одразу повідомляє команду про зміни:

```python
await notification_service.notify_new_result(
    actor_id=coach.id,
    actor_name=coach.full_name,
    athlete_id=athlete_id,
    athlete_name=athlete_name,
    dist=dist,
    total=total,
    timestamp=timestamp,
    new_prs=new_prs,
)
```

## Резервне копіювання та відновлення

Sprint-Bot автоматично копіює локальну базу `data/chat.db` до сховища Amazon S3 (або сумісного S3-сервісу). Бекапи виконуються у фоновому завданні `BackupService` з певним інтервалом, а про успішні операції та помилки бот повідомляє адміністраторів у Telegram.

Необхідні змінні оточення:

- `S3_BACKUP_BUCKET` — назва бакету для резервних копій;
- `S3_BACKUP_PREFIX` — префікс (каталог) усередині бакету, за замовчуванням `sprint-bot/backups/`;
- `BACKUP_INTERVAL_HOURS` — інтервал між бекапами у годинах (наприклад, `6`);
- `S3_STORAGE_CLASS` та `S3_ENDPOINT_URL` — необов'язкові параметри для альтернативних S3-сховищ.

> 💡 Для роботи з AWS S3 встановіть SDK командою `pip install boto3`.

Доступні лише адміністраторам команди:

- `/backup_now` — виконати резервне копіювання негайно;
- `/backup_status` — показати останні архіви в бакеті;
- `/restore_backup [s3_key]` — відновити базу з останнього або конкретного архіву.

Приклад ініціалізації та використання сервісу за допомогою офіційного SDK `boto3`:

```python
from datetime import timedelta
from pathlib import Path

from aiogram import Bot

from backup_service import BackupService

bot = Bot(token="<TELEGRAM_TOKEN>")
backup_service = BackupService(
    bot=bot,
    db_path=Path("data/chat.db"),
    bucket_name="sprint-bot-backups",
    backup_prefix="sprint-bot/backups/",
    interval=timedelta(hours=6),
)

# Створити резервну копію вручну та отримати метадані файлу в S3
metadata = await backup_service.backup_now()
print("Uploaded:", metadata.key, metadata.size)
```

## Чат тренера та спортсмена

Бот підтримує вбудовану систему повідомлень. Тренер відкриває пункт меню «💬 Повідомлення»,
обирає спортсмена та надсилає текст — бот зберігає його в SQLite (`chat_service.py`) і
переадресовує спортсмену. Спортсмен бачить список доступних тренерів, переглядає історію
спілкування та може відповісти прямо з бота. Всі повідомлення маркуються як прочитані, а
про нові надходження користувач отримує миттєве сповіщення в Telegram.

## Установка и запуск
1. Клонируйте репозиторий:
   ```bash
   git clone <repository_url>
   cd Sprint-Bot
   ```
2. Создайте и активируйте виртуальное окружение:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```
3. Установите зависимости:
   ```bash
   pip install -r requirements.txt
   ```
4. Скопируйте файл `.env.example` в `.env` и задайте переменную `BOT_TOKEN` со значением токена вашего бота.
5. Запустите бот:
   ```bash
   python bot.py
   ```

## Структура проекта
- `bot.py` — основной файл бота, содержит обработчики команд и логику работы со спринтами.
- `db.py` — модуль для работы с базой данных SQLite (создание таблиц, запросы).
- `keyboards.py` — файл с описаниями клавиатур Telegram для удобного взаимодействия.
- `chat_service.py` — асинхронне сховище повідомлень між тренерами та спортсменами.
- `examples/` — примеры файлів для імпорту та пояснення формату.

## Імпорт результатів

Для масового завантаження результатів використовуйте CSV-файл у форматі з каталогу
`examples/`. Кожен рядок обов'язково повинен містити `athlete_id` спортсмена, який уже
зареєстрований у боті, і (за наявності) його ім'я з аркуша `AthletesList`.

> ❗️ Рядки з невідомими або незареєстрованими спортсменами будуть відхилені під час
> імпорту. Перед завантаженням переконайтеся, що всі учасники додані до реєстру.

