from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "support_platform",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)
celery_app.conf.task_default_queue = "celery"
celery_app.conf.beat_schedule = {
    "process-missed-chats-every-minute": {
        "task": "app.workers.tasks.process_missed_chats",
        "schedule": 60.0,
    },
    "process-ai-response-timeouts": {
        "task": "app.workers.tasks.process_ai_response_timeouts",
        "schedule": 30.0,
    },
}


@celery_app.task(name="app.workers.tasks.hello_world")
def hello_world(name: str = "support-platform") -> str:
    return f"hello from celery, {name}"
