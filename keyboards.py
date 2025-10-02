from __future__ import annotations

import base64
import binascii
from typing import TYPE_CHECKING, Iterable, Sequence

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from i18n import t
from role_service import ROLE_ADMIN, ROLE_ATHLETE, ROLE_TRAINER

if TYPE_CHECKING:  # pragma: no cover - typing helpers only
    from services.query_service import SearchResult

# --- CallbackData Factories ---


class StrokeCB(CallbackData, prefix="stroke"):
    stroke: str


class DistanceCB(CallbackData, prefix="dist"):
    """Callback factory for choosing a sprint distance."""

    value: int


class TemplateCB(CallbackData, prefix="tpl"):
    """Callback factory for sprint templates."""

    template_id: str


class RepeatCB(CallbackData, prefix="repeat"):
    """Callback factory for repeating the previous result."""

    athlete_id: int


class AuditUndoCB(CallbackData, prefix="auditundo"):
    """Callback factory for audit undo actions."""

    op_id: int


class CommentCB(CallbackData, prefix="comment"):
    """Callback factory for comment management."""

    action: str
    ts: str
    athlete_id: int


class AddWizardCB(CallbackData, prefix="aw"):
    """Callback factory for add-result wizard actions."""

    action: str
    value: str = ""


class OnboardingRoleCB(CallbackData, prefix="onbrole"):
    """Callback data for onboarding role selection."""

    role: str


class OnboardingLanguageCB(CallbackData, prefix="onblang"):
    """Callback data for onboarding language selection."""

    language: str


class SearchFilterCB(CallbackData, prefix="searchf"):
    """Callback data for search wizard selections."""

    field: str
    value: str


class SearchPageCB(CallbackData, prefix="searchpg"):
    """Callback for navigating result pages."""

    page: int


# --- Reply Keyboards ---

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Додати результат ➕")],
        [
            KeyboardButton(text="Мої результати 🏆"),
            KeyboardButton(text="Особисті рекорди 🥇"),
        ],
    ],
    resize_keyboard=True,
)

# --- Inline Keyboards ---


def get_stroke_keyboard() -> InlineKeyboardMarkup:
    """Get keyboard for choosing swim stroke."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏊‍♂️ Кроль", callback_data=StrokeCB(stroke="freestyle").pack()
                ),
                InlineKeyboardButton(
                    text="🏊‍♀️ Спина", callback_data=StrokeCB(stroke="backstroke").pack()
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🦋 Батерфляй",
                    callback_data=StrokeCB(stroke="butterfly").pack(),
                ),
                InlineKeyboardButton(
                    text="🐸 Брас", callback_data=StrokeCB(stroke="breaststroke").pack()
                ),
            ],
        ]
    )


def get_history_keyboard() -> InlineKeyboardMarkup:
    """Get keyboard with a button to show detailed history."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📜 Показати детальну історію", callback_data="history"
                )
            ]
        ]
    )


def get_sportsmen_keyboard(sportsmen: list) -> InlineKeyboardMarkup:
    """Gets keyboard with sportsmen names."""
    buttons = [
        InlineKeyboardButton(text=name, callback_data=name) for name in sportsmen
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


def get_distance_keyboard() -> InlineKeyboardMarkup:
    """Return keyboard with frequently used sprint distances."""

    distance_buttons = [
        [
            InlineKeyboardButton(
                text=f"{dist} м", callback_data=DistanceCB(value=dist).pack()
            )
            for dist in row
        ]
        for row in ((50, 100, 200), (400, 800, 1500))
    ]

    extra_row = [
        InlineKeyboardButton(text="📋 Шаблони", callback_data="choose_template"),
        InlineKeyboardButton(text="✏️ Інша", callback_data="manual_distance"),
    ]

    return InlineKeyboardMarkup(inline_keyboard=distance_buttons + [extra_row])


def get_template_keyboard(templates: Iterable[tuple[str, str]]) -> InlineKeyboardMarkup:
    """Build keyboard with template choices."""

    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []

    for template_id, title in templates:
        row.append(
            InlineKeyboardButton(
                text=title, callback_data=TemplateCB(template_id=template_id).pack()
            )
        )
        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append(
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_distance"),
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_repeat_keyboard(athlete_id: int) -> InlineKeyboardMarkup:
    """Return keyboard with repeat action."""

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔁 Повторити попередній результат",
                    callback_data=RepeatCB(athlete_id=athlete_id).pack(),
                )
            ]
        ]
    )


