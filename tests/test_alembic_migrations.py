"""Smoke tests for the Alembic migration chain.

We run ``upgrade head`` and ``downgrade base`` against an in-memory
SQLite engine to catch obvious schema regressions (orphaned indexes,
forgotten down_revision, dialect-specific syntax). The legacy migrations
live in ``alembic/versions/`` and rely on neutral SQLAlchemy types so
they should round-trip on SQLite even though production uses Postgres.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("alembic")

from alembic import command
from alembic.config import Config


REPO_ROOT = Path(__file__).resolve().parents[1]


def _make_config(db_url: str) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_alembic_chain_upgrades_and_downgrades(tmp_path) -> None:
    pytest.importorskip("aiosqlite")
    db_path = tmp_path / "alembic_smoke.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"

    cfg = _make_config(db_url)
    command.upgrade(cfg, "head")
    assert db_path.exists()

    command.downgrade(cfg, "base")


def test_migrations_reach_expected_head() -> None:
    """The newest legacy migration should be the current head."""

    from alembic.script import ScriptDirectory

    cfg = _make_config("sqlite:///")
    script = ScriptDirectory.from_config(cfg)
    head_revision = script.get_current_head()
    assert head_revision == "20240601_0003"
