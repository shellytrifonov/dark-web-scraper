from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "dark_web_scraper",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.services.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,
    worker_prefetch_multiplier=1,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
)

celery_app.conf.beat_schedule = {
    "check-scraper-status": {
        "task": "app.services.tasks.check_scraper_status",
        "schedule": 60.0,
    },
}
