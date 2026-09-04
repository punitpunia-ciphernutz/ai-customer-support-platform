"""Day 3 support agent tests."""

import pytest
from sqlalchemy import select

from app.infrastructure.database.models import Message, Organization, SenderType, Ticket
from app.infrastructure.database.session import AsyncSessionLocal
from app.modules.ai.application.ai_config_service import get_or_create_ai_config
from app.modules.ai.application.ai_service import AIService
from app.modules.ai.application.context_builder import ContextBuilder, format_history_for_prompt
from app.modules.ai.application.confidence import calculate_support_confidence
from app.modules.ai.application.escalation import detect_human_request, evaluate_escalation
from app.modules.ai.domain.models import AIConfig, AIMode, AIRun, AIRunStatus, AIRunType
from app.modules.ai.domain.schemas import (
    AgentDecision,
    Citation,
    ConversationTurn,
    CustomerContext,
    IntentLabel,
    RetrievedDocument,
    SupportAgentState,
)
from app.modules.ai.infrastructure.llm.providers import EchoLLMProvider
from app.modules.ai.infrastructure.reranker import Reranker, aggregate_retrieval_score
from app.modules.knowledge.application.ingestion_service import IngestionService
from app.modules.knowledge.domain.models import IngestionStatus, KnowledgeSource, KnowledgeSourceType
from app.modules.knowledge.infrastructure.embeddings import OfflineSemanticEmbeddingProvider
from app.modules.knowledge.infrastructure.loaders import LoadedContent
from app.modules.knowledge.infrastructure.vectorstore import PgVectorRetriever
from app.modules.conversations.schemas import ConversationCreate
from app.modules.conversations.service import ConversationService
from app.infrastructure.database.models import Customer, User


@pytest.mark.asyncio
async def test_context_builder_includes_history() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        customer = Customer(organization_id=org_id, name="John Smith", email="john@acme.com", company_name="Acme Inc.")
        session.add(customer)
        await session.flush()
        user = (await session.execute(select(User).limit(1))).scalar_one()
        conv = await ConversationService(session).create_conversation(
            user,
            ConversationCreate(customer_id=customer.id, channel="WEB_CHAT", initial_message="I can't login."),
        )
        from app.modules.conversations.schemas import MessageCreate

        await ConversationService(session).add_agent_message(
            user,
            conv.id,
            MessageCreate(content="What error are you seeing?", sender_type=SenderType.AGENT),
        )
        await ConversationService(session).add_public_message(
            conv.id, customer.id, "It says invalid password."
        )
        msgs = await session.execute(select(Message).where(Message.conversation_id == conv.id))
        last = list(msgs.scalars().all())[-1]
        state = await ContextBuilder(session).build(conv.id, last.id)
        assert state.user_message == "It says invalid password."
        assert len(state.conversation_history) >= 2
        formatted = format_history_for_prompt(state.conversation_history)
        assert "login" in formatted.lower()
        await session.rollback()


@pytest.mark.asyncio
async def test_confidence_engine_weighted() -> None:
    state = SupportAgentState(
        intent=IntentLabel.ACCOUNT_ACCESS,
        intent_confidence=0.96,
        retrieval_score=0.92,
        grounded=True,
        citations=[Citation(document_id="1", title="Guide")],
        customer_context=CustomerContext(customer_id="c1", name="John"),
        user_message="reset password",
        draft_response="Use Settings → Security.",
        conversation_history=[ConversationTurn(sender_type="CUSTOMER", content="help")],
    )
    score = calculate_support_confidence(state)
    assert score >= 0.85


@pytest.mark.asyncio
async def test_human_request_detection() -> None:
    assert detect_human_request("I want to speak to a human.")
    assert not detect_human_request("How do I reset my password?")


@pytest.mark.asyncio
async def test_reranker_orders_password_doc() -> None:
    from app.modules.knowledge.infrastructure.vectorstore.retriever import RetrievalHit

    hits = [
        RetrievalHit("c1", "d1", "Billing FAQ", "Change your billing plan in admin.", 0.7, {}),
        RetrievalHit("c2", "d2", "Password Reset Guide", "Reset from Settings → Security.", 0.65, {}),
    ]
    ranked = await Reranker().rank("How do I reset my password?", hits, top_k=2)
    assert ranked[0].hit.title == "Password Reset Guide"
    assert aggregate_retrieval_score(ranked) > 0.4


