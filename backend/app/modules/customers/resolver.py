from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import Customer


class CustomerResolver:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def resolve_by_email(
        self,
        organization_id: str,
        email: str,
        *,
        name: str | None = None,
    ) -> Customer:
        normalized = email.strip().lower()
        result = await self.db.execute(
            select(Customer).where(
                Customer.organization_id == organization_id,
                Customer.email == normalized,
            )
        )
        customer = result.scalar_one_or_none()
        if customer is not None:
            return customer

        display_name = name or normalized.split("@")[0].replace(".", " ").title()
        customer = Customer(
            organization_id=organization_id,
            name=display_name,
            email=normalized,
        )
        self.db.add(customer)
        await self.db.flush()
        await self.db.refresh(customer)
        return customer

    async def resolve_by_id(self, organization_id: str, customer_id: str) -> Customer | None:
        result = await self.db.execute(
            select(Customer).where(
                Customer.id == customer_id,
                Customer.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def resolve_anonymous_visitor(
        self,
        organization_id: str,
        *,
        external_id: str,
        name: str = "Visitor",
        metadata: dict | None = None,
    ) -> Customer:
        result = await self.db.execute(
            select(Customer).where(
                Customer.organization_id == organization_id,
                Customer.external_id == external_id,
            )
        )
        customer = result.scalar_one_or_none()
        if customer is not None:
            if metadata:
                merged = dict(customer.metadata_ or {})
                merged.update(metadata)
                customer.metadata_ = merged
                await self.db.flush()
            return customer

        customer = Customer(
            organization_id=organization_id,
            name=name.strip() or "Visitor",
            external_id=external_id,
            metadata_=metadata or {},
        )
        self.db.add(customer)
        await self.db.flush()
        await self.db.refresh(customer)
        return customer
