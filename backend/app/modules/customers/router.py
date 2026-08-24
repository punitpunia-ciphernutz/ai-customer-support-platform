from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.infrastructure.audit import write_audit
from app.infrastructure.database.models import ActorType, Customer, User
from app.infrastructure.database.session import get_db
from app.infrastructure.events import DomainEvent, event_bus
from app.modules.auth.permissions import CUSTOMERS_READ, CUSTOMERS_WRITE
from app.modules.customers.schemas import CustomerCreate, CustomerOut, CustomerUpdate

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=list[CustomerOut])
async def list_customers(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CUSTOMERS_READ)),
) -> list[Customer]:
    result = await db.execute(
        select(Customer)
        .where(Customer.organization_id == user.organization_id)
        .order_by(Customer.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{customer_id}", response_model=CustomerOut)
async def get_customer(
    customer_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CUSTOMERS_READ)),
) -> Customer:
    customer = await _get_org_customer(db, user.organization_id, customer_id)
    return customer


@router.post("", response_model=CustomerOut, status_code=201)
async def create_customer(
    body: CustomerCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CUSTOMERS_WRITE)),
) -> Customer:
    customer = Customer(
        organization_id=user.organization_id,
        name=body.name,
        email=str(body.email).lower() if body.email else None,
        phone=body.phone,
        company_name=body.company_name,
        external_id=body.external_id,
        metadata_=body.metadata,
    )
    db.add(customer)
    await db.flush()
    await db.refresh(customer)
    await event_bus.publish(
        DomainEvent(
            name="customer.created",
            organization_id=user.organization_id,
            payload={"customer_id": customer.id},
        )
    )
    return customer


@router.patch("/{customer_id}", response_model=CustomerOut)
async def update_customer(
    customer_id: str,
    body: CustomerUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(CUSTOMERS_WRITE)),
) -> Customer:
    customer = await _get_org_customer(db, user.organization_id, customer_id)
    old = {
        "name": customer.name,
        "email": customer.email,
        "phone": customer.phone,
        "company_name": customer.company_name,
    }
    data = body.model_dump(exclude_unset=True)
    if "metadata" in data:
        customer.metadata_ = data.pop("metadata") or {}
    if "email" in data and data["email"] is not None:
        data["email"] = str(data["email"]).lower()
    for key, value in data.items():
        setattr(customer, key, value)
    await db.flush()
    await db.refresh(customer)
    await write_audit(
        db,
        organization_id=user.organization_id,
        actor_type=ActorType.USER,
        actor_id=user.id,
        action="customer.updated",
        entity_type="customer",
        entity_id=customer.id,
        old_value=old,
        new_value={
            "name": customer.name,
            "email": customer.email,
            "phone": customer.phone,
            "company_name": customer.company_name,
        },
    )
    await event_bus.publish(
        DomainEvent(
            name="customer.updated",
            organization_id=user.organization_id,
            payload={"customer_id": customer.id},
        )
    )
    return customer


async def _get_org_customer(db: AsyncSession, org_id: str, customer_id: str) -> Customer:
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id, Customer.organization_id == org_id)
    )
    customer = result.scalar_one_or_none()
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return customer
