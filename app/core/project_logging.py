import json
import logging
import logging.config
from contextvars import ContextVar

from app.core.config import settings

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class _JsonFormatter(logging.Formatter):
    """Emit each log record as a single JSON line (CloudWatch / Datadog friendly)."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_var.get("-"),
        }
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class _TextFormatter(logging.Formatter):
    """Human-readable formatter that includes the request ID."""

    def format(self, record: logging.LogRecord) -> str:
        rid = request_id_var.get("-")
        record.request_id = rid
        return super().format(record)


def setup_project_logging() -> None:
    use_json = settings.LOG_FORMAT.lower() == "json"
    level = settings.LOG_LEVEL.upper()

    if use_json:
        formatter: dict = {
            "()": f"{__name__}._JsonFormatter",
        }
    else:
        formatter = {
            "()": f"{__name__}._TextFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s [%(request_id)s]: %(message)s",
        }

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"default": formatter},
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
            }
        },
        "root": {"level": level, "handlers": ["console"]},
    }
    logging.config.dictConfig(config)
