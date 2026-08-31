"""Enqueue async AI processing for customer messages."""

from __future__ import annotations

import logging

from app.infrastructure.database.models import SenderType

logger = logging.getLogger(__name__)


def enqueue_ai_message_processing(message_id: str, sender_type: str) -> None:
    if sender_type != SenderType.CUSTOMER.value:
        return
    try:
        from app.workers.tasks import process_ai_message

        process_ai_message.delay(message_id)
    except Exception:
        logger.exception("Failed to enqueue AI processing for message %s", message_id)
