"""Day 5 Phase 1 — omnichannel database models."""

from sqlalchemy import create_engine, inspect

from app.config import get_settings
from app.infrastructure.database.models import DeliveryStatus


def test_day5_migration_tables_exist() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url_sync)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    for table in ("external_messages", "attachments", "channel_configurations"):
        assert table in tables


def test_delivery_status_enum() -> None:
    assert DeliveryStatus.SENT.value == "SENT"
    assert DeliveryStatus.FAILED.value == "FAILED"
