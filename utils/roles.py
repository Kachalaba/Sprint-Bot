"""Role-based access helpers."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Set, Tuple

from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject

from i18n import t
from role_service import ROLE_ADMIN, ROLE_ATHLETE, ROLE_TRAINER, RoleService

DEFAULT_ROLE_KEY = "user_role"

_ROLE_LABEL_KEYS: Dict[str, str] = {
    ROLE_ATHLETE: "roles.athlete",
    ROLE_TRAINER: "roles.trainer",
    ROLE_ADMIN: "roles.admin",
}


def _normalize_roles(roles: Iterable[str]) -> Tuple[str, ...]:
    """Return tuple of roles preserving the initial order without duplicates."""

    seen: Dict[str, None] = {}
    for role in roles:
        role_key = str(role)
        if role_key not in seen:
            seen[role_key] = None
    return tuple(seen.keys())


def localize_role(role: str, *, lang: str | None = None) -> str:
    """Return localized label for the provided role identifier."""

    translation_key = _ROLE_LABEL_KEYS.get(role)
    if translation_key is None:
        return str(role)
    return t(translation_key, lang=lang)


def build_forbidden_message(roles: Iterable[str], *, lang: str | None = None) -> str:
    """Compose localized forbidden message with a role hint."""

    base_message = t("error.forbidden", lang=lang)
    normalized = _normalize_roles(roles)
    if not normalized:
        return base_message

    localized_roles = " / ".join(localize_role(role, lang=lang) for role in normalized)
    hint = t("error.need_role", lang=lang, role=localized_roles)
    return f"{base_message}\n{hint}"


class RequireRolesFilter(BaseFilter):
    """Filter allowing events only for specific roles."""

    def __init__(self, *roles: str, context_key: str = DEFAULT_ROLE_KEY) -> None:
        if not roles:
            raise ValueError("require_roles() expects at least one role")
        normalized_roles = _normalize_roles(roles)
        self.allowed_roles: Set[str] = set(normalized_roles)
        self._ordered_roles: Tuple[str, ...] = normalized_roles
        self.context_key = context_key

    async def __call__(
        self, event: TelegramObject, data: Dict[str, Any] | None = None
    ) -> bool:
        context = data if data is not None else {}
        role = context.get(self.context_key)
        if role is None:
            role_service: RoleService | None = context.get("role_service")
            user = getattr(event, "from_user", None)
            if role_service is None or user is None:
                return False
            role = await role_service.get_role(user.id)
            context[self.context_key] = role
        return str(role) in self.allowed_roles

    def extend(self, roles: Iterable[str]) -> "RequireRolesFilter":
        """Return new filter instance with additional roles allowed."""

        combined_roles = _normalize_roles((*self._ordered_roles, *roles))
        return RequireRolesFilter(*combined_roles, context_key=self.context_key)

    def get_required_roles(self) -> Tuple[str, ...]:
        """Return tuple of roles accepted by the filter preserving order."""

        return self._ordered_roles

    def get_forbidden_message(self, *, lang: str | None = None) -> str:
        """Return localized forbidden message describing required roles."""

        return build_forbidden_message(self._ordered_roles, lang=lang)


def require_roles(
    *roles: str, context_key: str = DEFAULT_ROLE_KEY
) -> RequireRolesFilter:
    """Shortcut returning :class:`RequireRolesFilter` instance."""

    return RequireRolesFilter(*roles, context_key=context_key)
