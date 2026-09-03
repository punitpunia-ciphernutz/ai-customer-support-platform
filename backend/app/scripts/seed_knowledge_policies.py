"""Seed knowledge base with customer policies (refund, cancellation, plans).

Idempotent: wipes all existing knowledge_sources for the default org, then
creates one TEXT source with three detailed policy documents.

Usage:
    cd backend && python -m app.scripts.seed_knowledge_policies
"""

from __future__ import annotations

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.infrastructure.database.models import Organization
from app.modules.knowledge.domain.models import (
    Document,
    IngestionStatus,
    KnowledgeSource,
    KnowledgeSourceType,
)

REFUND_POLICY = """\
# Refund Policy

## Eligibility
- Full refund within 14 days of purchase for any plan (monthly or annual).
- Partial refund (50%) available within 30 days of purchase for annual plans only.
- After 30 days, no refunds are issued for any plan.

## Non-Refundable Items
- Add-on modules and marketplace extensions.
- Usage-based overages (API calls, storage, seats beyond plan limit).
- Third-party integration fees (Slack, Salesforce, Jira connectors).

## How to Request a Refund
1. Go to Settings → Billing → Request Refund, or email support@example.com with your account ID.
2. Refund requests are reviewed within 1 business day.
3. Approved refunds are processed to the original payment method within 5–7 business days.

## Exceptions
- Duplicate charges: refunded immediately upon verification — no waiting period.
- Service outage lasting more than 24 consecutive hours: pro-rated credit applied automatically to your next invoice.
- Fraudulent charges: report within 60 days for full reversal.

## Frequently Asked Questions
Q: Can I get a refund on my annual Pro plan after 20 days?
A: Yes — you are within the 30-day window for annual plans, so you qualify for a 50% partial refund.

Q: I purchased an add-on 3 days ago. Can I get a refund?
A: No — add-on modules are non-refundable regardless of timing.

Q: How long until I see the refund in my bank account?
A: Approved refunds take 5–7 business days to appear on your statement.
"""

CANCELLATION_POLICY = """\
# Cancellation Policy

## Self-Service Cancellation
- Cancel your subscription at any time from Settings → Billing → Cancel Subscription.
- Cancellation takes effect at the end of your current billing period. You retain full access until then.

## Monthly Plans
- Immediate cancellation is available if requested through support.
- No partial-month refund is issued unless you also qualify under the Refund Policy (within 14 days of purchase).

## Annual Plans
- Cancelling an annual plan stops auto-renewal. Your access continues until the end of the paid year.
- No mid-year refund is provided after the 30-day refund window.

## Reactivation
- You may reactivate a cancelled account within 90 days at the same plan and pricing (if the plan is still offered).
- After 90 days, you must sign up as a new customer at current pricing.

## Data Retention After Cancellation
- Your account data (conversations, tickets, knowledge base, customer records) is preserved for 30 days after the billing period ends.
- After 30 days, all data is permanently deleted and cannot be recovered.
- You may request an immediate data export before cancellation from Settings → Data Export.

## Frequently Asked Questions
Q: If I cancel today, when does my access end?
A: Your access continues until the end of your current billing period (the date shown on Settings → Billing).

Q: Can I cancel and get a refund at the same time?
A: Yes — if you are within the refund eligibility window, submit both a cancellation and a refund request.

Q: What happens to my team members when I cancel?
A: All team member access ends when the subscription expires. They will be notified by email 7 days before expiration.
"""

SUBSCRIPTION_PLANS_POLICY = """\
# Subscription Plans & Changes

## Available Plans
| Plan | Monthly Price | Annual Price | Key Features |
|------|--------------|-------------|--------------|
| Basic | $19/month | $182/year (20% off) | 2 agents, 500 conversations/mo, email channel, basic AI |
| Pro | $49/month | $470/year (20% off) | 10 agents, unlimited conversations, all channels, advanced AI, automations |
| Enterprise | Custom | Custom | Unlimited agents, SSO, dedicated support, SLA guarantees, custom integrations |

## Upgrading Your Plan
- Upgrades take effect immediately.
- You are charged a prorated amount for the remainder of your current billing cycle.
- Example: upgrading from Basic ($19/mo) to Pro ($49/mo) on day 15 of a 30-day cycle charges $15 for the remaining 15 days at the Pro rate.

## Downgrading Your Plan
- Downgrades take effect at the start of your next billing cycle.
- No mid-cycle refund is issued for unused features on the current plan.
- If your current usage exceeds the lower plan's limits (e.g., more than 2 agents on Basic), you must reduce usage before the downgrade activates.

## Billing Cycles
- Monthly plans renew on the same calendar date each month.
- Annual plans renew on the anniversary of your signup date.
- Annual billing provides a 20% discount compared to monthly billing.

## How to Change Your Plan
1. Go to Settings → Billing → Change Plan.
2. Select your new plan and confirm.
3. For upgrades, the prorated charge appears on your next invoice.
4. For downgrades, the change is scheduled for the next billing cycle.

## Frequently Asked Questions
Q: Can I downgrade from Pro to Basic mid-month?
A: You can request the downgrade at any time, but it takes effect at the start of your next billing cycle. You keep Pro features until then.

Q: Do I get a refund for unused Pro time when downgrading?
A: No — downgrades do not generate a mid-cycle refund.

Q: Can I switch from monthly to annual billing?
A: Yes — go to Settings → Billing → Change Plan and select the annual option. The 20% discount applies immediately, and you are charged the annual rate prorated from today.

Q: How do I get Enterprise pricing?
A: Contact sales@example.com or use the in-app chat to request a custom quote.
"""

POLICIES = [
    ("Refund Policy", REFUND_POLICY),
    ("Cancellation Policy", CANCELLATION_POLICY),
    ("Subscription Plans & Changes", SUBSCRIPTION_PLANS_POLICY),
]


def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url.replace("+asyncpg", "+psycopg2"))

    with Session(engine) as session:
        org_id = session.execute(select(Organization.id).limit(1)).scalar_one()

        # Wipe all existing knowledge sources (cascade deletes docs + chunks)
        session.execute(
            delete(KnowledgeSource).where(KnowledgeSource.organization_id == org_id)
        )
        session.flush()

        # Create source
        source = KnowledgeSource(
            organization_id=org_id,
            name="Customer Policies",
            type=KnowledgeSourceType.TEXT,
            status=IngestionStatus.PENDING,
            configuration={},
        )
        session.add(source)
        session.flush()

        # Create documents
        doc_ids = []
        for title, content in POLICIES:
            doc = Document(
                knowledge_source_id=source.id,
                title=title,
                content=content,
                metadata_={"source_type": "TEXT"},
                status=IngestionStatus.PENDING,
            )
            session.add(doc)
            session.flush()
            doc_ids.append(doc.id)

        session.commit()
        print(f"✓ Created source '{source.name}' with {len(doc_ids)} documents")
        print(f"  Source ID: {source.id}")
        for did in doc_ids:
            print(f"  Document ID: {did}")
        print()
        print("Run Celery worker to ingest: celery -A app.workers.celery_app worker -l info")
        print("Or trigger manually per doc:")
        for did in doc_ids:
            print(f"  python -c \"from app.workers.tasks import ingest_document; ingest_document.delay('{did}')\"")


if __name__ == "__main__":
    main()
