"""Handlers implementing sprint result search with filters."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Mapping, Sequence

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from i18n import t
from keyboards import (
    SearchFilterCB,
    SearchPageCB,
    build_search_athlete_keyboard,
    build_search_distance_keyboard,
    build_search_pr_keyboard,
    build_search_results_keyboard,
    build_search_style_keyboard,
)
from role_service import ROLE_ATHLETE, RoleService
from services.query_service import QueryService, SearchFilters, SearchPage
from utils import fmt_time

router = Router()

PAGE_SIZE = 5

STYLE_VALUES: Sequence[str] = (
    "any",
    "freestyle",
    "backstroke",
    "butterfly",
    "breaststroke",
    "medley",
)

STYLE_LABEL_KEYS: Mapping[str, str] = {
    "any": "search.style.any",
    "freestyle": "search.style.freestyle",
    "backstroke": "search.style.backstroke",
    "butterfly": "search.style.butterfly",
    "breaststroke": "search.style.breaststroke",
    "medley": "search.style.medley",
}

SKIP_TOKENS = {
    "-",
    "skip",
    "any",
    "пропустити",
    "пропустить",
    "будь-яка",
    "любая",
    "любой",
}

DISTANCE_VALUES: Sequence[str] = ("any", "50", "100", "200", "400", "800", "1500")


def _stroke_label(value: str) -> str:
    key = STYLE_LABEL_KEYS.get(value)
    if key:
        return t(key)
    return value


def _style_choices() -> list[tuple[str, str]]:
    return [(value, _stroke_label(value)) for value in STYLE_VALUES]


def _distance_label(value: int | None) -> str:
    if value is None:
        return t("search.distance.any")
    return t("search.distance.value", distance=value)


def _distance_choices() -> list[tuple[str, str]]:
    choices: list[tuple[str, str]] = []
    for value in DISTANCE_VALUES:
        if value == "any":
            choices.append((value, t("search.distance.any")))
        else:
            choices.append((value, t("search.distance.value", distance=int(value))))
    return choices


class SearchStates(StatesGroup):
    """FSM states for search wizard."""

    choose_athlete = State()
    choose_style = State()
    choose_distance = State()
    enter_dates = State()
    choose_pr = State()
    browsing = State()


@router.message(Command("search"))
async def start_search(
    message: types.Message, state: FSMContext, role_service: RoleService
) -> None:
    """Initiate search wizard by asking for an athlete."""

    await state.clear()
    requester = message.from_user.id
    accessible = set(await role_service.get_accessible_athletes(requester))
    if not accessible:
        accessible.add(requester)

    users = await role_service.list_users(roles=(ROLE_ATHLETE,))
    labels = {
        str(user.telegram_id): user.full_name or f"ID {user.telegram_id}"
        for user in users
    }
    options: list[tuple[str, str]] = []
    for uid in sorted(accessible):
        key = str(uid)
        options.append((key, labels.get(key, f"ID {uid}")))

    if not options:
        key = str(requester)
        options = [(key, labels.get(key, f"ID {requester}"))]

    include_all = len(options) > 1
    all_label = t("search.filter.all_users")
    keyboard = build_search_athlete_keyboard(
        options, include_all=include_all, all_label=all_label
    )

    default_athlete_label = all_label if include_all else options[0][1]

    await state.update_data(
        athlete_id=None,
        athlete_label=default_athlete_label,
        athlete_labels={value: label for value, label in options},
        stroke=None,
        stroke_label=_stroke_label("any"),
        distance=None,
        distance_label=_distance_label(None),
        date_from=None,
        date_to=None,
        date_label=t("search.filter.no_dates"),
        only_pr=False,
    )

    await message.answer(t("search.prompt.athlete"), reply_markup=keyboard)
    await state.set_state(SearchStates.choose_athlete)


@router.callback_query(
    SearchStates.choose_athlete, SearchFilterCB.filter(F.field == "athlete")
)
async def select_athlete(
    callback: types.CallbackQuery, state: FSMContext, callback_data: SearchFilterCB
) -> None:
    """Handle athlete selection and proceed to style choice."""

    await callback.answer()
    data = await state.get_data()
    raw_labels = data.get("athlete_labels")
    labels: dict[str, str]
    if isinstance(raw_labels, Mapping):
        labels = {str(key): str(value) for key, value in raw_labels.items()}
    else:
        labels = {}
    value = callback_data.value
    if value == "any":
        athlete_id: int | None = None
        label = t("search.filter.all_users")
    else:
        try:
            athlete_id = int(value)
        except ValueError:
            athlete_id = None
        label = labels.get(value, f"ID {value}")

    await state.update_data(athlete_id=athlete_id, athlete_label=label)
    await callback.message.answer(
        t("search.prompt.style"),
        reply_markup=build_search_style_keyboard(_style_choices()),
    )
    await state.set_state(SearchStates.choose_style)


@router.callback_query(
    SearchStates.choose_style, SearchFilterCB.filter(F.field == "stroke")
)
async def select_style(
    callback: types.CallbackQuery, state: FSMContext, callback_data: SearchFilterCB
) -> None:
    """Handle swim style selection."""

    await callback.answer()
    value = callback_data.value
    if value == "any":
        stroke = None
        label = _stroke_label("any")
    else:
        stroke = value
        label = _stroke_label(value)

    await state.update_data(stroke=stroke, stroke_label=label)
    await callback.message.answer(
        t("search.prompt.distance"),
        reply_markup=build_search_distance_keyboard(_distance_choices()),
    )
    await state.set_state(SearchStates.choose_distance)


@router.callback_query(
    SearchStates.choose_distance, SearchFilterCB.filter(F.field == "distance")
)
async def select_distance(
    callback: types.CallbackQuery, state: FSMContext, callback_data: SearchFilterCB
) -> None:
    """Handle distance selection."""

    await callback.answer()
    value = callback_data.value
    if value == "any":
        distance = None
    else:
        try:
            distance = int(value)
        except ValueError:
            distance = None
    label = _distance_label(distance)

    await state.update_data(distance=distance, distance_label=label)
    await callback.message.answer(
        t("search.prompt.dates"),
    )
    await state.set_state(SearchStates.enter_dates)


@router.message(SearchStates.enter_dates)
async def input_dates(message: types.Message, state: FSMContext) -> None:
    """Parse date range input and proceed to PR filter."""

    text = (message.text or "").strip()
    try:
        date_from, date_to, label = _parse_date_range(text)
    except ValueError:
        await message.answer(t("search.error.range"))
        return

    await state.update_data(date_from=date_from, date_to=date_to, date_label=label)
    await message.answer(
        t("search.prompt.pr"),
        reply_markup=build_search_pr_keyboard(),
    )
    await state.set_state(SearchStates.choose_pr)


@router.callback_query(SearchStates.choose_pr, SearchFilterCB.filter(F.field == "pr"))
async def select_pr(
    callback: types.CallbackQuery,
    state: FSMContext,
    callback_data: SearchFilterCB,
    query_service: QueryService,
) -> None:
    """Handle PR filter selection and show first page of results."""

    await callback.answer()
    value = callback_data.value
    only_pr = value == "only"
    await state.update_data(only_pr=only_pr)

    data = await state.get_data()
    filters = _filters_from_state(data)
    page = await query_service.search_results(filters, page=1, page_size=PAGE_SIZE)
    if page.total == 0:
        await callback.message.answer(t("search.empty"))
        await state.set_state(SearchStates.browsing)
        return

    text = _format_results(page, data)
    markup = build_search_results_keyboard(
        page.items,
        page=page.page,
        total_pages=page.pages,
        start_index=(page.page - 1) * PAGE_SIZE,
    )
    await callback.message.answer(text, reply_markup=markup)
    await state.update_data(last_page=page.page, total_pages=page.pages)
    await state.set_state(SearchStates.browsing)


@router.callback_query(SearchStates.browsing, SearchPageCB.filter())
async def paginate(
    callback: types.CallbackQuery,
    state: FSMContext,
    callback_data: SearchPageCB,
    query_service: QueryService,
) -> None:
    """Switch between result pages."""

    await callback.answer()
    target_page = max(1, callback_data.page)
    data = await state.get_data()
    filters = _filters_from_state(data)
    page = await query_service.search_results(
        filters, page=target_page, page_size=PAGE_SIZE
    )
    if page.total == 0:
        await callback.message.edit_text(t("search.empty"))
        return

    text = _format_results(page, data)
    markup = build_search_results_keyboard(
        page.items,
        page=page.page,
        total_pages=page.pages,
        start_index=(page.page - 1) * PAGE_SIZE,
    )
    await callback.message.edit_text(text, reply_markup=markup)
    await state.update_data(last_page=page.page, total_pages=page.pages)


def _parse_date_token(raw: str) -> date:
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(t("search.error.date", value=raw)) from exc


def _parse_date_range(value: str) -> tuple[str | None, str | None, str]:
    if not value or value.lower() in SKIP_TOKENS:
        return None, None, t("search.filter.no_dates")
    parts = [part for part in value.replace(",", " ").split() if part]
    if not parts:
        return None, None, t("search.filter.no_dates")
    if len(parts) == 1:
        start = _parse_date_token(parts[0])
        label = t("search.filter.date_single", date=start.strftime("%d.%m.%Y"))
        return start.isoformat(), start.isoformat(), label
    start = _parse_date_token(parts[0])
    end = _parse_date_token(parts[1])
    if end < start:
        start, end = end, start
    label = t(
        "search.filter.date_range",
        start=start.strftime("%d.%m.%Y"),
        end=end.strftime("%d.%m.%Y"),
    )
    return start.isoformat(), end.isoformat(), label


def _filters_from_state(data: Mapping[str, Any]) -> SearchFilters:
    raw_from = data.get("date_from")
    raw_to = data.get("date_to")
    date_from = (
        date.fromisoformat(raw_from) if isinstance(raw_from, str) and raw_from else None
    )
    date_to = date.fromisoformat(raw_to) if isinstance(raw_to, str) and raw_to else None
    athlete_id = data.get("athlete_id")
    distance = data.get("distance")
    stroke = data.get("stroke")
    only_pr = bool(data.get("only_pr"))
    return SearchFilters(
        athlete_id=athlete_id if isinstance(athlete_id, int) else None,
        stroke=stroke if isinstance(stroke, str) else None,
        distance=distance if isinstance(distance, int) else None,
        date_from=date_from,
        date_to=date_to,
        only_pr=only_pr,
    )


def _filters_summary(data: Mapping[str, Any]) -> str:
    athlete = data.get("athlete_label") or t("search.filter.all_users")
    stroke = data.get("stroke_label") or _stroke_label("any")
    distance = data.get("distance_label") or _distance_label(None)
    date_label = data.get("date_label") or t("search.filter.no_dates")
    pr_label = (
        t("search.filter.pr_only") if data.get("only_pr") else t("search.filter.pr_all")
    )
    entries = [
        t("search.filter.user", value=athlete),
        t("search.filter.style", value=stroke),
        t("search.filter.distance", value=distance),
        t("search.filter.dates", value=date_label),
        pr_label,
    ]
    return t("search.filter.summary", filters="; ".join(entries))


def _format_results(page: SearchPage, data: Mapping[str, Any]) -> str:
    parts = [t("search.title"), _filters_summary(data)]
    parts.append(t("search.page", cur=page.page, total=max(page.pages, 1)))
    start_index = (page.page - 1) * PAGE_SIZE
    for idx, item in enumerate(page.items, start=start_index + 1):
        style_label = _stroke_label(item.stroke)
        distance_label = _distance_label(item.distance)
        athlete_name = item.athlete_name or f"ID {item.athlete_id}"
        timestamp = item.timestamp.strftime("%d.%m.%Y %H:%M")
        pr_flag = t("search.card.pr_flag") if item.is_pr else ""
        card = "\n".join(
            [
                f"{idx}. {timestamp} • {distance_label} • {style_label}",
                f"   👤 {athlete_name} ({item.athlete_id})",
                f"   ⏱ {fmt_time(item.total_seconds)}{pr_flag}",
            ]
        )
        parts.append(card)
    return "\n\n".join(parts)


__all__ = ["router", "SearchStates", "start_search"]
