# Sprint-Bot

Sprint-Bot — Telegram-бот на основе **Python** и **aiogram 3**, позволяющий создавать и проходить спортивные «спринты». Бот подойдет спортсменам и тренерам, которые хотят организовать совместные челленджи и следить за прогрессом участников.

## Основные функции
- создание новых спринтов и выбор дистанции;
- присоединение к уже созданным спринтам;
- фиксация результатов и расчет личных рекордов;
- просмотр истории попыток;
- админ-панель для управления участниками.

## Технологии
- Python 3;
- библиотека aiogram 3 для работы с Telegram API;
- база данных SQLite для хранения данных (результаты, пользователи).

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
- `examples/` — примеры файлів для імпорту та пояснення формату.

## Імпорт результатів

Для масового завантаження результатів використовуйте CSV-файл у форматі з каталогу
`examples/`. Кожен рядок обов'язково повинен містити `athlete_id` спортсмена, який уже
зареєстрований у боті, і (за наявності) його ім'я з аркуша `AthletesList`.

> ❗️ Рядки з невідомими або незареєстрованими спортсменами будуть відхилені під час
> імпорту. Перед завантаженням переконайтеся, що всі учасники додані до реєстру.

