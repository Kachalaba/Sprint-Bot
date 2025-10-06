import asyncio
from types import SimpleNamespace

import pytest

from middlewares.roles import RoleMiddleware
from utils.roles import RequireRolesFilter, require_roles


class StubRoleService:
    def __init__(self, mapping: dict[int, str]) -> None:
        self.mapping = mapping

    async def get_role(self, user_id: int) -> str:
        return self.mapping.get(user_id, "athlete")


def test_require_roles_accepts_role_from_context() -> None:
    filt = require_roles("admin")
    event = SimpleNamespace(from_user=SimpleNamespace(id=1))
    assert asyncio.run(filt(event, user_role="admin"))


def test_require_roles_fetches_role_from_service() -> None:
    service = StubRoleService({2: "coach"})
    filt = require_roles("coach")
    event = SimpleNamespace(from_user=SimpleNamespace(id=2))
    result = asyncio.run(filt(event, role_service=service))
    assert result == {"user_role": "coach"}


def test_require_roles_denies_without_service() -> None:
    filt = require_roles("admin")
    event = SimpleNamespace(from_user=SimpleNamespace(id=3))
    assert not asyncio.run(filt(event))


def test_require_roles_denies_when_user_missing() -> None:
    filt = require_roles("admin")
    event = SimpleNamespace()
    assert not asyncio.run(filt(event, role_service=StubRoleService({})))


def test_require_roles_extend_creates_new_filter() -> None:
    base = RequireRolesFilter("coach")
    extended = base.extend(["admin"])
    assert base is not extended
    assert base.allowed_roles == {"coach"}
    assert extended.allowed_roles == {"coach", "admin"}


def test_require_roles_raises_without_roles() -> None:
    with pytest.raises(ValueError):
        require_roles()


def test_role_middleware_injects_role() -> None:
    service = StubRoleService({5: "admin"})
    middleware = RoleMiddleware(service)
    event = SimpleNamespace(from_user=SimpleNamespace(id=5))
    data: dict[str, str] = {}

    async def handler(evt, ctx):
        return ctx["user_role"], ctx is data

    role, same_data = asyncio.run(middleware(handler, event, data))
    assert role == "admin"
    assert same_data
