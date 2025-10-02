from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Iterable, Sequence, TYPE_CHECKING

from utils import get_segments

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover - typing helpers only
    from services.audit_service import AuditService


@dataclass(slots=True)
class SprintTemplate:
    """Data model describing reusable sprint presets."""

    template_id: str
    title: str
    dist: int
    stroke: str
    hint: str = ""
    segments: tuple[float, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        """Serialize template to JSON-friendly dict."""

        payload = {
            "template_id": self.template_id,
            "title": self.title,
            "dist": self.dist,
            "stroke": self.stroke,
            "hint": self.hint,
        }
        if self.segments:
            payload["segments"] = list(self.segments)
        return payload

    @classmethod
    def from_dict(cls, raw: dict) -> "SprintTemplate":
        """Build template instance from raw data."""

        segments = raw.get("segments") or ()
        if segments:
            segments = tuple(float(value) for value in segments)
        return cls(
            template_id=str(raw["template_id"]),
            title=str(raw.get("title", "Без назви")),
            dist=int(raw.get("dist", 0)),
            stroke=str(raw.get("stroke", "freestyle")),
            hint=str(raw.get("hint", "")),
            segments=tuple(segments),
        )

    def segments_or_default(self) -> tuple[float, ...]:
        """Return stored segments or calculate defaults for the distance."""

        if self.segments:
            return self.segments
        return tuple(float(v) for v in get_segments(self.dist))


DEFAULT_TEMPLATES: tuple[SprintTemplate, ...] = (
    SprintTemplate(
        template_id="50_free",
        title="⚡️ 50 м кроль",
        dist=50,
        stroke="freestyle",
        hint="4×12.5 м — вибуховий старт та потужний фініш.",
        segments=(12.5, 12.5, 12.5, 12.5),
    ),
    SprintTemplate(
        template_id="100_free",
        title="🔥 100 м кроль",
        dist=100,
        stroke="freestyle",
        hint="4×25 м. Другий відрізок контрольний, третій — прискорення.",
        segments=(25, 25, 25, 25),
    ),
    SprintTemplate(
        template_id="100_fly",
        title="🦋 100 м батерфляй",
        dist=100,
        stroke="butterfly",
        hint="4×25 м. Тримайте стабільну техніку й темп.",
        segments=(25, 25, 25, 25),
    ),
    SprintTemplate(
        template_id="200_mixed",
        title="🥇 200 м комплекс",
        dist=200,
        stroke="medley",
        hint="По 50 м на стиль: батерфляй, спина, брас, кроль.",
        segments=(50, 50, 50, 50),
    ),
)


class TemplateService:
    """Manage persistent sprint templates stored in JSON file."""

    def __init__(
        self,
        storage_path: str | Path = Path("data/sprint_templates.json"),
        audit_service: "AuditService" | None = None,
    ) -> None:
        self._path = Path(storage_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._audit = audit_service

    async def init(self) -> None:
        """Ensure storage file exists and contains valid JSON."""

        async with self._lock:
            if not self._path.exists():
                logger.info("Creating sprint template storage at %s", self._path)
                await asyncio.to_thread(self._write_all, list(DEFAULT_TEMPLATES))
                return
            try:
                await asyncio.to_thread(self._read_raw)
            except json.JSONDecodeError:
                logger.warning(
                    "Invalid sprint template storage detected. Recreating with defaults.",
                )
                await asyncio.to_thread(self._write_all, list(DEFAULT_TEMPLATES))

    async def list_templates(self) -> Sequence[SprintTemplate]:
        """Return all available templates sorted by title."""

        async with self._lock:
            templates = await asyncio.to_thread(self._read_all)
        return tuple(sorted(templates, key=lambda tpl: tpl.title.lower()))

    async def get_template(self, template_id: str) -> SprintTemplate | None:
        """Return template by identifier or None if missing."""

        templates = await self.list_templates()
        for template in templates:
            if template.template_id == template_id:
                return template
        return None

    async def create_template(
        self,
        *,
        title: str,
        dist: int,
        stroke: str,
        hint: str = "",
        segments: Iterable[float] | None = None,
        actor_id: int | None = None,
    ) -> SprintTemplate:
        """Create new template and persist it."""

        title_clean = title.strip()
        if not title_clean:
            raise ValueError("Title must not be empty")
        if dist <= 0:
            raise ValueError("Distance must be positive")

        async with self._lock:
            existing = await asyncio.to_thread(self._read_all)
            template_id = self._generate_id(title_clean, existing)
            normalized_segments = self._normalize_segments(segments, dist)
            template = SprintTemplate(
                template_id=template_id,
                title=title_clean,
                dist=int(dist),
                stroke=stroke.strip() or "freestyle",
                hint=hint.strip(),
                segments=normalized_segments,
            )
            existing.append(template)
            await asyncio.to_thread(self._write_all, existing)
            logger.info("Created sprint template %s", template_id)
            if self._audit and actor_id is not None and actor_id > 0:
                await self._audit.log_template_create(
                    actor_id=actor_id,
                    template_id=template_id,
                    after=template.to_dict(),
                )
            return template

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
    ) -> SprintTemplate:
        """Update existing template and return new value."""

        async with self._lock:
            templates = await asyncio.to_thread(self._read_all)
            for idx, template in enumerate(templates):
                if template.template_id != template_id:
                    continue
                updated = SprintTemplate(
                    template_id=template.template_id,
                    title=template.title,
                    dist=template.dist,
                    stroke=template.stroke,
                    hint=template.hint,
                    segments=template.segments,
                )
                if title is not None:
                    title_clean = title.strip()
                    if not title_clean:
                        raise ValueError("Title must not be empty")
                    updated = replace(updated, title=title_clean)
                if dist is not None:
                    if dist <= 0:
                        raise ValueError("Distance must be positive")
                    updated = replace(updated, dist=int(dist))
                if stroke is not None:
                    updated = replace(updated, stroke=stroke.strip() or template.stroke)
                if hint is not None:
                    updated = replace(updated, hint=hint.strip())
                if segments is not None:
                    normalized_segments = self._normalize_segments(
                        segments, dist if dist is not None else updated.dist
                    )
                    updated = replace(updated, segments=normalized_segments)
                if dist is not None and segments is None:
                    normalized_segments: tuple[float, ...] = ()
                    if template.segments:
                        try:
                            normalized_segments = self._normalize_segments(
                                template.segments, dist
                            )
                        except ValueError:
                            normalized_segments = ()
                    updated = replace(updated, segments=normalized_segments)
                templates[idx] = updated
                await asyncio.to_thread(self._write_all, templates)
                logger.info("Updated sprint template %s", template_id)
                if self._audit and actor_id is not None and actor_id > 0:
                    await self._audit.log_template_update(
                        actor_id=actor_id,
                        template_id=template_id,
                        before=template.to_dict(),
                        after=updated.to_dict(),
                    )
                return updated
        raise KeyError(f"Template {template_id} not found")

    async def delete_template(
        self,
        template_id: str,
        *,
        actor_id: int | None = None,
    ) -> bool:
        """Remove template by identifier."""

        async with self._lock:
            templates = await asyncio.to_thread(self._read_all)
            new_templates = [tpl for tpl in templates if tpl.template_id != template_id]
            if len(new_templates) == len(templates):
                return False
            removed: SprintTemplate | None = None
            for tpl in templates:
                if tpl.template_id == template_id:
                    removed = tpl
                    break
            await asyncio.to_thread(self._write_all, new_templates)
            logger.info("Deleted sprint template %s", template_id)
            if (
                removed is not None
                and self._audit
                and actor_id is not None
                and actor_id > 0
            ):
                await self._audit.log_template_delete(
                    actor_id=actor_id,
                    template_id=template_id,
                    before=removed.to_dict(),
                )
            return True

    # --- internal helpers -------------------------------------------------

    def _read_raw(self) -> list[dict] | None:
        if not self._path.exists():
            return None
        content = self._path.read_text(encoding="utf-8").strip()
        if not content:
            return []
        return json.loads(content)

    def _read_all(self) -> list[SprintTemplate]:
        raw = self._read_raw()
        if raw is None:
            return [
                SprintTemplate.from_dict(template.to_dict())
                for template in DEFAULT_TEMPLATES
            ]
        return [SprintTemplate.from_dict(item) for item in raw]

    def _write_all(self, templates: Iterable[SprintTemplate]) -> None:
        payload = [template.to_dict() for template in templates]
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _generate_id(self, title: str, existing: Sequence[SprintTemplate]) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "template"
        candidate = base
        suffix = 1
        existing_ids = {template.template_id for template in existing}
        while candidate in existing_ids:
            suffix += 1
            candidate = f"{base}-{suffix}"
        return candidate

    def _normalize_segments(
        self, segments: Iterable[float] | None, dist: int
    ) -> tuple[float, ...]:
        if segments is None:
            return ()
        values: list[float] = []
        for raw in segments:
            number = float(raw)
            if number > 0:
                values.append(number)
        if not values:
            return ()
        total = sum(values)
        if abs(total - dist) > 1e-6:
            raise ValueError("Sum of segments must match distance")
        return tuple(values)
