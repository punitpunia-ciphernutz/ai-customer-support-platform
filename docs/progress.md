# Progress — AI Customer Support Platform

Last updated: 2026-09-02 (Day 5 fix pass + re-audit)

## Status summary

**Day 1–4:** Complete (re-audited 2026-09-01).  
**Day 5:** **Complete** — Email channel, omnichannel foundation, unified inbox, Customer 360, attachments (wired + UI), channel settings, audit fix pass closed.

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
| 7 | Attachment model/API, inbound store, outbound send, UI chips in `MessageBubble` |
| 8 | Per-channel AI modes on EMAIL (Suggest / Autopilot / KB) + PATCH via `/ai/config` |
| 9 | Unified inbox filters + badges, Customer 360 API + UI, channel settings |
| 10 | Ticket integration on email escalation |
| 11–12 | Channels API, email composer (To/subject/body), `/channels`, `/app/channels`, route aliases |
| 13 | Day 5 test suite — **23 tests**, Day 4 regression — **26/26** |
| Fix pass | Audit P1/P2 closed — see [`docs/day5-audit.md`](day5-audit.md) |

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
  tests/test_day5_bot_config_patch.py \
  tests/test_day5_attachments_inbound.py \
  tests/test_day5_attachments_outbound.py \
  tests/test_day5_email_suggest_accept_send.py \
  tests/test_day5_email_knowledge_base.py \
  tests/test_day5_webhook_enabled.py \
  tests/test_channel_adapter.py
```

**Result:** 23/23 passed (2026-09-02 fix pass)

Full backend: **97/101** (4 pre-existing Gemini/env failures when `GEMINI_API_KEY` is set in container)

---

## Day 4 — Completed (prior)

See [`docs/day4-final-audit.md`](day4-final-audit.md). Day 4 suite: **26/26 passed** after Day 5 changes.

---

## Documentation

- Day 5 plan: [`docs/day5-implementation-plan.md`](day5-implementation-plan.md)
- Day 5 audit (re-audit): [`docs/day5-audit.md`](day5-audit.md)
- Day 5 schema: [`docs/database/day5-schema.md`](database/day5-schema.md)
- Run guide: [`docs/run-guide.md`](run-guide.md)

## Default credentials

- Email: `agent@example.com`
- Password: `agent123!`

## Notes

- **Email provider (dev):** `EMAIL_PROVIDER=mock` — no external API required
- **Inbound webhook:** `POST /api/v1/webhooks/email/inbound` with `x-mock-signature: test-bypass` for local testing
- **Disabled channel:** webhook returns **403** when EMAIL channel is disabled
- **Channel AI mode:** `PATCH /api/v1/ai/config` with `channel_overrides` or UI at **Channels / Channel settings**
- **Channel defaults (seed):** Web Chat=Autopilot, Email=Suggest Reply, Form=Knowledge Base
- **Customer 360:** `/customers/:customerId` or `/app/customers/:customerId`
- **Channel overview:** `/channels` or `/app/channels`
