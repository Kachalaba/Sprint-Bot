from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from keyboards import AddWizardCB, wizard_cancel_button, wizard_navigation_row
from utils import fmt_time
from utils.parse_time import parse_splits, parse_total, validate_splits

router = Router()


class AddWizardStates(StatesGroup):
    """States for guided sprint result entry."""

    choose_style = State()
    choose_distance = State()
    choose_template = State()
    enter_splits = State()
    enter_total = State()
    confirm = State()


STYLE_CHOICES: tuple[tuple[str, str], ...] = (
    ("freestyle", "🏊‍♂️ Кроль"),
    ("backstroke", "🏊‍♀️ Спина"),
    ("butterfly", "🦋 Батерфляй"),
    ("breaststroke", "🐸 Брас"),
    ("medley", "🔁 Комплекс"),
)

DISTANCE_CHOICES: tuple[int, ...] = (50, 100, 200, 400, 800)


@dataclass(frozen=True, slots=True)
class SegmentTemplate:
    """Template describing segment distribution for a distance."""

    label: str
    segments: tuple[float, ...]


def _generate_segment_templates(distance: int) -> tuple[SegmentTemplate, ...]:
    """Return default segment templates for provided distance."""

    if distance <= 0:
        return (SegmentTemplate(label=f"{distance} м", segments=(float(distance),)),)

    candidates: set[tuple[float, ...]] = set()
    base_lengths: tuple[int, ...] = (1, 2, 4, 8)
    for divider in base_lengths:
        if distance % divider == 0:
            value = distance / divider
            candidates.add(tuple(float(value) for _ in range(divider)))
    if distance % 25 == 0:
        count = distance // 25
        candidates.add(tuple(25.0 for _ in range(count)))
    candidates.add((float(distance),))

    templates: list[SegmentTemplate] = []
    for segments in sorted(candidates, key=lambda item: (-len(item), item[0])):
        parts = len(segments)
        segment_label = " + ".join(f"{value:g} м" for value in segments)
        templates.append(
            SegmentTemplate(
                label=f"{parts}×{segments[0]:g} м" if parts > 1 else f"{distance} м",
                segments=segments,
            )
        )
    return tuple(templates)


def _style_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for value, label in STYLE_CHOICES:
        row.append(
            InlineKeyboardButton(
                text=label,
                callback_data=AddWizardCB(action="style", value=value).pack(),
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([wizard_cancel_button()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _distance_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for chunk_start in range(0, len(DISTANCE_CHOICES), 3):
        chunk = DISTANCE_CHOICES[chunk_start : chunk_start + 3]
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{distance} м",
                    callback_data=AddWizardCB(
                        action="distance", value=str(distance)
                    ).pack(),
                )
                for distance in chunk
            ]
        )
    rows.append(wizard_navigation_row(back_target="style"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _template_keyboard(distance: int) -> InlineKeyboardMarkup:
    templates = _generate_segment_templates(distance)
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for template in templates:
        row.append(
            InlineKeyboardButton(
                text=template.label,
                callback_data=AddWizardCB(
                    action="template",
                    value="|".join(str(value) for value in template.segments),
                ).pack(),
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(wizard_navigation_row(back_target="distance"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _splits_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔢 Автосумма",
                    callback_data=AddWizardCB(action="autosum").pack(),
                )
            ],
            wizard_navigation_row(back_target="template"),
        ]
    )


def _total_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚖️ Равномерно из total",
                    callback_data=AddWizardCB(action="even").pack(),
                )
            ],
            wizard_navigation_row(back_target="splits"),
        ]
    )


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💾 Сохранить",
                    callback_data=AddWizardCB(action="save").pack(),
                )
            ],
            wizard_navigation_row(back_target="total"),
        ]
    )


