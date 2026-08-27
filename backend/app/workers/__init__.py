from app.workers.celery_app import celery_app, hello_world
from app.workers.tasks import ingest_document

__all__ = ["celery_app", "hello_world", "ingest_document"]
