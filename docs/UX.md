# Sprint Bot Scenario Playbook

## /start Onboarding
- **Happy path**: роль → приватность → имя → тренер → группа → язык → карточка профиля.
- **Защита**: отказ приватности сбрасывает состояние и отзывает инвайт; неверные trainer-ID/инвайты дают подсказки.
- **Сценарные тесты**: `tests/test_onboarding_flow.py` покрывает happy-path, отказ приватности и deep-link-инвайт.

```mermaid
flowchart LR
    start[/Команда /start/] --> role{Выбор роли}
    role -->|Тренер| privacy{Поделиться данными?}
    role -->|Атлет| privacy
    privacy -->|Нет| abort[/Отменяем онбординг/]
    abort --> exit_state[(FSM reset)]
    privacy -->|Да| profile["Запрос имени и контакта"]
    profile --> trainer[Проверка trainer ID или инвайта]
    trainer --> group[Выбор группы]
    group --> locale[Выбор языка]
    locale --> card[Показываем карточку профиля]
    card --> done[/Онбординг завершён/]
```

## /help Справка
- Сообщение разбито на блоки: ввод, история, сравнение, рекорды, лидерборд, экспорт.
- Строки локализованы (uk/ru) и проверяются в `tests/test_bot_i18n.py`.
- Хэндлер не требует состояний — доступен всегда, безопасен к спаму.

```mermaid
sequenceDiagram
    participant U as Пользователь
    participant B as Бот
    U->>B: /help
    B-->>U: Заголовок + интро
    B-->>U: Блок "Ввод результатов"
    B-->>U: Блок "История"
    B-->>U: Блок "Сравнение"
    B-->>U: Блок "Рекорды"
    B-->>U: Блок "Лидерборд"
    B-->>U: Блок "Экспорт"
```

## Мастер ввода сплитов
- Шаги: стиль/дистанция → шаблон → сплиты → тотал → подтверждение.
- Поддерживает форматы `mm:ss.ss`, `см/мс`, `repeat/cancel`, автосумму и выравнивание.
- Тесты (`tests/test_add_wizard.py`, `tests/test_add_wizard_i18n.py`) закрывают happy-path, отмену, повтор и ошибки формата.

```mermaid
stateDiagram-v2
    [*] --> preset
    preset: Стиль/дистанция/шаблон
    preset --> splits
    splits: Ввод сплитов
    splits --> splits: Подсказка формата / повтор шага
    splits --> total: Тотал и валидация
    total --> confirm: Подтверждение сохранения
    total --> splits: Ошибка формата → возврат
    confirm --> [*]
    [*] --> cancel: /cancel в любой момент
    cancel --> [*]
```
