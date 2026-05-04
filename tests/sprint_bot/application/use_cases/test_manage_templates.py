from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from sprint_bot.application.use_cases import (
    ManageTemplatesUseCase,
    TemplateInput,
)


@pytest.mark.asyncio
async def test_create_template_normalises_payload() -> None:
    repo = AsyncMock()
    repo.create_template = AsyncMock(return_value="TEMPLATE")

    use_case = ManageTemplatesUseCase(repository=repo)
    payload = TemplateInput(
        title="  Sprint 100  ",
        distance=100,
        stroke="  ",
        hint="  warmup  ",
        segments=(25.0, 25.0),
    )
    result = await use_case.create_template(payload, actor_id=11)

    repo.create_template.assert_awaited_once_with(
        title="Sprint 100",
        dist=100,
        stroke="freestyle",
        hint="warmup",
        segments=(25.0, 25.0),
        actor_id=11,
    )
    assert result == "TEMPLATE"


@pytest.mark.asyncio
async def test_create_template_validates_inputs() -> None:
    use_case = ManageTemplatesUseCase(repository=AsyncMock())
    with pytest.raises(ValueError, match="title"):
        await use_case.create_template(
            TemplateInput(title="   ", distance=100, stroke="free")
        )
    with pytest.raises(ValueError, match="distance"):
        await use_case.create_template(
            TemplateInput(title="Ok", distance=0, stroke="free")
        )
    with pytest.raises(ValueError, match="segment"):
        await use_case.create_template(
            TemplateInput(
                title="Ok", distance=100, stroke="free", segments=(25, -1)
            )
        )


@pytest.mark.asyncio
async def test_update_template_validates_partial() -> None:
    repo = AsyncMock()
    repo.update_template = AsyncMock(return_value="UPDATED")

    use_case = ManageTemplatesUseCase(repository=repo)

    await use_case.update_template("tpl", title="New", actor_id=4)
    repo.update_template.assert_awaited_with(
        "tpl",
        title="New",
        dist=None,
        stroke=None,
        hint=None,
        segments=None,
        actor_id=4,
    )

    with pytest.raises(ValueError, match="template_id"):
        await use_case.update_template(" ")
    with pytest.raises(ValueError, match="title"):
        await use_case.update_template("tpl", title="")
    with pytest.raises(ValueError, match="distance"):
        await use_case.update_template("tpl", distance=0)
    with pytest.raises(ValueError, match="segment"):
        await use_case.update_template("tpl", segments=(25, 0))


@pytest.mark.asyncio
async def test_delete_template_validates_id() -> None:
    repo = AsyncMock()
    use_case = ManageTemplatesUseCase(repository=repo)

    await use_case.delete_template("tpl", actor_id=1)
    repo.delete_template.assert_awaited_with("tpl", actor_id=1)

    with pytest.raises(ValueError, match="template_id"):
        await use_case.delete_template(" ")


@pytest.mark.asyncio
async def test_get_template_returns_repo_value() -> None:
    repo = AsyncMock()
    repo.get_template = AsyncMock(return_value="TPL")

    use_case = ManageTemplatesUseCase(repository=repo)
    assert await use_case.get_template("tpl") == "TPL"

    with pytest.raises(ValueError, match="template_id"):
        await use_case.get_template(" ")
