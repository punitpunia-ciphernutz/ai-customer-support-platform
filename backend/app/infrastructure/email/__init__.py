from functools import lru_cache

from app.config import get_settings
from app.infrastructure.email.base import EmailProvider
from app.infrastructure.email.providers import MockEmailProvider, ResendEmailProvider

_mock_provider = MockEmailProvider()


@lru_cache
def get_email_provider(provider_name: str | None = None) -> EmailProvider:
    settings = get_settings()
    name = (provider_name or settings.email_provider or "mock").lower()
    if name == "resend" and settings.resend_api_key:
        return ResendEmailProvider(settings.resend_api_key, settings.email_from_address)
    return _mock_provider


def get_mock_email_provider() -> MockEmailProvider:
    return _mock_provider
