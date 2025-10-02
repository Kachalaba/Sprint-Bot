import asyncio
import sqlite3
from datetime import datetime
from pathlib import Path

from services.audit_service import AuditService
from services.io_service import ImportPreview, ImportRecord, IOService
from template_service import TemplateService


def test_undo_result_creation_restores_state(tmp_path: Path) -> None:
    async def scenario() -> None:
        db_path = tmp_path / "results.db"
        templates_path = tmp_path / "templates.json"
        audit_service = AuditService(results_db_path=db_path, template_path=templates_path)
        await audit_service.init()

        io_service = IOService(db_path=db_path, audit_service=audit_service)
        await io_service.init()

        record = ImportRecord(
            row_number=1,
            athlete_id=101,
            athlete_name="Tester",
            stroke="freestyle",
            distance=50,
            total_seconds=25.5,
            timestamp=datetime(2024, 5, 1, 8, 0),
            is_pr=True,
        )
        preview = ImportPreview(rows=(record,), issues=(), total_rows=1)
        await io_service.apply_import(preview, user_id=42)

        entries = await audit_service.list_entries(limit=5)
        assert entries, "Audit log must contain create entry"
        entry = entries[0]
        assert entry.action == "create"
        assert entry.entity_type == "result"

        with sqlite3.connect(db_path) as conn:
            count_before = conn.execute("SELECT COUNT(*) FROM results").fetchone()[0]
        assert count_before == 1

        assert await audit_service.undo(entry.id)

        with sqlite3.connect(db_path) as conn:
            count_after = conn.execute("SELECT COUNT(*) FROM results").fetchone()[0]
        assert count_after == 0

    asyncio.run(scenario())


def test_undo_template_update_and_delete(tmp_path: Path) -> None:
    async def scenario() -> None:
        db_path = tmp_path / "results.db"
        templates_path = tmp_path / "templates.json"
        audit_service = AuditService(results_db_path=db_path, template_path=templates_path)
        await audit_service.init()

        template_service = TemplateService(storage_path=templates_path, audit_service=audit_service)
        await template_service.init()

        template = await template_service.create_template(
            title="Test", dist=100, stroke="freestyle", segments=(25, 25, 25, 25), actor_id=7
        )

        updated = await template_service.update_template(
            template.template_id,
            hint="Новий опис",
            actor_id=7,
        )
        assert updated.hint == "Новий опис"

        entries = await audit_service.list_entries(limit=5)
        update_entry = next(entry for entry in entries if entry.action == "update")
        assert await audit_service.undo(update_entry.id)

        restored = await template_service.get_template(template.template_id)
        assert restored is not None
        assert restored.hint == ""

        assert await template_service.delete_template(template.template_id, actor_id=7)
        entries = await audit_service.list_entries(limit=5)
        delete_entry = next(entry for entry in entries if entry.action == "delete")
        assert await audit_service.undo(delete_entry.id)

        recovered = await template_service.get_template(template.template_id)
        assert recovered is not None
        assert recovered.title == template.title

    asyncio.run(scenario())