@pytest.mark.asyncio
async def test_ai_test_known_password_question() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        source = KnowledgeSource(
            organization_id=org_id,
            name="FAQ",
            type=KnowledgeSourceType.TEXT,
            status=IngestionStatus.PENDING,
            configuration={},
        )
        session.add(source)
        await session.flush()
        service = IngestionService(session, embedding_provider=OfflineSemanticEmbeddingProvider())
        doc = await service.create_pending_document(
            source=source,
            title="Password Reset Guide",
            content="x",
        )
        await service.ingest_loaded_content(
            doc.id,
            LoadedContent(
                title="Password Reset Guide",
                text="How do I reset my password? Go to Settings → Security → Reset Password.",
                metadata={"source_type": "TEXT"},
            ),
        )
        config = await get_or_create_ai_config(session, org_id)
        config.auto_reply_threshold = 0.84
        config.escalation_threshold = 0.84
        response = await AIService(session, llm=EchoLLMProvider()).run_test(
            "How do I reset my password?",
            organization_id=org_id,
        )
        assert response.intent == IntentLabel.ACCOUNT_ACCESS
        assert response.confidence >= 0.84
        assert response.grounded
        assert response.citations
        assert response.decision == AgentDecision.AI_RESOLVE
        await session.rollback()


@pytest.mark.asyncio
async def test_ai_test_billing_escalation() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        response = await AIService(session, llm=EchoLLMProvider()).run_test(
            "Can you change my company's billing plan?",
            organization_id=org_id,
        )
        assert response.escalation_required
        assert response.decision == AgentDecision.ESCALATE
        await session.rollback()


@pytest.mark.asyncio
async def test_ai_test_human_request_escalation() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        response = await AIService(session, llm=EchoLLMProvider()).run_test(
            "I want to speak to a human.",
            organization_id=org_id,
        )
        assert response.escalation_required
        await session.rollback()


@pytest.mark.asyncio
async def test_idempotency_skips_duplicate_agent_run() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        customer = Customer(organization_id=org_id, name="Idem", email="idem@example.com")
        session.add(customer)
        await session.flush()
        user = (await session.execute(select(User).limit(1))).scalar_one()
        conv = await ConversationService(session).create_conversation(
            user,
            ConversationCreate(customer_id=customer.id, channel="WEB_CHAT"),
        )
        msg = await ConversationService(session).add_public_message(
            conv.id, customer.id, "How do I reset my password?"
        )
        ai = AIService(session, llm=EchoLLMProvider())
        _, run1 = await ai.run_support_agent(conv.id, msg.id, persist_side_effects=False)
        _, run2 = await ai.run_support_agent(conv.id, msg.id, persist_side_effects=False)
        assert run1.id == run2.id
        count = (
            await session.execute(
                select(AIRun).where(
                    AIRun.message_id == msg.id,
                    AIRun.type == AIRunType.AGENT,
                )
            )
        ).scalars().all()
        assert len(count) == 1
        await session.rollback()


@pytest.mark.asyncio
async def test_process_customer_message_creates_ai_reply() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        config = await get_or_create_ai_config(session, org_id)
        config.mode = AIMode.AUTO_REPLY
        config.enabled = True
        source = KnowledgeSource(
            organization_id=org_id,
            name="FAQ",
            type=KnowledgeSourceType.TEXT,
            status=IngestionStatus.PENDING,
            configuration={},
        )
        session.add(source)
        await session.flush()
        ingest = IngestionService(session, embedding_provider=OfflineSemanticEmbeddingProvider())
        doc = await ingest.create_pending_document(source=source, title="Password Reset Guide", content="x")
        await ingest.ingest_loaded_content(
            doc.id,
            LoadedContent(
                title="Password Reset Guide",
                text="Reset your password from Settings → Security → Reset Password.",
                metadata={},
            ),
        )
        customer = Customer(organization_id=org_id, name="Chat User", email="chat@example.com")
        session.add(customer)
        await session.flush()
        user = (await session.execute(select(User).limit(1))).scalar_one()
        conv = await ConversationService(session).create_conversation(
            user,
            ConversationCreate(customer_id=customer.id, channel="WEB_CHAT"),
        )
        msg = await ConversationService(session).add_public_message(
            conv.id, customer.id, "How do I reset my password?"
        )
        run = await AIService(session, llm=EchoLLMProvider()).process_customer_message(msg.id)
        assert run is not None
        assert run.status == AIRunStatus.COMPLETED
        ai_messages = (
            await session.execute(
                select(Message).where(
                    Message.conversation_id == conv.id,
                    Message.sender_type == SenderType.AI,
                )
            )
        ).scalars().all()
        assert any("password" in m.content.lower() for m in ai_messages)
        await session.rollback()


@pytest.mark.asyncio
async def test_escalation_creates_ticket() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        config = await get_or_create_ai_config(session, org_id)
        config.mode = AIMode.AUTO_REPLY
        customer = Customer(organization_id=org_id, name="Billing User", email="bill@example.com")
        session.add(customer)
        await session.flush()
        user = (await session.execute(select(User).limit(1))).scalar_one()
        conv = await ConversationService(session).create_conversation(
            user,
            ConversationCreate(customer_id=customer.id, channel="WEB_CHAT"),
        )
        msg = await ConversationService(session).add_public_message(
            conv.id, customer.id, "Can you change my company's billing plan?"
        )
        await AIService(session, llm=EchoLLMProvider()).process_customer_message(msg.id)
        tickets = (
            await session.execute(select(Ticket).where(Ticket.conversation_id == conv.id))
        ).scalars().all()
        assert tickets
        await session.rollback()


