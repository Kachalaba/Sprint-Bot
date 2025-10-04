from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from i18n import t
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
    enter_turn_details = State()
    enter_total = State()
    confirm = State()


@dataclass(frozen=True, slots=True)
class StrokeOption:
    """Configuration for stroke selection options."""

    code: str
    callback_id: str


STROKE_OPTIONS: tuple[StrokeOption, ...] = (
    StrokeOption(code="freestyle", callback_id="STROKE_FREESTYLE"),
    StrokeOption(code="backstroke", callback_id="STROKE_BACKSTROKE"),
    StrokeOption(code="butterfly", callback_id="STROKE_BUTTERFLY"),
    StrokeOption(code="breaststroke", callback_id="STROKE_BREASTSTROKE"),
    StrokeOption(code="medley", callback_id="STROKE_MEDLEY"),
)

STROKE_ID_TO_CODE: dict[str, str] = {
    option.callback_id: option.code for option in STROKE_OPTIONS
}
STROKE_CODES: set[str] = {option.code for option in STROKE_OPTIONS}

DISTANCE_CHOICES: tuple[int, ...] = (50, 100, 200, 400, 800)

_TYPE_ENCODINGS: dict[str, str] = {"swim": "s", "turn": "t"}
_TYPE_DECODINGS: dict[str, str] = {value: key for key, value in _TYPE_ENCODINGS.items()}


def _count_turn_segments(segment_types: Sequence[str]) -> int:
    """Return number of turn segments in provided type list."""

    return sum(1 for seg_type in segment_types if seg_type == "turn")


def _count_swim_segments(segment_types: Sequence[str], fallback: int) -> int:
    """Return number of swim segments, falling back if types missing."""

    if not segment_types:
        return fallback
    return len(segment_types) - _count_turn_segments(segment_types)


def _combine_times_by_type(
    segment_types: Sequence[str],
    swim_times: Sequence[float],
    turn_times: Sequence[float],
) -> list[float]:
    """Return combined sequence of swim and turn times in template order."""

    if not segment_types:
        return list(swim_times)
    combined: list[float] = []
    swim_iter = iter(swim_times)
    turn_iter = iter(turn_times)
    for seg_type in segment_types:
        if seg_type == "turn":
            try:
                combined.append(next(turn_iter))
            except StopIteration:  # pragma: no cover - defensive fallback
                combined.append(0.0)
        else:
            try:
                combined.append(next(swim_iter))
            except StopIteration:  # pragma: no cover - defensive fallback
                combined.append(0.0)
    combined.extend(list(swim_iter))
    combined.extend(list(turn_iter))
    return combined


def _needs_turn_step(stroke: str | None, segment_types: Sequence[str]) -> bool:
    """Return True if turn data entry is required for selected stroke."""

    if stroke not in {"breaststroke", "butterfly"}:
        return False
    return any(seg_type == "turn" for seg_type in segment_types)


@dataclass(frozen=True, slots=True)
class SegmentTemplate:
    """Template describing segment distribution for a distance."""

    label: str
    segments: tuple[float, ...]
    segment_types: tuple[str, ...]


def _generate_segment_templates(
    distance: int, stroke: str | None = None
) -> tuple[SegmentTemplate, ...]:
    """Return default segment templates for provided distance."""

    if distance <= 0:
        return (
            SegmentTemplate(
                label=f"{distance} м",
                segments=(float(distance),),
                segment_types=("swim",),
            ),
        )

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
        templates.append(
            SegmentTemplate(
                label=f"{parts}×{segments[0]:g} м" if parts > 1 else f"{distance} м",
                segments=segments,
                segment_types=tuple("swim" for _ in segments),
            )
        )

    if stroke in {"breaststroke", "butterfly"} and distance % 25 == 0 and distance > 25:
        lengths = distance // 25
        turn_segments: list[float] = []
        turn_types: list[str] = []
        for index in range(lengths):
            turn_segments.append(25.0)
            turn_types.append("swim")
            if index != lengths - 1:
                turn_segments.append(0.0)
                turn_types.append("turn")
        label_parts: list[str] = []
        for value, seg_type in zip(turn_segments, turn_types):
            if seg_type == "turn":
                label_parts.append("поворот")
            else:
                label_parts.append(f"{value:g} м")
        templates.insert(
            0,
            SegmentTemplate(
                label=" + ".join(label_parts),
                segments=tuple(turn_segments),
                segment_types=tuple(turn_types),
            ),
        )
    return tuple(templates)