def _format_summary(data: dict) -> str:
    style_label = next(
        (label for value, label in STYLE_CHOICES if value == data.get("style")),
        data.get("style", ""),
    )
    distance = data.get("distance")
    segments = data.get("segments", [])
    splits = data.get("splits", [])
    total = data.get("total")
    segments_line = " + ".join(f"{value:g} м" for value in segments)
    splits_line = ", ".join(fmt_time(value) for value in splits)
    total_line = fmt_time(total) if total is not None else "—"
    return (
        "<b>Перевірка даних</b>\n"
        f"Стиль: {style_label}\n"
        f"Дистанція: {distance} м\n"
        f"Розбивка: {segments_line}\n"
        f"Спліти: {splits_line}\n"
        f"Сумарно: {total_line}"
    )


async def _show_style_step(message: types.Message) -> None:
    await message.answer(
        "Оберіть стиль запливу:",
        reply_markup=_style_keyboard(),
    )


async def _show_distance_step(message: types.Message) -> None:
    await message.answer(
        "Тепер дистанція — натисніть потрібну кнопку:",
        reply_markup=_distance_keyboard(),
    )


async def _show_template_step(message: types.Message, distance: int) -> None:
    await message.answer(
        f"Дистанція {distance} м. Оберіть шаблон розбивки:",
        reply_markup=_template_keyboard(distance),
    )


async def _show_splits_step(message: types.Message, segments: Iterable[float]) -> None:
    await message.answer(
        "Введіть спліти через пробіл у форматі 0:32.45."
        "\nПриклад: 0:30.5 0:31.2",
        reply_markup=_splits_keyboard(),
    )


async def _show_total_step(message: types.Message) -> None:
    await message.answer(
        "Тепер введіть підсумковий час (наприклад, 1:04.32):",
        reply_markup=_total_keyboard(),
    )


async def _show_confirm_step(message: types.Message, data: dict) -> None:
    await message.answer(
        _format_summary(data),
        reply_markup=_confirm_keyboard(),
        parse_mode="HTML",
    )


async def _clear_after(state: FSMContext, fields: Sequence[str]) -> None:
    data = await state.get_data()
    for field in fields:
        data.pop(field, None)
    await state.set_data(data)


@router.message(Command("add_wizard"))
async def start_wizard(message: types.Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AddWizardStates.choose_style)
    await _show_style_step(message)


