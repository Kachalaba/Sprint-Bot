import json
import logging
from uuid import uuid4

import utils.logger as logger_module
from utils.logger import get_logger


def test_logger_writes_json_to_rotating_file_and_stderr(
    tmp_path, monkeypatch, capfd
) -> None:
    monkeypatch.setattr(logger_module, "LOG_DIR", tmp_path)

    logger_name = f"tests.logger.{uuid4()}"
    logger = get_logger(logger_name)

    duplicate_logger = get_logger(logger_name)
    assert logger is duplicate_logger

    handlers = logger.handlers
    assert len(handlers) == 2
    assert (
        sum(getattr(handler, "_is_sprint_json_stream", False) for handler in handlers)
        == 1
    )
    assert (
        sum(getattr(handler, "_is_sprint_json_file", False) for handler in handlers)
        == 1
    )

    logger.info("hello %s", "world")
    logger.warning("heads up", extra={"user_id": 7})
    logger.error(
        "boom",
        extra={"user_id": 42, "cmd": "/start", "latency_ms": 123},
    )

    for handler in handlers:
        if hasattr(handler, "flush"):
            handler.flush()

    captured = capfd.readouterr()
    assert not captured.out

    err_lines = [line for line in captured.err.splitlines() if line.strip()]
    assert len(err_lines) == 2

    warning_payload = json.loads(err_lines[0])
    error_payload = json.loads(err_lines[1])

    assert warning_payload["msg"] == "heads up"
    assert warning_payload["level"] == "WARNING"
    assert warning_payload["user_id"] == 7

    assert error_payload["msg"] == "boom"
    assert error_payload["level"] == "ERROR"
    assert error_payload["user_id"] == 42
    assert error_payload["cmd"] == "/start"
    assert error_payload["latency_ms"] == 123

    log_file = tmp_path / "bot.log"
    assert log_file.exists()

    file_lines = [
        json.loads(line)
        for line in log_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(file_lines) == 3

    info_payload, warning_file_payload, error_file_payload = file_lines

    for payload in (info_payload, warning_file_payload, error_file_payload):
        for key in ("ts", "level", "msg"):
            assert key in payload

    assert info_payload["msg"] == "hello world"
    assert info_payload["level"] == "INFO"

    assert warning_file_payload == warning_payload
    assert error_file_payload == error_payload

    # Clean up handlers to avoid influencing other tests.
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    logging.getLogger(logger_name).handlers.clear()
