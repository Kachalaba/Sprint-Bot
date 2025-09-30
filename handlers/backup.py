"""Administrative commands for managing database backups."""

from __future__ import annotations

from aiogram import Router, types
from aiogram.filters import Command

from backup_service import BackupService
from role_service import ROLE_ADMIN, RoleService

router = Router()


@router.message(Command("backup_now"))
async def backup_now_handler(
    message: types.Message,
    backup_service: BackupService,
    role_service: RoleService,
) -> None:
    """Trigger an immediate backup if the sender is an administrator."""

    if message.from_user is None:
        await message.answer("Команда доступна лише адміністраторам.")
        return
    if await role_service.get_role(message.from_user.id) != ROLE_ADMIN:
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
    message: types.Message,
    backup_service: BackupService,
    role_service: RoleService,
) -> None:
    """Display recent backups."""

    if message.from_user is None:
        await message.answer("Команда доступна лише адміністраторам.")
        return
    if await role_service.get_role(message.from_user.id) != ROLE_ADMIN:
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
    message: types.Message,
    backup_service: BackupService,
    role_service: RoleService,
) -> None:
    """Restore the latest backup or one specified by key."""

    if message.from_user is None:
        await message.answer("Команда доступна лише адміністраторам.")
        return
    if await role_service.get_role(message.from_user.id) != ROLE_ADMIN:
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
