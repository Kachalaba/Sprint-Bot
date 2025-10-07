from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Any, Dict, Iterator, List, Tuple

import pytest
from unittest.mock import MagicMock

import backup_service
from backup_service import BackupService


REAL_DATETIME = datetime


class FakeClientError(Exception):
    """Lightweight stand-in for botocore.exceptions.ClientError."""

    def __init__(self, operation_name: str, message: str = "fake failure") -> None:
        self.response = {"Error": {"Code": "FakeError", "Message": message}}
        self.operation_name = operation_name
        super().__init__(f"{operation_name} failed: {message}")


class FakePaginator:
    """Simple paginator for list_objects_v2 responses."""

    def __init__(self, client: "FakeS3Client") -> None:
        self._client = client

    def paginate(self, *, Bucket: str, Prefix: str) -> Iterator[dict[str, Any]]:
        contents: list[dict[str, Any]] = []
        for (bucket, key), meta in sorted(
            self._client.objects.items(),
            key=lambda item: item[1]["LastModified"],
        ):
            if bucket == Bucket and key.startswith(Prefix):
                contents.append(
                    {
                        "Key": key,
                        "Size": meta["Size"],
                        "LastModified": meta["LastModified"],
                    }
                )
        yield {"Contents": contents}


class FakeS3Client:
    """Record uploaded objects and emulate a subset of the S3 client API."""

    def __init__(self) -> None:
        self.objects: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self.uploaded: List[Tuple[str, str]] = []
        self._counter = 0

    def upload_file(
        self,
        Filename: str,
        Bucket: str,
        Key: str,
        ExtraArgs: dict[str, Any] | None = None,
    ) -> None:
        self._raise_if_negative(Filename, "upload_file")
        self._raise_if_negative(Key, "upload_file")
        data = Path(Filename).read_bytes()
        timestamp = datetime.utcnow() + timedelta(microseconds=self._counter)
        self._counter += 1
        self.objects[(Bucket, Key)] = {
            "Body": data,
            "Size": len(data),
            "LastModified": timestamp,
            "ExtraArgs": ExtraArgs or {},
        }
        self.uploaded.append((Bucket, Key))

    def download_file(self, Bucket: str, Key: str, Filename: str) -> None:
        self._raise_if_negative(Key, "download_file")
        self._raise_if_negative(Filename, "download_file")
        meta = self.objects.get((Bucket, Key))
        if meta is None:
            raise FakeClientError("download_file", f"{Key} not found")
        destination = Path(Filename)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(meta["Body"])

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        self._raise_if_negative(Key, "head_object")
        meta = self.objects.get((Bucket, Key))
        if meta is None:
            raise FakeClientError("head_object", f"{Key} not found")
        return {
            "ContentLength": meta["Size"],
            "LastModified": meta["LastModified"],
        }

    def get_paginator(self, name: str) -> FakePaginator:
        if name != "list_objects_v2":
            raise ValueError(f"Unsupported paginator {name}")
        return FakePaginator(self)

    @staticmethod
    def _is_negative_path(value: str) -> bool:
        return Path(value).name.startswith("-")

    def _raise_if_negative(self, value: str, operation: str) -> None:
        if self._is_negative_path(value):
            raise FakeClientError(operation, f"negative path disallowed: {value}")


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> FakeS3Client:
    fake = FakeS3Client()
    fake_boto3 = SimpleNamespace(
        session=SimpleNamespace(Session=MagicMock(name="FakeSession"))
    )
    monkeypatch.setattr(backup_service, "boto3", fake_boto3)
    monkeypatch.setattr(backup_service, "ClientError", FakeClientError)
    monkeypatch.setattr(backup_service, "BotoCoreError", FakeClientError)
    return fake


def _patch_notifications(
    monkeypatch: pytest.MonkeyPatch, service: BackupService
) -> list[str]:
    captured: list[str] = []

    async def capture(self: BackupService, text: str) -> None:
        captured.append(text)

    async def fake_send(*args: Any, **kwargs: Any) -> None:
        if "text" in kwargs:
            captured.append(kwargs["text"])
        elif len(args) >= 3:
            captured.append(args[2])

    monkeypatch.setattr(service, "_notify_admins", MethodType(capture, service))
    monkeypatch.setattr(backup_service, "send_notification", fake_send)
    return captured


def _run(coro: Any) -> Any:
    return asyncio.run(coro)




