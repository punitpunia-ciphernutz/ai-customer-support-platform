from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "support_platform",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
celery_app.conf.task_routes = {"app.workers.tasks.*": {"queue": "default"}}
celery_app.autodiscover_tasks(["app.workers"])


@celery_app.task(name="app.workers.tasks.hello_world")
def hello_world(name: str = "support-platform") -> str:
    return f"hello from celery, {name}"
