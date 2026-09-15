from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

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
