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


@celery_app.task(name="app.workers.tasks.hello_world")
def hello_world(name: str = "support-platform") -> str:
    return f"hello from celery, {name}"
