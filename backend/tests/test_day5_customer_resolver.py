"""Day 5 customer resolver tests."""

import pytest
from sqlalchemy import select

from app.infrastructure.database.models import Customer, Organization
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.customers.resolver import CustomerResolver


@pytest.mark.asyncio
async def test_resolve_by_email_creates_customer() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        resolver = CustomerResolver(session)
        customer = await resolver.resolve_by_email(org_id, "newuser@example.com", name="New User")
        assert customer.email == "newuser@example.com"
        assert customer.name == "New User"
        again = await resolver.resolve_by_email(org_id, "newuser@example.com")
        assert again.id == customer.id
        await session.rollback()


@pytest.mark.asyncio
async def test_resolve_by_email_finds_existing() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        existing = Customer(organization_id=org_id, name="Existing", email="existing@example.com")
        session.add(existing)
        await session.flush()
        resolved = await CustomerResolver(session).resolve_by_email(org_id, "existing@example.com")
        assert resolved.id == existing.id
        await session.rollback()
