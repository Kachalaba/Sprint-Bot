from __future__ import annotations

from unittest.mock import MagicMock

import backup_service
from backup_service import BackupService


def test_backup_service_prefers_provided_client_factory(tmp_path, monkeypatch):
    factory_client = object()
    factory = MagicMock(return_value=factory_client)

    session_mock = MagicMock(
        side_effect=AssertionError("Session should not be constructed")
    )
    monkeypatch.setattr(backup_service.boto3.session, "Session", session_mock)

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
    session_mock.assert_not_called()
