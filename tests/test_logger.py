import json

from utils.logger import get_logger


def test_logger_emits_json(capfd) -> None:
    logger = get_logger("tests.logger.json")
    logger.info("hello %s", "world")

    captured = capfd.readouterr()
    line = captured.err.strip() or captured.out.strip()
    assert line, "logger should emit a line"

    payload = json.loads(line)
    assert payload["msg"] == "hello world"
    assert payload["level"] == "INFO"
    for key in ("ts", "level", "msg"):
        assert key in payload
