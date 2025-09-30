"""Administrative commands for managing database backups."""

from __future__ import annotations

from aiogram import Router, types
from aiogram.filters import Command

from backup_service import BackupService
from services import ADMIN_IDS

router = Router()

ADMIN_CHAT_IDS: set[int] = set()
for raw_id in ADMIN_IDS:
    raw_id = raw_id.strip()
    if not raw_id:
        continue
    try:
        ADMIN_CHAT_IDS.add(int(raw_id))
    except ValueError:
        continue


def _is_admin(message: types.Message) -> bool:
    user_id = message.from_user.id if message.from_user else None
    if user_id is None:
        return False
    return user_id in ADMIN_CHAT_IDS


@router.message(Command("backup_now"))
async def backup_now_handler(
    message: types.Message, backup_service: BackupService
) -> None:
    """Trigger an immediate backup if the sender is an administrator."""

    if not _is_admin(message):
        await message.answer("Команда доступна лише адміністраторам.")
        return

    try:
        metadata = await backup_service.backup_now()
    except Exception as exc:  # pragma: no cover - network dependent
        await message.answer(f"❗️ Не вдалося створити резервну копію: {exc}")
        return

    await message.answer(
        "✅ Резервне копіювання виконано.\n"
        f"Файл: <code>{metadata.key}</code>\n"
        f"Розмір: {metadata.size} байт"
    )


@router.message(Command("backup_status"))
async def backup_status_handler(
    message: types.Message, backup_service: BackupService
) -> None:
    """Display recent backups."""

    if not _is_admin(message):
        await message.answer("Команда доступна лише адміністраторам.")
        return

    try:
        backups = await backup_service.list_backups(limit=5)
    except Exception as exc:  # pragma: no cover - network dependent
        await message.answer(f"❗️ Не вдалося отримати список бекапів: {exc}")
        return
    if not backups:
        await message.answer("ℹ️ Наразі немає збережених резервних копій.")
        return

    lines = ["🗂 Останні резервні копії:"]
    for index, backup in enumerate(backups, start=1):
        lines.append(
            f"{index}. <code>{backup.key}</code> — {backup.size} байт — "
            f"{backup.last_modified:%Y-%m-%d %H:%M:%S}"
        )
    await message.answer("\n".join(lines))


@router.message(Command("restore_backup"))
async def restore_backup_handler(
    message: types.Message, backup_service: BackupService
) -> None:
    """Restore the latest backup or one specified by key."""

    if not _is_admin(message):
        await message.answer("Команда доступна лише адміністраторам.")
        return

    key = message.get_args().strip()
    key = key or None

    try:
        metadata = await backup_service.restore_backup(key=key)
    except LookupError as exc:
        await message.answer(f"❗️ {exc}")
        return
    except Exception as exc:  # pragma: no cover - network dependent
        await message.answer(f"❗️ Помилка відновлення: {exc}")
        return

    text = "♻️ Відновлення завершено успішно.\n" f"Файл: <code>{metadata.key}</code>"
    await message.answer(text)
