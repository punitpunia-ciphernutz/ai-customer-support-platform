import logging
import sys

from app.config import get_settings


def configure_logging() -> None:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] request_id=%(request_id)s %(message)s",
        stream=sys.stdout,
    )

    old_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):  # type: ignore[no-untyped-def]
        record = old_factory(*args, **kwargs)
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return record

    logging.setLogRecordFactory(record_factory)
