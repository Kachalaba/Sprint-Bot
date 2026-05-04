"""ManageTemplates use case: validate and persist sprint templates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Protocol, Sequence


@dataclass(frozen=True, slots=True)
class TemplateInput:
    """Validated template payload sent to the repository."""

    title: str
    distance: int
    stroke: str
    hint: str = ""
    segments: tuple[float, ...] = field(default_factory=tuple)


class TemplateRepository(Protocol):
    """Subset of ``TemplateService`` consumed by the use case."""

    async def list_templates(self) -> Sequence[object]: ...
    async def get_template(self, template_id: str) -> object | None: ...
    async def create_template(
        self,
        *,
        title: str,
        dist: int,
        stroke: str,
        hint: str = "",
        segments: Iterable[float] | None = None,
        actor_id: int | None = None,
    ) -> object: ...
    async def update_template(
        self,
        template_id: str,
        *,
        title: str | None = None,
        dist: int | None = None,
        stroke: str | None = None,
        hint: str | None = None,
        segments: Iterable[float] | None = None,
        actor_id: int | None = None,
    ) -> object: ...
    async def delete_template(
        self, template_id: str, *, actor_id: int | None = None
    ) -> None: ...


class ManageTemplatesUseCase:
    """CRUD orchestration for sprint templates."""

    def __init__(self, *, repository: TemplateRepository) -> None:
        self._repo = repository

    async def list_templates(self) -> Sequence[object]:
        return await self._repo.list_templates()

    async def get_template(self, template_id: str) -> object | None:
        if not template_id.strip():
            raise ValueError("template_id must not be blank")
        return await self._repo.get_template(template_id)

    async def create_template(
        self, payload: TemplateInput, *, actor_id: int | None = None
    ) -> object:
        validated = self._validate(payload)
        return await self._repo.create_template(
            title=validated.title,
            dist=validated.distance,
            stroke=validated.stroke,
            hint=validated.hint,
            segments=validated.segments or None,
            actor_id=actor_id,
        )

    async def update_template(
        self,
        template_id: str,
        *,
        title: str | None = None,
        distance: int | None = None,
        stroke: str | None = None,
        hint: str | None = None,
        segments: tuple[float, ...] | None = None,
        actor_id: int | None = None,
    ) -> object:
        if not template_id.strip():
            raise ValueError("template_id must not be blank")
        if title is not None and not title.strip():
            raise ValueError("title must not be blank when provided")
        if distance is not None and distance <= 0:
            raise ValueError("distance must be positive when provided")
        if segments is not None and any(value <= 0 for value in segments):
            raise ValueError("each segment must be positive")
        return await self._repo.update_template(
            template_id,
            title=title,
            dist=distance,
            stroke=stroke,
            hint=hint,
            segments=segments,
            actor_id=actor_id,
        )

    async def delete_template(
        self, template_id: str, *, actor_id: int | None = None
    ) -> None:
        if not template_id.strip():
            raise ValueError("template_id must not be blank")
        await self._repo.delete_template(template_id, actor_id=actor_id)

    @staticmethod
    def _validate(payload: TemplateInput) -> TemplateInput:
        title = payload.title.strip()
        if not title:
            raise ValueError("title must not be blank")
        if payload.distance <= 0:
            raise ValueError("distance must be positive")
        stroke = payload.stroke.strip() or "freestyle"
        if any(value <= 0 for value in payload.segments):
            raise ValueError("each segment must be positive")
        return TemplateInput(
            title=title,
            distance=payload.distance,
            stroke=stroke,
            hint=payload.hint.strip(),
            segments=tuple(payload.segments),
        )


__all__ = [
    "ManageTemplatesUseCase",
    "TemplateInput",
    "TemplateRepository",
]
