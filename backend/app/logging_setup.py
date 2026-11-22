"""Logging: readable lines on laptops, one JSON object per line in production (structured logs).

On the cloud server every line (our own logs and uvicorn's request logs) becomes e.g.
{"time": "2026-11-22T10:15:02Z", "level": "INFO", "logger": "app.main", "msg": "Warm-up done in 21 s"}
so the logs can be filtered by level or logger. Never log CV text, emails or keys.
"""
import json
import logging
import time

UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            out["error"] = self.formatException(record.exc_info)
        return json.dumps(out, ensure_ascii=False)


def setup(production: bool) -> None:
    """Configure the root logger once at import time."""
    handler = logging.StreamHandler()
    if production:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)


def route_uvicorn_logs() -> None:
    """Uvicorn sets up its own handlers when it starts; send its lines through ours instead
    (called at app startup, production only)."""
    for name in UVICORN_LOGGERS:
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