@pytest.mark.asyncio
async def test_ai_test_multilingual_password() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        response = await AIService(session, llm=EchoLLMProvider()).run_test(
            "¿Cómo restablezco mi contraseña?",
            organization_id=org_id,
        )
        assert response.intent == IntentLabel.ACCOUNT_ACCESS
        assert "contraseña" in response.answer.lower() or "password" in response.answer.lower()
        await session.rollback()


@pytest.mark.asyncio
async def test_ai_test_ambiguous_question() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        response = await AIService(session, llm=EchoLLMProvider()).run_test(
            "It isn't working.",
            organization_id=org_id,
        )
        assert response.intent == IntentLabel.TECHNICAL_ISSUE
        assert (
            response.escalation_required
            or response.decision == AgentDecision.SOFT_REPLY
            or "detail" in response.answer.lower()
            or "clarif" in response.answer.lower()
            or "more" in response.answer.lower()
            or "knowledge" in response.answer.lower()
        )
        assert not response.grounded
        await session.rollback()


@pytest.mark.asyncio
async def test_ai_test_unsupported_integration() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        response = await AIService(session, llm=EchoLLMProvider()).run_test(
            "Does your product integrate with XYZ?",
            organization_id=org_id,
        )
        # Response Policy: true OOD soft-refuses by default (no ticket / no escalate)
        assert response.decision == AgentDecision.SOFT_REPLY
        assert not response.escalation_required
        assert not response.grounded
        assert response.message_kind is not None
        lower = response.answer.lower()
        assert "outside" in lower or "help with" in lower or "focus" in lower
        await session.rollback()


@pytest.mark.asyncio
async def test_ai_test_unsupported_integration_policy_off_escalates() -> None:
    async with AsyncSessionLocal() as session:
        from app.modules.ai.application.ai_config_service import get_or_create_ai_config

        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        cfg = await get_or_create_ai_config(session, org_id)
        cfg.response_policy_enabled = False
        await session.flush()
        response = await AIService(session, llm=EchoLLMProvider()).run_test(
            "Does your product integrate with XYZ?",
            organization_id=org_id,
        )
        assert response.escalation_required
        assert response.decision == AgentDecision.ESCALATE
        await session.rollback()


@pytest.mark.asyncio
async def test_agent_run_lifecycle_pending_running_completed() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        customer = Customer(organization_id=org_id, name="Lifecycle", email="life@example.com")
        session.add(customer)
        await session.flush()
        user = (await session.execute(select(User).limit(1))).scalar_one()
        conv = await ConversationService(session).create_conversation(
            user,
            ConversationCreate(customer_id=customer.id, channel="WEB_CHAT"),
        )
        msg = await ConversationService(session).add_public_message(
            conv.id, customer.id, "How do I reset my password?"
        )
        ai = AIService(session, llm=EchoLLMProvider())
        observed: list[AIRunStatus] = []
        original_flush = session.flush

        async def tracking_flush(*args, **kwargs):
            await original_flush(*args, **kwargs)
            run = await ai._get_existing_agent_run(msg.id)  # noqa: SLF001
            if run is not None:
                observed.append(run.status)

        session.flush = tracking_flush  # type: ignore[method-assign]

        _, completed = await ai.run_support_agent(conv.id, msg.id, persist_side_effects=False)
        assert AIRunStatus.PENDING in observed
        assert AIRunStatus.RUNNING in observed
        assert completed.status == AIRunStatus.COMPLETED
        await session.rollback()