def _style_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for option in STROKE_OPTIONS:
        row.append(
            InlineKeyboardButton(
                text=t(f"stroke.{option.code}"),
                callback_data=AddWizardCB(
                    action="style", value=option.callback_id
                ).pack(),
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


def _encode_template_payload(template: SegmentTemplate) -> str:
    """Return compact payload for template selection callback."""

    parts: list[str] = []
    for value, seg_type in zip(template.segments, template.segment_types):
        suffix = _TYPE_ENCODINGS.get(seg_type, "s")
        parts.append(f"{value:g}{suffix}")
    return "|".join(parts)


def _decode_template_payload(payload: str) -> tuple[tuple[float, ...], tuple[str, ...]]:
    """Decode template selection payload back to segments and types."""

    segments: list[float] = []
    segment_types: list[str] = []
    if not payload:
        return tuple(segments), tuple(segment_types)
    for chunk in payload.split("|"):
        if not chunk:
            continue
        type_code = chunk[-1]
        value_part = chunk[:-1]
        if type_code not in _TYPE_DECODINGS or not value_part:
            value_part = chunk
            seg_type = "swim"
        else:
            seg_type = _TYPE_DECODINGS[type_code]
        try:
            value = float(value_part)
        except ValueError:
            continue
        segments.append(value)
        segment_types.append(seg_type)
    return tuple(segments), tuple(segment_types)


def _template_keyboard(distance: int, stroke: str | None) -> InlineKeyboardMarkup:
    templates = _generate_segment_templates(distance, stroke)
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for template in templates:
        row.append(
            InlineKeyboardButton(
                text=template.label,
                callback_data=AddWizardCB(
                    action="template",
                    value=_encode_template_payload(template),
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
                    text=t("add.btn.autosum"),
                    callback_data=AddWizardCB(action="autosum").pack(),
                )
            ],
            wizard_navigation_row(back_target="template"),
        ]
    )


def _turn_details_keyboard() -> InlineKeyboardMarkup:
    """Return navigation keyboard for turn detail input."""

    return InlineKeyboardMarkup(
        inline_keyboard=[wizard_navigation_row(back_target="splits")]
    )


def _total_keyboard(back_target: str = "splits") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("add.btn.distribute"),
                    callback_data=AddWizardCB(action="even").pack(),
                )
            ],
            wizard_navigation_row(back_target=back_target),
        ]
    )


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("common.save"),
                    callback_data=AddWizardCB(action="save").pack(),
                )
            ],
            wizard_navigation_row(back_target="total"),
        ]
    )


def _format_segments_line(
    segments: Sequence[float], segment_types: Sequence[str]
) -> str:
    """Return human readable segment label including turns."""

    if not segments:
        return ""
    if len(segments) != len(segment_types) or not segment_types:
        return " + ".join(f"{value:g} м" for value in segments)
    parts: list[str] = []
    for value, seg_type in zip(segments, segment_types):
        if seg_type == "turn":
            parts.append("поворот")
        else:
            parts.append(f"{value:g} м")
    return " + ".join(parts)


def _format_turn_summary(turn_times: Sequence[float]) -> str:
    """Return formatted list of turn times for summary output."""

    if not turn_times:
        return "—"
    formatted: list[str] = []
    for index, value in enumerate(turn_times, start=1):
        formatted.append(f"#{index}: {fmt_time(value)}")
    return ", ".join(formatted)


def _format_summary(data: dict) -> str:
    style_code = data.get("style")
    style_label = t(f"stroke.{style_code}") if style_code else ""
    if not style_label and style_code:
        style_label = style_code
    distance = data.get("distance")
    segments = data.get("segments", [])
    segment_types = data.get("segment_types", [])
    splits = data.get("splits", [])
    turn_times = data.get("turn_times", [])
    total = data.get("total")
    segments_line = _format_segments_line(segments, segment_types)
    splits_line = ", ".join(fmt_time(value) for value in splits)
    turn_summary = _format_turn_summary(turn_times)
    total_line = fmt_time(total) if total is not None else "—"
    summary = t(
        "add.summary",
        style=style_label,
        distance=f"{distance} м" if distance is not None else "—",
        segments=segments_line or "—",
        splits=splits_line or "—",
        total=total_line,
        turns=turn_summary,
    )
    return summary


