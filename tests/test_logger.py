import json

from utils.logger import get_logger


def test_logger_emits_valid_json_lines(capfd) -> None:
    logger = get_logger("tests.logger.json")

    logger.info("hello %s", "world")
    logger.error(
        "boom",
        extra={"user_id": 42, "cmd": "/start", "latency_ms": 123},
    )

    captured = capfd.readouterr()
    output = "".join(part for part in (captured.err, captured.out) if part)
    lines = [line for line in output.splitlines() if line.strip()]

    assert len(lines) == 2, f"expected two log lines, got {lines!r}"

    first_payload = json.loads(lines[0])
    second_payload = json.loads(lines[1])

    for payload in (first_payload, second_payload):
        for key in ("ts", "level", "msg"):
            assert key in payload

    assert first_payload["msg"] == "hello world"
    assert first_payload["level"] == "INFO"

    assert second_payload["msg"] == "boom"
    assert second_payload["level"] == "ERROR"
    assert second_payload["user_id"] == 42
    assert second_payload["cmd"] == "/start"
    assert second_payload["latency_ms"] == 123
