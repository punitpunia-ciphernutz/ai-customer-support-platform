# Progress — AI Customer Support Platform

Last updated: 2026-09-02

## Status summary

**Day 1–4:** Complete (re-audited 2026-09-01).  
**Day 5:** **Complete** — Email channel, omnichannel foundation, unified inbox, Customer 360, attachments, channel settings.

LLM: **Google Gemini** when `GEMINI_API_KEY` is set; otherwise **Echo/heuristic** + offline lexical embeddings.

---

## Day 5 — Completed

| Phase | Work |
|-------|------|
| 1 | Migration `0007_day5_omnichannel`: `Message` extensions, `ExternalMessage`, `Attachment`, `ChannelConfiguration`, `DeliveryStatus` |
| 2 | `ObjectStorage` (local filesystem), normalized channel events, webhook architecture |
| 3 | `EmailProvider` ABC + `MockEmailProvider` + `ResendEmailProvider` |
| 4 | `EmailAdapter`, `MessageNormalizer`, `CustomerResolver`, `receive_inbound()` |
| 5 | `POST /webhooks/email/inbound`, idempotency, email threading |
| 6 | Outbound email via adapter, delivery status lifecycle, AI → `EmailAdapter` |
| 7 | Attachment model/API, local object storage |
| 8 | Per-channel AI modes validated on EMAIL (Suggest / Autopilot / KB) |
| 9 | Unified inbox filters + badges, Customer 360 API + UI, channel settings |
| 10 | Ticket integration on email escalation (source, customer_id, channel) |
| 11–12 | Channels API, email composer UI, `/settings/channels`, `/customers/:id` |
| 13 | Day 5 test suite — **16 tests**, Day 4 regression — **26/26** |

## Day 5 tests

```bash
docker compose exec backend pytest -q \
  tests/test_day5_phase1_models.py \
  tests/test_day5_customer_resolver.py \
  tests/test_day5_email_inbound.py \
  tests/test_day5_email_outbound.py \
  tests/test_day5_email_threading.py \
  tests/test_day5_email_ai_suggest.py \
  tests/test_day5_email_autopilot.py \
  tests/test_day5_email_escalation.py \
  tests/test_day5_attachments.py \
  tests/test_channel_adapter.py
```

**Result:** 16/16 passed (2026-09-02)

---

## Day 4 — Completed (prior)

See [`docs/day4-final-audit.md`](day4-final-audit.md). Day 4 suite: **26/26 passed** after Day 5 changes.

---

## Documentation

- Day 5 plan: [`docs/day5-implementation-plan.md`](day5-implementation-plan.md)
- Day 5 schema: [`docs/database/day5-schema.md`](database/day5-schema.md)
- Run guide: [`docs/run-guide.md`](run-guide.md)

## Default credentials

- Email: `agent@example.com`
- Password: `agent123!`

## Notes

- **Email provider (dev):** `EMAIL_PROVIDER=mock` — no external API required
- **Inbound webhook:** `POST /api/v1/webhooks/email/inbound` with `x-mock-signature: test-bypass` for local testing
- **Channel defaults (seed):** Web Chat=Autopilot, Email=Suggest Reply, Form=Knowledge Base
- **Customer 360:** `/customers/:customerId` or `GET /api/v1/customers/{id}/360`
