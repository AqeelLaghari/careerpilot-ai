"""Structured logs: in production every line is one JSON object."""
import json
import logging

from app.logging_setup import JsonFormatter


def _record(msg, *args, exc_info=None):
    return logging.LogRecord("app.test", logging.WARNING, __file__, 1, msg, args, exc_info)


def test_json_line_has_time_level_logger_and_message():
    out = json.loads(JsonFormatter().format(_record("Warm-up done in %d s", 21)))
    assert out["level"] == "WARNING"
    assert out["logger"] == "app.test"
    assert out["msg"] == "Warm-up done in 21 s"
    assert out["time"].endswith("Z")
    assert "error" not in out


def test_exceptions_stay_on_one_json_line():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        line = JsonFormatter().format(_record("failed", exc_info=sys.exc_info()))
    assert "\n" not in line
    assert "ValueError: boom" in json.loads(line)["error"]
