import re
from pathlib import Path

CYRILLIC_PATTERN = re.compile(r"[А-Яа-яЁёІіЇїЄє]")

# TODO: shrink this allowlist as translations are migrated to i18n/.
ALLOWED_CYRILLIC_PATHS = {
    Path("backup_service.py"),
    Path("handlers/add_wizard.py"),
    Path("handlers/admin.py"),
    Path("handlers/backup.py"),
    Path("handlers/common.py"),
    Path("handlers/error_handler.py"),
    Path("handlers/export_import.py"),
    Path("handlers/messages.py"),
    Path("handlers/notifications.py"),
    Path("handlers/onboarding.py"),
    Path("handlers/progress.py"),
    Path("handlers/registration.py"),
    Path("handlers/search.py"),
    Path("handlers/sprint_actions.py"),
    Path("handlers/templates.py"),
    Path("notifications.py"),
    Path("reports/image_report.py"),
    Path("services/base.py"),
    Path("template_service.py"),
    Path("tests/test_add_wizard.py"),
    Path("tests/test_audit_undo.py"),
    Path("tests/test_bot_i18n.py"),
    Path("tests/test_i18n_basic.py"),
    Path("tests/test_i18n_middleware.py"),
    Path("tests/test_i18n_sanity.py"),
    Path("tests/test_leaderboard.py"),
    Path("tests/test_onboarding.py"),
    Path("tests/test_onboarding_i18n.py"),
    Path("tests/test_roles_i18n.py"),
    Path("tests/test_stats_service_i18n.py"),
    Path("tests/test_user_service_i18n.py"),
    Path("utils/__init__.py"),
}


def test_python_files_do_not_contain_cyrillic():
    repo_root = Path(__file__).resolve().parents[1]
    offending_entries = []

    for path in repo_root.rglob("*.py"):
        if "i18n" in path.parts:
            continue

        relative_path = path.relative_to(repo_root)
        if relative_path in ALLOWED_CYRILLIC_PATHS:
            continue

        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = path.read_text(encoding="utf-8", errors="ignore")

        for line_number, line in enumerate(content.splitlines(), start=1):
            if CYRILLIC_PATTERN.search(line):
                offending_entries.append((relative_path, line_number, line.strip()))

    assert not offending_entries, _format_error(offending_entries)


def _format_error(entries: list[tuple[Path, int, str]]) -> str:
    formatted = "; ".join(
        f"{path}:{line_number} contains Cyrillic characters: '{snippet}'"
        for path, line_number, snippet in entries
    )
    return (
        "Cyrillic characters detected outside the i18n directory in the following files: "
        f"{formatted}"
    )