def _install_sequential_datetime(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = {"value": 0}
    start = REAL_DATETIME(2025, 1, 1, 0, 0, 0)

    class _SequentialDatetime(REAL_DATETIME):
        @classmethod
        def utcnow(cls) -> REAL_DATETIME:
            value = start + timedelta(seconds=counter["value"])
            counter["value"] += 1
            return value

    monkeypatch.setattr(backup_service, "datetime", _SequentialDatetime)
    monkeypatch.setattr(sys.modules[__name__], "datetime", _SequentialDatetime)


def test_backup_now_success_creates_object_and_notifies(
    tmp_path: Path, fake_client: FakeS3Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        _install_sequential_datetime(monkeypatch)
        db_path = tmp_path / "bot.sqlite3"
        db_path.write_text("initial data")
        service = BackupService(
            bot=MagicMock(),
            db_path=db_path,
            bucket_name="bucket",
            admin_chat_ids=(101,),
            client_factory=lambda: fake_client,
        )
        notifications = _patch_notifications(monkeypatch, service)

        metadata = await service.backup_now(notify=True)

        assert (service.bucket_name, metadata.key) in fake_client.objects
        stored = fake_client.objects[(service.bucket_name, metadata.key)]
        assert stored["Size"] == len("initial data")
        assert metadata.size == stored["Size"]
        assert metadata.key.startswith(service.backup_prefix)
        assert notifications and "✅" in notifications[0]
        assert metadata.key in notifications[0]

    _run(scenario())


def test_list_backups_respects_order_and_limit(
    tmp_path: Path, fake_client: FakeS3Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        _install_sequential_datetime(monkeypatch)
        db_path = tmp_path / "bot.sqlite3"
        service = BackupService(
            bot=MagicMock(),
            db_path=db_path,
            bucket_name="bucket",
            client_factory=lambda: fake_client,
        )
        _patch_notifications(monkeypatch, service)

        db_path.write_text("v1")
        await service.backup_now(notify=False)
        db_path.write_text("v2")
        second = await service.backup_now(notify=False)
        db_path.write_text("v3")
        third = await service.backup_now(notify=False)

        latest_two = await service.list_backups(limit=2)

        assert [meta.key for meta in latest_two] == [third.key, second.key]
        assert latest_two[0].last_modified >= latest_two[1].last_modified

    _run(scenario())


def test_restore_backup_latest_and_explicit(
    tmp_path: Path, fake_client: FakeS3Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        _install_sequential_datetime(monkeypatch)
        db_path = tmp_path / "bot.sqlite3"
        service = BackupService(
            bot=MagicMock(),
            db_path=db_path,
            bucket_name="bucket",
            admin_chat_ids=(202,),
            client_factory=lambda: fake_client,
        )
        notifications = _patch_notifications(monkeypatch, service)

        db_path.write_text("version one")
        first = await service.backup_now(notify=False)
        db_path.write_text("version two")
        second = await service.backup_now(notify=False)

        db_path.write_text("corrupted")
        notifications.clear()
        restored_latest = await service.restore_backup(notify=True)
        assert restored_latest.key == second.key
        assert db_path.read_text() == "version two"
        assert notifications and "♻️" in notifications[-1]
        bak_files = list(db_path.parent.glob("*.bak"))
        assert bak_files
        assert any(path.read_text() == "corrupted" for path in bak_files)

        db_path.write_text("changed again")
        notifications.clear()
        restored_first = await service.restore_backup(key=first.key, notify=False)
        assert restored_first.key == first.key
        assert db_path.read_text() == "version one"
        assert len(fake_client.objects) == 2
        bak_second = [
            path
            for path in db_path.parent.glob("*.bak")
            if path.read_text() == "changed again"
        ]
        assert bak_second

    _run(scenario())


def test_error_scenarios_raise_and_notify(
    tmp_path: Path, fake_client: FakeS3Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        _install_sequential_datetime(monkeypatch)
        db_path = tmp_path / "-broken.sqlite3"
        db_path.write_text("broken data")
        service = BackupService(
            bot=MagicMock(),
            db_path=db_path,
            bucket_name="bucket",
            admin_chat_ids=(303,),
            client_factory=lambda: fake_client,
        )
        notifications = _patch_notifications(monkeypatch, service)

        with pytest.raises(RuntimeError):
            await service.backup_now(notify=True)

        notifications.clear()
        with pytest.raises(LookupError):
            await service.restore_backup(key="-missing-key", notify=True)
        assert notifications == []

        async def cancel_immediately(seconds: float) -> None:
            raise asyncio.CancelledError

        monkeypatch.setattr(backup_service.asyncio, "sleep", cancel_immediately)

        notifications.clear()
        with pytest.raises(asyncio.CancelledError):
            await service._backup_loop()

        assert notifications
        assert notifications[-1].startswith("❗️")
        assert "Failed to upload backup to S3" in notifications[-1]

    _run(scenario())


def test_backup_service_prefers_provided_client_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory_client = object()
    factory = MagicMock(return_value=factory_client)

    fake_boto3 = SimpleNamespace(
        session=MagicMock(
            side_effect=AssertionError("Session should not be constructed")
        )
    )
    monkeypatch.setattr(backup_service, "boto3", fake_boto3)

    service = BackupService(
        bot=MagicMock(),
        db_path=tmp_path / "bot.sqlite3",
        bucket_name="bucket",
        client_factory=factory,
    )

    first_client = service._get_client()
    second_client = service._get_client()

    assert first_client is factory_client
    assert second_client is factory_client
    factory.assert_called_once_with()
    fake_boto3.session.assert_not_called()
