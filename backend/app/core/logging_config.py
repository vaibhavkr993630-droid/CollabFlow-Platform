import json
import logging
import sys
from datetime import UTC, datetime

from app.core.config import get_settings

settings = get_settings()


class JSONFormatter(logging.Formatter):
    """
    Minimal stdlib-only JSON formatter — no external logging library. A production
    system would likely want request-id correlation and log shipping, but for this
    project's scope, structured (parseable) output is the actual requirement,
    not a specific vendor's log pipeline.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def setup_logging() -> None:
    """Called once from main.py, before the FastAPI app is constructed."""
    root_logger = logging.getLogger()
    # Root always stays at INFO, even in debug mode: DEBUG here doesn't just
    # affect this app's own log.debug() calls, it applies to every third-party
    # library too. Confirmed the hard way — running with settings.debug=True
    # buried real startup output under hundreds of botocore internal DEBUG lines
    # (event-name rewrites, JSON file loads, etc.) that have nothing to do with
    # this app. App-level debug verbosity is opted into per-logger below instead.
    root_logger.setLevel(logging.INFO)

    # Replace handlers rather than adding to them: uvicorn installs its own
    # handlers on import, and this call runs after that - without clearing
    # first, log lines would be formatted (and printed) twice.
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root_logger.addHandler(handler)

    # uvicorn's access/error loggers propagate to root by default, which is
    # exactly what's wanted here - no need to touch them individually.

    if settings.debug:
        logging.getLogger("app").setLevel(logging.DEBUG)
