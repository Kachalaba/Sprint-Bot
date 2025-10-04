from __future__ import annotations

import logging
import re
from html import escape
from typing import Sequence

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from i18n import t
from menu_callbacks import CB_MENU_TEMPLATES
from role_service import ROLE_ADMIN, ROLE_TRAINER, RoleService
from template_service import SprintTemplate, TemplateService
from utils import TemplateStates

logger = logging.getLogger(__name__)

router = Router()


class TemplateCB(CallbackData, prefix="tplm"):
    action: str
    template_id: str = ""


class StrokeCB(CallbackData, prefix="tpls"):
    mode: str
    template_id: str
    stroke: str


STROKES: Sequence[tuple[str, str]] = (
    ("freestyle", "Кроль"),
    ("backstroke", "Спина"),
    ("butterfly", "Батерфляй"),
    ("breaststroke", "Брас"),
    ("medley", "Комплекс"),
)


def _stroke_keyboard(mode: str, template_id: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for stroke, label in STROKES:
        row.append(
            InlineKeyboardButton(
                text=f"🏊‍♂️ {label}",
                callback_data=StrokeCB(
                    mode=mode, template_id=template_id, stroke=stroke
                ).pack(),
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _templates_keyboard(templates: Sequence[SprintTemplate]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=template.title,
                callback_data=TemplateCB(
                    action="open", template_id=template.template_id
                ).pack(),
            )
        ]
        for template in templates
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="➕ Новий шаблон",
                callback_data=TemplateCB(action="create").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _template_keyboard(template_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Назва",
                    callback_data=TemplateCB(
                        action="edit_title", template_id=template_id
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="📏 Дистанція",
                    callback_data=TemplateCB(
                        action="edit_distance", template_id=template_id
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🏊‍♂️ Стиль",
                    callback_data=TemplateCB(
                        action="edit_stroke", template_id=template_id
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="🔁 Відрізки",
                    callback_data=TemplateCB(
                        action="edit_segments", template_id=template_id
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="💡 Підказка",
                    callback_data=TemplateCB(
                        action="edit_hint", template_id=template_id
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Видалити",
                    callback_data=TemplateCB(
                        action="delete", template_id=template_id
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="⬅️ До списку",
                    callback_data=TemplateCB(action="back").pack(),
                ),
            ],
        ]
    )


def _stroke_label(stroke: str) -> str:
    for value, label in STROKES:
        if value == stroke:
            return label
    return stroke


def _resolve_hint(raw_hint: str) -> str:
    if not raw_hint:
        return ""
    hint = raw_hint.strip()
    if not hint:
        return ""
    if hint.startswith("tpl."):
        try:
            return t(hint)
        except KeyError:  # pragma: no cover - defensive fallback
            logger.warning("Missing translation for template hint '%s'", hint)
            return hint
    return hint


def _template_text(template: SprintTemplate) -> str:
    segments = template.segments or template.segments_or_default()
    segments_line = " + ".join(f"{value:g} м" for value in segments)
    hint_value = _resolve_hint(template.hint)
    hint_text = escape(hint_value) if hint_value else "(без підказки)"
    return (
        f"<b>{escape(template.title)}</b>\n"
        f"ID: <code>{escape(template.template_id)}</code>\n"
        f"Дистанція: <b>{template.dist} м</b>\n"
        f"Стиль: <b>{_stroke_label(template.stroke)}</b>\n"
        f"Відрізки: {segments_line}\n"
        f"Підказка: {hint_text}"
    )


def _parse_segments(raw: str, *, dist: int) -> tuple[float, ...]:
    text = raw.strip()
    if not text or text.lower() in {"default", "skip", "-"}:
        return ()
    parts = re.split(r"[\s,;]+", text.replace("+", " "))
    values: list[float] = []
    for chunk in parts:
        if not chunk:
            continue
        values.append(float(chunk))
    total = sum(values)
    if abs(total - dist) > 1e-6:
        raise ValueError("Сума відрізків має дорівнювати дистанції")
    return tuple(values)


async def _is_manager(user: types.User, role_service: RoleService) -> bool:
    role = await role_service.get_role(user.id)
    return role in {ROLE_ADMIN, ROLE_TRAINER}


async def _show_list(
    target: types.Message | types.CallbackQuery, template_service: TemplateService
) -> None:
    templates = await template_service.list_templates()
    text = (
        "📋 <b>Шаблони спринтів</b>. Оберіть один для редагування або створіть новий."
        if templates
        else "📋 <b>Шаблони спринтів</b>. Поки що порожньо — додайте перший шаблон."
    )
    keyboard = _templates_keyboard(templates)
    if isinstance(target, types.Message):
        await target.answer(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await target.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        await target.answer()


async def _show_template(
    target: types.Message | types.CallbackQuery, template: SprintTemplate
) -> None:
    if isinstance(target, types.Message):
        await target.answer(
            _template_text(template),
            reply_markup=_template_keyboard(template.template_id),
            parse_mode="HTML",
        )
    else:
        await target.message.answer(
            _template_text(template),
            reply_markup=_template_keyboard(template.template_id),
            parse_mode="HTML",
        )
        await target.answer()


@router.message(Command("templates"))
async def templates_menu(
    message: types.Message,
    state: FSMContext,
    template_service: TemplateService,
    role_service: RoleService,
) -> None:
    if not await _is_manager(message.from_user, role_service):
        await message.answer("Функція доступна лише тренерам та адміністраторам.")
        return
    await state.clear()
    await state.set_state(TemplateStates.menu)
    await _show_list(message, template_service)


@router.callback_query(F.data == CB_MENU_TEMPLATES)
async def menu_templates(
    cb: types.CallbackQuery,
    state: FSMContext,
    template_service: TemplateService,
    role_service: RoleService,
) -> None:
    """Open templates menu from the main menu."""

    if not await _is_manager(cb.from_user, role_service):
        await cb.answer("Недостатньо прав", show_alert=True)
        return
    await state.clear()
    await state.set_state(TemplateStates.menu)
    await _show_list(cb, template_service)


@router.callback_query(TemplateCB.filter())
async def template_actions(
    cb: types.CallbackQuery,
    callback_data: TemplateCB,
    state: FSMContext,
    template_service: TemplateService,
    role_service: RoleService,
) -> None:
    if not await _is_manager(cb.from_user, role_service):
        await cb.answer("Недостатньо прав", show_alert=True)
        return
    action = callback_data.action
    template_id = callback_data.template_id
    if action == "back":
        await state.set_state(TemplateStates.menu)
        await _show_list(cb, template_service)
        return
    if action == "create":
        await state.set_state(TemplateStates.create_title)
        await state.update_data(new_template={})
        await cb.message.answer("Введіть назву нового шаблону.")
        await cb.answer()
        return
    if action == "open":
        template = await template_service.get_template(template_id)
        if not template:
            await cb.answer("Шаблон не знайдено", show_alert=True)
            return
        await state.update_data(active_template_id=template.template_id)
        await state.set_state(TemplateStates.menu)
        await _show_template(cb, template)
        return
    if action == "delete":
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Видалити",
                        callback_data=TemplateCB(
                            action="confirm_delete", template_id=template_id
                        ).pack(),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ Скасувати",
                        callback_data=TemplateCB(
                            action="open", template_id=template_id
                        ).pack(),
                    )
                ],
            ]
        )
        await cb.message.answer("Підтвердіть видалення шаблону.", reply_markup=keyboard)
        await cb.answer()
        return
    if action == "confirm_delete":
        actor_id = cb.from_user.id if cb.from_user else None
        await template_service.delete_template(template_id, actor_id=actor_id)
        logger.info("Deleted sprint template %s", template_id)
        await state.set_state(TemplateStates.menu)
        await cb.message.answer("🗑 Шаблон видалено.")
        await _show_list(cb, template_service)
        return
    if action == "edit_stroke":
        await state.update_data(active_template_id=template_id)
        await state.set_state(TemplateStates.editing_stroke)
        await cb.message.answer(
            "Оберіть новий стиль:", reply_markup=_stroke_keyboard("edit", template_id)
        )
        await cb.answer()
        return
    if action in {"edit_title", "edit_distance", "edit_segments", "edit_hint"}:
        prompts = {
            "edit_title": "Введіть нову назву.",
            "edit_distance": "Вкажіть дистанцію у метрах.",
            "edit_segments": "Вкажіть відрізки через кому або напишіть 'default'.",
            "edit_hint": "Надішліть підказку або '-' щоб очистити її.",
        }
        await state.update_data(
            active_template_id=template_id,
            edit_field=action.replace("edit_", ""),
        )
        await state.set_state(TemplateStates.editing_value)
        await cb.message.answer(prompts[action])
        await cb.answer()
        return
    await cb.answer()


@router.message(TemplateStates.create_title)
async def create_title(message: types.Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if not title:
        await message.answer("Назва не може бути порожньою.")
        return
    await state.update_data(new_template={"title": title})
    await state.set_state(TemplateStates.create_distance)
    await message.answer("Вкажіть дистанцію у метрах.")


@router.message(TemplateStates.create_distance)
async def create_distance(message: types.Message, state: FSMContext) -> None:
    try:
        dist = int(message.text)
    except (TypeError, ValueError):
        await message.answer("Дистанція має бути цілим числом.")
        return
    if dist <= 0:
        await message.answer("Дистанція має бути більшою за нуль.")
        return
    data = await state.get_data()
    payload = data.get("new_template", {})
    payload["dist"] = dist
    await state.update_data(new_template=payload)
    await state.set_state(TemplateStates.create_stroke)
    await message.answer(
        "Оберіть стиль:", reply_markup=_stroke_keyboard("create", "__new__")
    )


@router.callback_query(StrokeCB.filter(F.mode == "create"))
async def create_stroke(
    cb: types.CallbackQuery, callback_data: StrokeCB, state: FSMContext
) -> None:
    data = await state.get_data()
    payload = data.get("new_template", {})
    payload["stroke"] = callback_data.stroke
    await state.update_data(new_template=payload)
    await state.set_state(TemplateStates.create_segments)
    await cb.message.answer(
        "Вкажіть відрізки через кому (наприклад 25,25,25,25) або напишіть 'default'."
    )
    await cb.answer()


@router.message(TemplateStates.create_segments)
async def create_segments(message: types.Message, state: FSMContext) -> None:
    data = await state.get_data()
    payload = data.get("new_template", {})
    dist = int(payload.get("dist", 0))
    if not dist:
        await message.answer("Помилка стану. Почніть з /templates.")
        await state.set_state(TemplateStates.menu)
        return
    text = message.text or ""
    try:
        payload["segments"] = _parse_segments(text, dist=dist)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(new_template=payload)
    await state.set_state(TemplateStates.create_hint)
    await message.answer("Додайте підказку або надішліть '-' щоб пропустити.")


@router.message(TemplateStates.create_hint)
async def create_hint(
    message: types.Message,
    state: FSMContext,
    template_service: TemplateService,
) -> None:
    data = await state.get_data()
    payload = data.get("new_template", {})
    title = payload.get("title")
    dist = payload.get("dist")
    stroke = payload.get("stroke")
    if not (title and dist and stroke):
        await message.answer("Не вистачає даних для створення шаблону.")
        await state.set_state(TemplateStates.menu)
        return
    hint = (message.text or "").strip()
    if hint == "-":
        hint = ""
    segments = payload.get("segments")
    actor_id = message.from_user.id if message.from_user else None
    template = await template_service.create_template(
        title=title,
        dist=int(dist),
        stroke=stroke,
        hint=hint,
        segments=segments,
        actor_id=actor_id,
    )
    logger.info("Created sprint template %s", template.template_id)
    await state.update_data(new_template=None)
    await state.set_state(TemplateStates.menu)
    await message.answer("✅ Шаблон створено!")
    await _show_template(message, template)


@router.callback_query(StrokeCB.filter(F.mode == "edit"))
async def edit_stroke(
    cb: types.CallbackQuery,
    callback_data: StrokeCB,
    state: FSMContext,
    template_service: TemplateService,
) -> None:
    actor_id = cb.from_user.id if cb.from_user else None
    template = await template_service.update_template(
        callback_data.template_id,
        stroke=callback_data.stroke,
        actor_id=actor_id,
    )
    logger.info("Updated sprint template %s stroke", template.template_id)
    await state.set_state(TemplateStates.menu)
    await cb.answer("Оновлено")
    await _show_template(cb, template)


@router.message(TemplateStates.editing_value)
async def apply_edit(
    message: types.Message,
    state: FSMContext,
    template_service: TemplateService,
) -> None:
    data = await state.get_data()
    template_id = data.get("active_template_id")
    field = data.get("edit_field")
    if not template_id or not field:
        await message.answer("Не знайдено шаблон. Почніть з /templates.")
        await state.set_state(TemplateStates.menu)
        return
    text = (message.text or "").strip()
    actor_id = message.from_user.id if message.from_user else None
    try:
        if field == "title":
            if not text:
                raise ValueError("Назва не може бути порожньою")
            template = await template_service.update_template(
                template_id, title=text, actor_id=actor_id
            )
        elif field == "distance":
            dist = int(text)
            if dist <= 0:
                raise ValueError("Дистанція має бути більшою за нуль")
            template = await template_service.update_template(
                template_id, dist=dist, actor_id=actor_id
            )
        elif field == "hint":
            template = await template_service.update_template(
                template_id, hint="" if text == "-" else text, actor_id=actor_id
            )
        elif field == "segments":
            current = await template_service.get_template(template_id)
            if not current:
                raise ValueError("Шаблон не знайдено")
            segments = _parse_segments(text, dist=current.dist)
            template = await template_service.update_template(
                template_id, segments=segments, actor_id=actor_id
            )
        else:
            raise ValueError("Невідоме поле")
    except ValueError as exc:
        await message.answer(str(exc))
        return
    except KeyError:
        await message.answer("Шаблон не знайдено. Оновіть список /templates.")
        await state.set_state(TemplateStates.menu)
        return
    await state.set_state(TemplateStates.menu)
    logger.info("Updated sprint template %s field %s", template_id, field)
    await message.answer("✅ Оновлено.")
    await _show_template(message, template)
