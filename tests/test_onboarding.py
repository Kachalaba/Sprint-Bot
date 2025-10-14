from __future__ import annotations

import asyncio
from pathlib import Path

from handlers.onboarding import _format_profile, _parse_trainer_reference, _validate_name
from handlers.registration import active_invites, consume_invite, resolve_invite
from role_service import ROLE_ATHLETE, ROLE_TRAINER
from services.user_service import UserProfile, UserService


def test_validate_name_accepts_valid_samples() -> None:
    assert _validate_name("Іван Петренко") == "Іван Петренко"
    assert _validate_name("Anna-Maria") == "Anna-Maria"


def test_validate_name_rejects_invalid_values() -> None:
    assert _validate_name("a") is None
    assert _validate_name("Имя!!!") is None


def test_format_profile_renders_labels() -> None:
    profile = UserProfile(
        telegram_id=1,
        role=ROLE_TRAINER,
        full_name="Coach",
        group_name="Sharks",
        language="uk",
    )
    text = _format_profile(profile)
    assert "Тренер" in text
    assert "Українська" in text


def test_parse_trainer_reference_accepts_digits() -> None:
    trainer_id, invite_code = _parse_trainer_reference("123456")
    assert trainer_id == 123456
    assert invite_code is None


def test_resolve_invite_handles_payload() -> None:
    active_invites["abcd"] = 555
    try:
        info = resolve_invite("рег_abcd")
        assert info is not None
        assert info.trainer_id == 555
        parsed_id, parsed_code = _parse_trainer_reference("reg_abcd")
        assert parsed_id == 555
        assert parsed_code == "abcd"
    finally:
        consume_invite("abcd")


def test_user_service_roundtrip(tmp_path: Path) -> None:
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    path = db_dir / "users.db"
    service = UserService(path)

    async def scenario() -> None:
        await service.init()

        await service.upsert_profile(
            42,
            role=ROLE_ATHLETE,
            full_name="Athlete Name",
            language="ru",
        )

        profile = await service.get_profile(42)
        assert profile is not None
        assert profile.role == ROLE_ATHLETE
        assert profile.language == "ru"

        await service.upsert_profile(
            42,
            role=ROLE_TRAINER,
            full_name="Coach",
            language="uk",
            group_name="Wave",
        )

        updated = await service.get_profile(42)
        assert updated is not None
        assert updated.role == ROLE_TRAINER
        assert updated.group_name == "Wave"
        assert updated.language == "uk"

    asyncio.run(scenario())
