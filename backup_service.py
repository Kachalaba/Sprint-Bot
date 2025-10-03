"""Manage regular backups of the Sprint Bot SQLite database to S3."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Sequence

from aiogram import Bot

from notifications import send_notification

try:  # pragma: no cover - optional dependency
    import boto3
    from botocore.client import BaseClient
    from botocore.exceptions import BotoCoreError, ClientError
except ImportError:  # pragma: no cover - optional dependency
    boto3 = None  # type: ignore[assignment]
    BaseClient = Any  # type: ignore[assignment]
    BotoCoreError = ClientError = Exception  # type: ignore[assignment]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BackupMetadata:
    """Describe a single backup object stored in the cloud."""

    key: str
    size: int
    last_modified: datetime


class BackupService:
    """Upload and restore SQLite backups from an S3-compatible storage."""

    def __init__(
        self,
        *,
        bot: Bot,
        db_path: Path | str,
        bucket_name: str,
        backup_prefix: str = "sprint-bot/backups/",
        interval: timedelta = timedelta(hours=6),
        admin_chat_ids: Sequence[int] | None = None,
        storage_class: str | None = None,
        endpoint_url: str | None = None,
    ) -> None:
        self.bot = bot
        self.db_path = Path(db_path)
        self.bucket_name = bucket_name
        self.backup_prefix = self._normalise_prefix(backup_prefix)
        self.interval = interval
        self.admin_chat_ids = tuple(admin_chat_ids or ())
        self.storage_class = storage_class
        self.endpoint_url = endpoint_url or os.getenv("S3_ENDPOINT_URL")
        self._client: BaseClient | None = None
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._available = boto3 is not None

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._available:
            logger.warning(
                "boto3 is not installed; backup functionality is disabled until the dependency is available"
            )

    async def startup(self) -> None:
        """Launch the periodic backup task if configuration is provided."""

        if not self._available:
            return
        if not self.bucket_name:
            logger.warning("Backup service disabled: S3 bucket is not configured")
            return

        if self._task and not self._task.done():
            return

        self._task = asyncio.create_task(
            self._backup_loop(), name="database-backup-loop"
        )
        logger.info(
            "Backup service started (interval: %s, bucket: %s)",
            self.interval,
            self.bucket_name,
        )

    async def shutdown(self) -> None:
        """Cancel background backup task."""

        if not self._task:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            logger.debug("Backup task cancelled")
        finally:
            self._task = None

    async def backup_now(self, *, notify: bool = True) -> BackupMetadata:
        """Create a new backup immediately and optionally notify admins."""

        self._ensure_available()
        if not self.bucket_name:
            raise RuntimeError("S3 bucket is not configured")

        async with self._lock:
            metadata = await asyncio.to_thread(self._upload_backup)

        logger.info(
            "Backup uploaded to s3://%s/%s (%s bytes)",
            self.bucket_name,
            metadata.key,
            metadata.size,
        )

        if notify:
            await self._notify_success(metadata)
        return metadata

    async def restore_backup(
        self, *, key: str | None = None, notify: bool = True
    ) -> BackupMetadata:
        """Restore the latest or specified backup from cloud storage."""

        self._ensure_available()
        if not self.bucket_name:
            raise RuntimeError("S3 bucket is not configured")

        async with self._lock:
            if key is None:
                backups = await asyncio.to_thread(self._list_backups_sync, 1)
                if not backups:
                    raise LookupError("No backups found in storage")
                target = backups[0]
            else:
                target = await asyncio.to_thread(self._head_object, key)

            await asyncio.to_thread(self._download_backup, target.key)

        logger.info("Backup %s restored from S3", target.key)
        if notify:
            await self._notify_admins(
                "♻️ Відновлення бази даних виконано успішно з архіву {key}.".format(
                    key=target.key
                )
            )
        return target

    async def list_backups(self, limit: int = 5) -> list[BackupMetadata]:
        """Return metadata for the latest backups."""

        self._ensure_available()
        if not self.bucket_name:
            return []
        return await asyncio.to_thread(self._list_backups_sync, limit)

    async def _backup_loop(self) -> None:
        while True:
            try:
                await self.backup_now(notify=True)
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("Scheduled backup failed: %s", exc)
                await self._notify_admins(
                    "❗️ Помилка резервного копіювання: {error}".format(error=exc)
                )
            await asyncio.sleep(self.interval.total_seconds())

    def _upload_backup(self) -> BackupMetadata:
        if not self.db_path.exists():
            raise FileNotFoundError(self.db_path)

        client = self._get_client()
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        key = f"{self.backup_prefix}{timestamp}-{self.db_path.name}"
        extra_args: dict[str, str] = {}
        if self.storage_class:
            extra_args["StorageClass"] = self.storage_class
        try:
            client.upload_file(
                str(self.db_path),
                self.bucket_name,
                key,
                ExtraArgs=extra_args or None,
            )
        except (BotoCoreError, ClientError) as exc:
            raise RuntimeError("Failed to upload backup to S3") from exc

        head = client.head_object(Bucket=self.bucket_name, Key=key)
        size = int(head.get("ContentLength", 0))
        last_modified = head.get("LastModified")
        if not isinstance(last_modified, datetime):
            last_modified = datetime.utcnow()
        return BackupMetadata(key=key, size=size, last_modified=last_modified)

    def _download_backup(self, key: str) -> None:
        client = self._get_client()
        tmp_path = self.db_path.with_suffix(self.db_path.suffix + ".download")
        try:
            client.download_file(self.bucket_name, key, str(tmp_path))
        except (BotoCoreError, ClientError) as exc:
            raise RuntimeError("Failed to download backup from S3") from exc

        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        if self.db_path.exists():
            backup_copy = self.db_path.with_suffix(
                self.db_path.suffix + f".{timestamp}.bak"
            )
            shutil.copy2(self.db_path, backup_copy)
            logger.info("Local database copy saved to %s", backup_copy)
        tmp_path.replace(self.db_path)

    def _list_backups_sync(self, limit: int) -> list[BackupMetadata]:
        client = self._get_client()
        paginator = client.get_paginator("list_objects_v2")
        backups: list[BackupMetadata] = []
        try:
            for page in paginator.paginate(
                Bucket=self.bucket_name, Prefix=self.backup_prefix
            ):
                for obj in page.get("Contents", []):
                    last_modified = obj.get("LastModified")
                    if not isinstance(last_modified, datetime):
                        last_modified = datetime.utcnow()
                    backups.append(
                        BackupMetadata(
                            key=obj["Key"],
                            size=int(obj.get("Size", 0)),
                            last_modified=last_modified,
                        )
                    )
        except (BotoCoreError, ClientError) as exc:
            raise RuntimeError("Failed to list backups") from exc
        backups.sort(key=lambda item: item.last_modified, reverse=True)
        return backups[:limit]

    def _head_object(self, key: str) -> BackupMetadata:
        client = self._get_client()
        try:
            response = client.head_object(Bucket=self.bucket_name, Key=key)
        except (BotoCoreError, ClientError) as exc:
            raise LookupError(f"Backup {key} not found") from exc
        last_modified = response.get("LastModified")
        if not isinstance(last_modified, datetime):
            last_modified = datetime.utcnow()
        size = int(response.get("ContentLength", 0))
        return BackupMetadata(key=key, size=size, last_modified=last_modified)

    async def _notify_success(self, metadata: BackupMetadata) -> None:
        message = (
            "✅ Резервну копію створено.\n"
            f"Файл: <code>{metadata.key}</code>\n"
            f"Розмір: {metadata.size} байт"
        )
        await self._notify_admins(message)

    async def _notify_admins(self, text: str) -> None:
        if not self.admin_chat_ids:
            return
        for chat_id in self.admin_chat_ids:
            await send_notification(self.bot, chat_id, text)

    def _get_client(self) -> BaseClient:
        self._ensure_available()
        if self._client is None:
            session = boto3.session.Session()
            self._client = session.client("s3", endpoint_url=self.endpoint_url)
        return self._client

    @staticmethod
    def _normalise_prefix(prefix: str) -> str:
        prefix = prefix.strip()
        if not prefix:
            return ""
        if not prefix.endswith("/"):
            prefix = f"{prefix}/"
        return prefix

    def _ensure_available(self) -> None:
        if not self._available or boto3 is None:
            raise RuntimeError(
                "boto3 dependency is missing. Install boto3 to enable backup support."
            )


__all__ = ["BackupService", "BackupMetadata"]