async def _show_style_step(message: types.Message) -> None:
    await message.answer(
        t("add.step.style"),
        reply_markup=_style_keyboard(),
    )


async def _show_distance_step(message: types.Message) -> None:
    await message.answer(
        t("add.step.distance"),
        reply_markup=_distance_keyboard(),
    )


async def _show_template_step(
    message: types.Message, distance: int, stroke: str | None
) -> None:
    await message.answer(
        t("add.step.template", distance=distance),
        reply_markup=_template_keyboard(distance, stroke),
    )


async def _show_splits_step(message: types.Message, _segments: Iterable[float]) -> None:
    await message.answer(
        t("add.step.splits"),
        reply_markup=_splits_keyboard(),
    )


async def _show_turn_details_step(message: types.Message, turn_count: int) -> None:
    await message.answer(
        t("add.step.turns", count=turn_count),
        reply_markup=_turn_details_keyboard(),
    )


async def _show_total_step(message: types.Message, back_target: str) -> None:
    await message.answer(
        t("add.step.total"),
        reply_markup=_total_keyboard(back_target),
    )


async def _show_confirm_step(message: types.Message, data: dict) -> None:
    summary = _format_summary(data)
    await message.answer(
        f"{t('add.step.confirm')}\n\n{summary}",
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


@router.callback_query(
    AddWizardCB.filter(F.action == "style"), AddWizardStates.choose_style
)
async def choose_style(
    callback: types.CallbackQuery, state: FSMContext, callback_data: AddWizardCB
) -> None:
    style_code = STROKE_ID_TO_CODE.get(callback_data.value, callback_data.value)
    if style_code not in STROKE_CODES:
        await callback.answer()
        return
    await state.update_data(style=style_code)
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
    await _clear_after(
        state,
        ("segments", "segment_types", "splits", "turn_times", "total"),
    )
    await state.set_state(AddWizardStates.choose_template)
    data = await state.get_data()
    await _show_template_step(callback.message, distance, data.get("style"))


@router.callback_query(
    AddWizardCB.filter(F.action == "template"), AddWizardStates.choose_template
)
async def choose_template(
    callback: types.CallbackQuery, state: FSMContext, callback_data: AddWizardCB
) -> None:
    await callback.answer()
    segments, segment_types = _decode_template_payload(callback_data.value)
    if not segment_types and segments:
        segment_types = tuple("swim" for _ in segments)
    await state.update_data(segments=segments, segment_types=list(segment_types))
    await _clear_after(state, ("splits", "turn_times", "total"))
    await state.set_state(AddWizardStates.enter_splits)
    await _show_splits_step(callback.message, segments)


@router.callback_query(
    AddWizardCB.filter(F.action == "autosum"), AddWizardStates.enter_splits
)
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
        await message.answer(t("error.invalid_time"))
        return

    data = await state.get_data()
    segments = data.get("segments") or ()
    segment_types = data.get("segment_types") or ()
    expected_splits = _count_swim_segments(segment_types, len(segments))
    if segments and expected_splits and expected_splits != len(splits):
        await message.answer(
            "Кількість сплітів не відповідає шаблону. Спробуйте ще раз."
        )
        return

    await state.update_data(splits=splits)
    turn_required = _needs_turn_step(data.get("style"), segment_types)
    if turn_required:
        turn_count = _count_turn_segments(segment_types)
        if turn_count > 0:
            await state.set_state(AddWizardStates.enter_turn_details)
            await _show_turn_details_step(message, turn_count)
            return
    await state.set_state(AddWizardStates.enter_total)
    back_target = "turns" if turn_required else "splits"
    await _show_total_step(message, back_target)


@router.message(AddWizardStates.enter_turn_details)
async def input_turn_details(message: types.Message, state: FSMContext) -> None:
    """Handle turn detail input for strokes that require it."""

    text = message.text or ""
    chunks = text.replace(",", " ").split()
    try:
        turn_times = parse_splits(chunks)
    except ValueError:
        await message.answer(t("error.invalid_time"))
        return

    data = await state.get_data()
    segment_types = data.get("segment_types") or ()
    expected_turns = _count_turn_segments(segment_types)
    if expected_turns and len(turn_times) != expected_turns:
        await message.answer(
            "Кількість поворотів не відповідає шаблону. Спробуйте ще раз."
        )
        return

    await state.update_data(turn_times=turn_times)
    await state.set_state(AddWizardStates.enter_total)
    await _show_total_step(message, "turns")


@router.callback_query(
    AddWizardCB.filter(F.action == "even"), AddWizardStates.enter_total
)
async def even_from_total(callback: types.CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    total = data.get("total")
    segments = data.get("segments") or ()
    segment_types = data.get("segment_types") or ()
    turn_times = data.get("turn_times") or []
    if not segment_types:
        turn_times = []
    if total is None:
        await callback.answer("Спочатку введіть сумарний час.", show_alert=True)
        return
    if not segments:
        await callback.answer("Немає даних про шаблон відрізків.", show_alert=True)
        return
    if segment_types:
        swim_segments = [
            value
            for value, seg_type in zip(segments, segment_types)
            if seg_type != "turn"
        ]
    else:
        swim_segments = list(segments)
    if not swim_segments:
        await callback.answer(
            "Немає відрізків для розрахунку сплітів.", show_alert=True
        )
        return
    distance = float(sum(swim_segments))
    if distance <= 0:
        await callback.answer("Невірний шаблон відрізків.", show_alert=True)
        return
    available_total = total - sum(float(value) for value in turn_times)
    if available_total <= 0:
        await callback.answer(
            "Total має бути більшим за суму поворотів.",
            show_alert=True,
        )
        return
    factor = available_total / distance
    splits = [round(segment * factor, 5) for segment in swim_segments]
    await state.update_data(splits=splits)
    await callback.answer()
    await callback.message.answer(
        "Спліти оновлено рівномірно: " + ", ".join(fmt_time(value) for value in splits)
    )


@router.message(AddWizardStates.enter_total)
async def input_total(message: types.Message, state: FSMContext) -> None:
    text = message.text or ""
    try:
        total = parse_total(text)
    except ValueError:
        await message.answer(t("error.invalid_time"))
        return

    data = await state.get_data()
    splits = data.get("splits") or []
    segment_types = data.get("segment_types") or []
    turn_times = data.get("turn_times") or []
    if not segment_types:
        turn_times = []
    combined_splits = _combine_times_by_type(segment_types, splits, turn_times)
    try:
        validate_splits(total, combined_splits)
    except ValueError:
        diff = abs(sum(float(value) for value in combined_splits) - total)
        await message.answer(t("error.splits_mismatch", diff=fmt_time(diff)))
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
        await _clear_after(
            state,
            (
                "style",
                "distance",
                "segments",
                "segment_types",
                "splits",
                "turn_times",
                "total",
            ),
        )
        await _show_style_step(callback.message)
    elif target == "distance":
        await state.set_state(AddWizardStates.choose_distance)
        await _clear_after(
            state,
            ("distance", "segments", "segment_types", "splits", "turn_times", "total"),
        )
        await _show_distance_step(callback.message)
    elif target == "template":
        data = await state.get_data()
        distance = data.get("distance")
        if distance is None:
            await state.set_state(AddWizardStates.choose_distance)
            await _show_distance_step(callback.message)
            return
        await state.set_state(AddWizardStates.choose_template)
        await _clear_after(
            state, ("segments", "segment_types", "splits", "turn_times", "total")
        )
        await _show_template_step(callback.message, distance, data.get("style"))
    elif target == "splits":
        data = await state.get_data()
        segments = data.get("segments") or ()
        await state.set_state(AddWizardStates.enter_splits)
        await _clear_after(state, ("splits", "turn_times", "total"))
        await _show_splits_step(callback.message, segments)
    elif target == "turns":
        data = await state.get_data()
        turn_count = _count_turn_segments(data.get("segment_types") or ())
        await state.set_state(AddWizardStates.enter_turn_details)
        await _clear_after(state, ("turn_times", "total"))
        if turn_count > 0:
            await _show_turn_details_step(callback.message, turn_count)
        else:
            await callback.message.answer("Поворотів у цьому шаблоні немає.")
    elif target == "total":
        await state.set_state(AddWizardStates.enter_total)
        await _clear_after(state, ("total",))
        data = await state.get_data()
        back_target = (
            "turns"
            if _needs_turn_step(data.get("style"), data.get("segment_types") or ())
            else "splits"
        )
        await _show_total_step(callback.message, back_target)
    else:
        await callback.message.answer("Ця дія недоступна.")