@router.callback_query(AddWizardCB.filter(F.action == "cancel"))
async def cancel_wizard(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await callback.message.answer("Майстер скасовано.")


@router.callback_query(AddWizardCB.filter(F.action == "style"), AddWizardStates.choose_style)
async def choose_style(
    callback: types.CallbackQuery, state: FSMContext, callback_data: AddWizardCB
) -> None:
    await state.update_data(style=callback_data.value)
    await state.set_state(AddWizardStates.choose_distance)
    await callback.answer()
    await _show_distance_step(callback.message)


@router.callback_query(
    AddWizardCB.filter(F.action == "distance"), AddWizardStates.choose_distance
)
async def choose_distance(
    callback: types.CallbackQuery, state: FSMContext, callback_data: AddWizardCB
) -> None:
    await callback.answer()
    distance = int(callback_data.value)
    await state.update_data(distance=distance)
    await _clear_after(state, ("segments", "splits", "total"))
    await state.set_state(AddWizardStates.choose_template)
    await _show_template_step(callback.message, distance)


@router.callback_query(
    AddWizardCB.filter(F.action == "template"), AddWizardStates.choose_template
)
async def choose_template(
    callback: types.CallbackQuery, state: FSMContext, callback_data: AddWizardCB
) -> None:
    await callback.answer()
    segments = tuple(float(value) for value in callback_data.value.split("|"))
    await state.update_data(segments=segments)
    await _clear_after(state, ("splits", "total"))
    await state.set_state(AddWizardStates.enter_splits)
    await _show_splits_step(callback.message, segments)


@router.callback_query(AddWizardCB.filter(F.action == "autosum"), AddWizardStates.enter_splits)
async def autosum_splits(callback: types.CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    splits = data.get("splits")
    if not splits:
        await callback.answer("Спочатку введіть спліти.", show_alert=True)
        return
    total = sum(float(value) for value in splits)
    await callback.answer()
    await callback.message.answer(f"Сума сплітів: {fmt_time(total)}")


@router.message(AddWizardStates.enter_splits)
async def input_splits(message: types.Message, state: FSMContext) -> None:
    text = message.text or ""
    chunks = text.replace(",", " ").split()
    try:
        splits = parse_splits(chunks)
    except ValueError:
        await message.answer(
            "Не вдалося розпізнати спліти. Використовуйте формат 0:32.45 або 32.1."
        )
        return

    data = await state.get_data()
    segments = data.get("segments") or ()
    if segments and len(segments) != len(splits):
        await message.answer(
            "Кількість сплітів не відповідає шаблону. Спробуйте ще раз."
        )
        return

    await state.update_data(splits=splits)
    await state.set_state(AddWizardStates.enter_total)
    await _show_total_step(message)


@router.callback_query(AddWizardCB.filter(F.action == "even"), AddWizardStates.enter_total)
async def even_from_total(callback: types.CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    total = data.get("total")
    segments = data.get("segments") or ()
    if total is None:
        await callback.answer("Спочатку введіть сумарний час.", show_alert=True)
        return
    if not segments:
        await callback.answer("Немає даних про шаблон відрізків.", show_alert=True)
        return
    distance = float(sum(segments))
    if distance <= 0:
        await callback.answer("Невірний шаблон відрізків.", show_alert=True)
        return
    factor = total / distance
    splits = [round(segment * factor, 5) for segment in segments]
    await state.update_data(splits=splits)
    await callback.answer()
    await callback.message.answer(
        "Спліти оновлено рівномірно: "
        + ", ".join(fmt_time(value) for value in splits)
    )


@router.message(AddWizardStates.enter_total)
async def input_total(message: types.Message, state: FSMContext) -> None:
    text = message.text or ""
    try:
        total = parse_total(text)
    except ValueError:
        await message.answer(
            "Формат часу не розпізнано. Приклад: 1:04.32 або 64.32"
        )
        return

    data = await state.get_data()
    splits = data.get("splits") or []
    try:
        validate_splits(total, splits)
    except ValueError:
        await message.answer(
            "Сума сплітів не збігається з тоталом. Перевірте значення або натисніть «Равномерно»."
        )
        return

    await state.update_data(total=total)
    await state.set_state(AddWizardStates.confirm)
    await _show_confirm_step(message, await state.get_data())


@router.callback_query(AddWizardCB.filter(F.action == "save"), AddWizardStates.confirm)
async def save_result(callback: types.CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    await callback.answer()
    await callback.message.answer(
        "Результат збережено (демо). Ось підсумок:\n" + _format_summary(data),
        parse_mode="HTML",
    )


@router.callback_query(AddWizardCB.filter(F.action == "back"))
async def navigate_back(
    callback: types.CallbackQuery, state: FSMContext, callback_data: AddWizardCB
) -> None:
    target = callback_data.value
    await callback.answer()
    if target == "style":
        await state.set_state(AddWizardStates.choose_style)
        await _clear_after(state, ("style", "distance", "segments", "splits", "total"))
        await _show_style_step(callback.message)
    elif target == "distance":
        await state.set_state(AddWizardStates.choose_distance)
        await _clear_after(state, ("distance", "segments", "splits", "total"))
        await _show_distance_step(callback.message)
    elif target == "template":
        data = await state.get_data()
        distance = data.get("distance")
        if distance is None:
            await state.set_state(AddWizardStates.choose_distance)
            await _show_distance_step(callback.message)
            return
        await state.set_state(AddWizardStates.choose_template)
        await _clear_after(state, ("segments", "splits", "total"))
        await _show_template_step(callback.message, distance)
    elif target == "splits":
        data = await state.get_data()
        segments = data.get("segments") or ()
        await state.set_state(AddWizardStates.enter_splits)
        await _clear_after(state, ("splits", "total"))
        await _show_splits_step(callback.message, segments)
    elif target == "total":
        await state.set_state(AddWizardStates.enter_total)
        await _clear_after(state, ("total",))
        await _show_total_step(callback.message)
    else:
        await callback.message.answer("Ця дія недоступна.")
