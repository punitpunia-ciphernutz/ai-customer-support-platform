from celery import Celery

from app.config import get_settings
from app.modules.automation.application.event_handler import register_automation_handlers

settings = get_settings()

# Celery workers process AI messages and emit domain events — handlers must be
# registered here, not only in the FastAPI lifespan.
register_automation_handlers()

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
    "process-sla-breaches": {
        "task": "app.workers.tasks.process_sla_breaches",
        "schedule": 60.0,
    },
}


@celery_app.task(name="app.workers.tasks.hello_world")
def hello_world(name: str = "support-platform") -> str:
    return f"hello from celery, {name}"
