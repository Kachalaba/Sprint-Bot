from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from typing import Optional

from aiogram import F, Router, types

from menu_callbacks import CB_MENU_INVITE
from role_service import ROLE_TRAINER, RoleService
from services import get_bot
from utils.roles import require_roles

logger = logging.getLogger(__name__)

router = Router()

active_invites: dict[str, int] = {}


@dataclass(frozen=True)
class InviteInfo:
    """Resolved invite payload linking athlete to trainer."""

    code: str
    trainer_id: int


def _generate_invite_code() -> str:
    """Return a short random token used in deep links."""

    return secrets.token_hex(4)


def _normalise_payload(raw: str | None) -> Optional[str]:
    if not raw:
        return None
    payload = raw.strip()
    if not payload:
        return None
    if "_" not in payload:
        return None
    prefix, token = payload.split("_", 1)
    if prefix.casefold() not in {"reg", "рег"}:
        return None
    token = token.strip()
    if not token:
        return None
    return token


def resolve_invite(payload: str | None) -> InviteInfo | None:
    """Return invite info for payload if the code is active."""

    token = _normalise_payload(payload)
    if not token:
        return None
    trainer_id = active_invites.get(token)
    if not trainer_id:
        return None
    return InviteInfo(code=token, trainer_id=trainer_id)


def consume_invite(code: str | None) -> None:
    """Remove invite code from active registry."""

    if not code:
        return
    active_invites.pop(code, None)


@router.callback_query(require_roles(ROLE_TRAINER), F.data == CB_MENU_INVITE)
async def send_invite(cb: types.CallbackQuery, role_service: RoleService) -> None:
    """Generate one-time invite link for a coach."""

    await role_service.upsert_user(cb.from_user, default_role=ROLE_TRAINER)
    code = _generate_invite_code()
    active_invites[code] = cb.from_user.id
    bot = get_bot()
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=\u0440\u0435\u0433_{code}"

    await cb.message.answer(f"Надішліть спортсмену це посилання:\n{link}")
    await cb.answer()