def build_audit_entry_keyboard(op_id: int) -> InlineKeyboardMarkup:
    """Build keyboard for undoing audit operation."""

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("audit.btn.undo"),
                    callback_data=AuditUndoCB(op_id=op_id).pack(),
                )
            ]
        ]
    )


def get_onboarding_role_keyboard() -> InlineKeyboardMarkup:
    """Return keyboard with onboarding role options."""

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Я тренер",
                    callback_data=OnboardingRoleCB(role=ROLE_TRAINER).pack(),
                ),
                InlineKeyboardButton(
                    text="Я спортсмен",
                    callback_data=OnboardingRoleCB(role=ROLE_ATHLETE).pack(),
                ),
            ]
        ]
    )


def get_onboarding_language_keyboard() -> InlineKeyboardMarkup:
    """Return keyboard with language choices."""

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Українська",
                    callback_data=OnboardingLanguageCB(language="uk").pack(),
                ),
                InlineKeyboardButton(
                    text="Русский",
                    callback_data=OnboardingLanguageCB(language="ru").pack(),
                ),
            ]
        ]
    )


def get_onboarding_skip_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard allowing to skip optional step."""

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Пропустить", callback_data="onboard_skip_group"
                )
            ]
        ]
    )


def pack_timestamp_for_callback(timestamp: str) -> str:
    """Convert timestamp to callback-friendly format."""

    encoded = base64.urlsafe_b64encode(timestamp.encode("utf-8")).decode("ascii")
    return encoded.rstrip("=")


def unpack_timestamp_from_callback(raw: str) -> str:
    """Restore original timestamp from callback data."""

    try:
        padding = "=" * (-len(raw) % 4)
        decoded = base64.urlsafe_b64decode((raw + padding).encode("ascii"))
        return decoded.decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return raw.replace("_", " ")


def get_comment_prompt_keyboard() -> InlineKeyboardMarkup:
    """Keyboard offering to skip comment input."""

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Пропустити", callback_data="comment_skip")]
        ]
    )


def wizard_cancel_button() -> InlineKeyboardButton:
    """Return standard cancel button for the add wizard."""

    return InlineKeyboardButton(
        text=t("common.cancel"), callback_data=AddWizardCB(action="cancel").pack()
    )


def wizard_navigation_row(back_target: str | None) -> list[InlineKeyboardButton]:
    """Return navigation row with back and cancel buttons."""

    buttons: list[InlineKeyboardButton] = []
    if back_target:
        buttons.append(
            InlineKeyboardButton(
                text=t("common.back"),
                callback_data=AddWizardCB(action="back", value=back_target).pack(),
            )
        )
    buttons.append(wizard_cancel_button())
    return buttons


def get_result_actions_keyboard(
    athlete_id: int, timestamp: str, has_comment: bool
) -> InlineKeyboardMarkup:
    """Keyboard with comment management and repeat actions."""

    packed_ts = pack_timestamp_for_callback(timestamp)
    comment_text = "✏️ Редагувати нотатку" if has_comment else "📝 Додати нотатку"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=comment_text,
                    callback_data=CommentCB(
                        action="edit", ts=packed_ts, athlete_id=athlete_id
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔁 Повторити попередній результат",
                    callback_data=RepeatCB(athlete_id=athlete_id).pack(),
                )
            ],
        ]
    )


def get_main_keyboard(role: str) -> InlineKeyboardMarkup:
    """Return main menu keyboard respecting user role."""

    buttons = [
        [InlineKeyboardButton(text="Спринт", callback_data="menu_sprint")],
        [InlineKeyboardButton(text="Стаєр", callback_data="menu_stayer")],
        [InlineKeyboardButton(text="Історія", callback_data="menu_history")],
        [InlineKeyboardButton(text="Рекорди", callback_data="menu_records")],
        [InlineKeyboardButton(text="💬 Повідомлення", callback_data="menu_messages")],
    ]

    if role in {ROLE_TRAINER, ROLE_ADMIN}:
        buttons.append(
            [
                InlineKeyboardButton(
                    text="➕ Запросити спортсмена", callback_data="invite"
                )
            ]
        )

    if role == ROLE_ADMIN:
        buttons.append([InlineKeyboardButton(text="Адмін", callback_data="menu_admin")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_search_athlete_keyboard(
    options: Sequence[tuple[str, str]],
    *,
    include_all: bool = False,
    all_label: str | None = None,
) -> InlineKeyboardMarkup:
    """Build inline keyboard for choosing an athlete."""

    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []

    if include_all:
        row.append(
            InlineKeyboardButton(
                text=all_label or t("search.filter.all_users"),
                callback_data=SearchFilterCB(field="athlete", value="any").pack(),
            )
        )

    for value, label in options:
        row.append(
            InlineKeyboardButton(
                text=label,
                callback_data=SearchFilterCB(field="athlete", value=value).pack(),
            )
        )
        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    if not buttons:
        buttons = [
            [
                InlineKeyboardButton(
                    text=all_label or t("search.filter.all_users"),
                    callback_data=SearchFilterCB(field="athlete", value="any").pack(),
                )
            ]
        ]

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_search_style_keyboard(
    choices: Sequence[tuple[str, str]],
) -> InlineKeyboardMarkup:
    """Return keyboard for choosing swim style."""

    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for value, label in choices:
        row.append(
            InlineKeyboardButton(
                text=label,
                callback_data=SearchFilterCB(field="stroke", value=value).pack(),
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_search_distance_keyboard(
    choices: Sequence[tuple[str, str]],
) -> InlineKeyboardMarkup:
    """Return keyboard for choosing sprint distance."""

    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for value, label in choices:
        row.append(
            InlineKeyboardButton(
                text=label,
                callback_data=SearchFilterCB(field="distance", value=value).pack(),
            )
        )
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_search_pr_keyboard() -> InlineKeyboardMarkup:
    """Return keyboard with PR filter choices."""

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("search.pr.only"),
                    callback_data=SearchFilterCB(field="pr", value="only").pack(),
                ),
                InlineKeyboardButton(
                    text=t("search.pr.all"),
                    callback_data=SearchFilterCB(field="pr", value="all").pack(),
                ),
                InlineKeyboardButton(
                    text=t("search.pr.any"),
                    callback_data=SearchFilterCB(field="pr", value="any").pack(),
                ),
            ]
        ]
    )


def build_search_results_keyboard(
    results: Sequence["SearchResult"],
    *,
    page: int,
    total_pages: int,
    start_index: int,
) -> InlineKeyboardMarkup:
    """Return keyboard with report buttons and pagination controls."""

    buttons: list[list[InlineKeyboardButton]] = []
    for idx, item in enumerate(results, start=start_index + 1):
        buttons.append(
            [
                InlineKeyboardButton(
                    text=t("search.report_btn", idx=idx),
                    switch_inline_query_current_chat=f"/report {item.result_id}",
                )
            ]
        )

    if total_pages > 1:
        nav_row: list[InlineKeyboardButton] = []
        if page > 1:
            nav_row.append(
                InlineKeyboardButton(
                    text=t("search.prev"),
                    callback_data=SearchPageCB(page=page - 1).pack(),
                )
            )
        if page < total_pages:
            nav_row.append(
                InlineKeyboardButton(
                    text=t("search.next"),
                    callback_data=SearchPageCB(page=page + 1).pack(),
                )
            )
        if nav_row:
            buttons.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=buttons)
