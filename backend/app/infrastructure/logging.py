import logging
import sys
from contextvars import ContextVar

from app.config import get_settings

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")
correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="-")


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        record.correlation_id = correlation_id_ctx.get()
        return True


def configure_logging() -> None:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] "
            "request_id=%(request_id)s correlation_id=%(correlation_id)s %(message)s"
        )
    )
    handler.addFilter(RequestContextFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def bind_request_context(request_id: str, correlation_id: str) -> None:
    request_id_ctx.set(request_id)
    correlation_id_ctx.set(correlation_id)