@pytest.mark.asyncio
async def test_failed_run_retry_reuses_run_without_duplicate(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.ai import application
    from app.modules.ai import tasks_bridge

    calls = {"count": 0}
    original = application.ai_service.timed_support_agent

    async def flaky_support_agent(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("simulated transient failure")
        return await original(*args, **kwargs)

    monkeypatch.setattr(application.ai_service, "timed_support_agent", flaky_support_agent)
    monkeypatch.setattr(tasks_bridge, "enqueue_ai_message_processing", lambda *_args, **_kwargs: None)

    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        config = await get_or_create_ai_config(session, org_id)
        config.mode = AIMode.AUTO_REPLY
        customer = Customer(organization_id=org_id, name="Retry", email="retry@example.com")
        session.add(customer)
        await session.flush()
        user = (await session.execute(select(User).limit(1))).scalar_one()
        conv = await ConversationService(session).create_conversation(
            user,
            ConversationCreate(customer_id=customer.id, channel="WEB_CHAT"),
        )
        msg = await ConversationService(session).add_public_message(
            conv.id, customer.id, "How do I reset my password?"
        )
        ai = AIService(session, llm=EchoLLMProvider())

        with pytest.raises(RuntimeError, match="simulated transient failure"):
            await ai.run_support_agent(conv.id, msg.id, persist_side_effects=False)

        failed = await ai._get_existing_agent_run(msg.id)  # noqa: SLF001
        assert failed is not None
        assert failed.status == AIRunStatus.FAILED

        _, retried = await ai.run_support_agent(conv.id, msg.id, persist_side_effects=False)
        assert retried.id == failed.id
        assert retried.status == AIRunStatus.COMPLETED

        runs = (
            await session.execute(
                select(AIRun).where(
                    AIRun.message_id == msg.id,
                    AIRun.type == AIRunType.AGENT,
                )
            )
        ).scalars().all()
        assert len(runs) == 1
        await session.rollback()


@pytest.mark.asyncio
async def test_celery_ai_pipeline_publishes_message_event(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.infrastructure.events import DomainEvent, event_bus
    from app.modules.ai import tasks_bridge

    published: list[DomainEvent] = []

    async def capture_publish(event: DomainEvent) -> None:
        published.append(event)

    async def run_celery_ai_task(message_id: str) -> str:
        """Same flow as ``_run_process_ai_message`` with deterministic offline LLM."""
        async with AsyncSessionLocal() as session:
            try:
                run = await AIService(session, llm=EchoLLMProvider()).process_customer_message(message_id)
                await session.commit()
                return run.id if run else "skipped"
            except Exception:
                await session.commit()
                raise

    monkeypatch.setattr(event_bus, "publish", capture_publish)
    monkeypatch.setattr(tasks_bridge, "enqueue_ai_message_processing", lambda *_args, **_kwargs: None)

    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        config = await get_or_create_ai_config(session, org_id)
        config.mode = AIMode.AUTO_REPLY
        config.enabled = True
        source = KnowledgeSource(
            organization_id=org_id,
            name="FAQ",
            type=KnowledgeSourceType.TEXT,
            status=IngestionStatus.PENDING,
            configuration={},
        )
        session.add(source)
        await session.flush()
        ingest = IngestionService(session, embedding_provider=OfflineSemanticEmbeddingProvider())
        doc = await ingest.create_pending_document(source=source, title="Password Reset Guide", content="x")
        await ingest.ingest_loaded_content(
            doc.id,
            LoadedContent(
                title="Password Reset Guide",
                text="Reset your password from Settings → Security → Reset Password.",
                metadata={},
            ),
        )
        customer = Customer(organization_id=org_id, name="Celery User", email="celery@example.com")
        session.add(customer)
        await session.flush()
        user = (await session.execute(select(User).limit(1))).scalar_one()
        conv = await ConversationService(session).create_conversation(
            user,
            ConversationCreate(customer_id=customer.id, channel="WEB_CHAT"),
        )
        msg = await ConversationService(session).add_public_message(
            conv.id, customer.id, "How do I reset my password?"
        )
        message_id = msg.id
        await session.commit()

    run_id = await run_celery_ai_task(message_id)
    assert run_id != "skipped"

    async with AsyncSessionLocal() as session:
        run = await session.get(AIRun, run_id)
        assert run is not None
        assert run.status == AIRunStatus.COMPLETED
        ai_messages = (
            await session.execute(
                select(Message).where(
                    Message.conversation_id == run.conversation_id,
                    Message.sender_type == SenderType.AI,
                )
            )
        ).scalars().all()
        assert ai_messages

    ai_events = [
        event
        for event in published
        if event.name == "message.created" and event.payload.get("sender_type") == "AI"
    ]
    assert ai_events
    assert any("password" in (event.payload.get("content") or "").lower() for event in ai_events)


@pytest.mark.asyncio
async def test_ai_disabled_skips_processing() -> None:
    async with AsyncSessionLocal() as session:
        org_id = (await session.execute(select(Organization.id).limit(1))).scalar_one()
        config = await get_or_create_ai_config(session, org_id)
        config.enabled = False
        customer = Customer(organization_id=org_id, name="Off", email="off@example.com")
        session.add(customer)
        await session.flush()
        user = (await session.execute(select(User).limit(1))).scalar_one()
        conv = await ConversationService(session).create_conversation(
            user,
            ConversationCreate(customer_id=customer.id, channel="WEB_CHAT"),
        )
        msg = await ConversationService(session).add_public_message(conv.id, customer.id, "Hello")
        with pytest.raises(ValueError, match="disabled"):
            await AIService(session, llm=EchoLLMProvider()).run_support_agent(
                conv.id, msg.id, persist_side_effects=False
            )
        await session.rollback()
