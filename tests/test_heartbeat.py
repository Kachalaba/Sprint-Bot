from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import pytest

from utils import heartbeat


@pytest.fixture
def heartbeat_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "heartbeat"
    monkeypatch.setenv("HEARTBEAT_PATH", str(target))
    monkeypatch.delenv("HEARTBEAT_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv("HEARTBEAT_STALE_SECONDS", raising=False)
    return target


def test_write_heartbeat_creates_file(heartbeat_file: Path) -> None:
    assert not heartbeat_file.exists()

    heartbeat.write_heartbeat()

    assert heartbeat_file.exists()


def test_write_heartbeat_refreshes_mtime(heartbeat_file: Path) -> None:
    heartbeat.write_heartbeat()
    old_mtime = heartbeat_file.stat().st_mtime
    past = old_mtime - 600
    os.utime(heartbeat_file, (past, past))

    heartbeat.write_heartbeat()

    assert heartbeat_file.stat().st_mtime > past


def test_is_fresh_when_recent(heartbeat_file: Path) -> None:
    heartbeat.write_heartbeat()
    assert heartbeat.is_heartbeat_fresh()


def test_is_stale_when_old(heartbeat_file: Path) -> None:
    heartbeat.write_heartbeat()
    stale_time = time.time() - 999
    os.utime(heartbeat_file, (stale_time, stale_time))
    assert not heartbeat.is_heartbeat_fresh(stale_after=10)


def test_is_stale_when_missing(heartbeat_file: Path) -> None:
    assert not heartbeat_file.exists()
    assert not heartbeat.is_heartbeat_fresh()


def test_heartbeat_path_uses_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "custom"
    monkeypatch.setenv("HEARTBEAT_PATH", str(target))
    assert heartbeat.heartbeat_path() == target


def test_interval_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HEARTBEAT_INTERVAL_SECONDS", raising=False)
    assert heartbeat.heartbeat_interval() == heartbeat.DEFAULT_INTERVAL_SECONDS


def test_interval_invalid_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HEARTBEAT_INTERVAL_SECONDS", "not-a-number")
    assert heartbeat.heartbeat_interval() == heartbeat.DEFAULT_INTERVAL_SECONDS


def test_interval_non_positive_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HEARTBEAT_INTERVAL_SECONDS", "0")
    assert heartbeat.heartbeat_interval() == heartbeat.DEFAULT_INTERVAL_SECONDS


def test_stale_after_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HEARTBEAT_STALE_SECONDS", raising=False)
    assert heartbeat.heartbeat_stale_after() == heartbeat.DEFAULT_STALE_AFTER_SECONDS


@pytest.mark.asyncio
async def test_heartbeat_loop_writes_then_cancels(heartbeat_file: Path) -> None:
    task = asyncio.create_task(heartbeat.heartbeat_loop(interval=0.01))
    try:
        await asyncio.sleep(0.05)
        assert heartbeat_file.exists()
        first_mtime = heartbeat_file.stat().st_mtime
        await asyncio.sleep(0.05)
        assert heartbeat_file.stat().st_mtime >= first_mtime
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
