import logging

from celery import Celery
from celery.schedules import crontab
from celery.signals import after_setup_logger, after_setup_task_logger

from app.core.config import get_settings
from app.core.logging_config import JSONFormatter

settings = get_settings()


@after_setup_logger.connect
@after_setup_task_logger.connect
def _use_json_formatter(logger: logging.Logger, **_kwargs) -> None:
    # Celery configures its own logging on worker startup and hijacks the root
    # logger by default (worker_hijack_root_logger=True) - calling
    # setup_logging() at import time here, the way main.py does for the API
    # process, would just get overwritten when the worker actually starts.
    # These two signals are Celery's documented hook for this instead.
    for handler in logger.handlers:
        handler.setFormatter(JSONFormatter())

celery_app = Celery("collabflow", broker=settings.redis_url, backend=settings.redis_url)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

celery_app.autodiscover_tasks(["app.workers"])

# Celery Beat: reminder job for tasks due within the next day. Runs once daily
# rather than continuously polling — due-date reminders don't need minute-level
# precision, and this keeps worker load and duplicate-notification risk low.
celery_app.conf.beat_schedule = {
    "send-due-soon-reminders": {
        "task": "app.workers.tasks.send_due_soon_reminders",
        "schedule": crontab(hour=8, minute=0),
    },
}
