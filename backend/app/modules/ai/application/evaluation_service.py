"""AI evaluation suite runner."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai.application.ai_config_service import get_or_create_ai_config
from app.modules.ai.application.runtime_config import RuntimeAIConfig
from app.modules.ai.domain.models import AIEvaluation, AIEvaluationResult, EvaluationBehavior
from app.modules.ai.domain.schemas import (
    AgentDecision,
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationReport,
    IntentLabel,
    SupportAgentState,
)
from app.modules.ai.graphs.support_agent import timed_support_agent
from app.modules.ai.infrastructure.llm.providers import EchoLLMProvider

EVALUATION_CASES: list[dict] = [
    {"input": "How do I reset my password?", "expected_intent": "ACCOUNT_ACCESS", "expected_behavior": "ANSWER", "expected_answer_contains": ["password"], "expected_escalation": False, "category": "FAQ"},
    {"input": "Where is the forgot password link?", "expected_intent": "ACCOUNT_ACCESS", "expected_behavior": "ANSWER", "expected_answer_contains": ["password"], "expected_escalation": False, "category": "FAQ"},
    {"input": "Can you change my billing plan?", "expected_intent": "BILLING", "expected_behavior": "ESCALATE", "expected_escalation": True, "category": "Billing"},
    {"input": "I was charged twice this month", "expected_intent": "BILLING", "expected_behavior": "ESCALATE", "expected_escalation": True, "category": "Billing"},
    {"input": "How do I update my account email?", "expected_intent": "ACCOUNT_ACCESS", "expected_behavior": "ANSWER", "expected_answer_contains": ["account"], "expected_escalation": False, "category": "Account"},
    {"input": "The app crashes when I open settings", "expected_intent": "BUG_REPORT", "expected_behavior": "ESCALATE", "expected_escalation": True, "category": "Technical"},
    {"input": "API requests return 500 errors", "expected_intent": "TECHNICAL_ISSUE", "expected_behavior": "ESCALATE", "expected_escalation": True, "category": "Technical"},
    {"input": "What is your refund policy?", "expected_intent": "REFUND", "expected_behavior": "ESCALATE", "expected_escalation": True, "category": "Billing"},
    {"input": "I want to cancel my subscription", "expected_intent": "CANCELLATION", "expected_behavior": "ESCALATE", "expected_escalation": True, "category": "Billing"},
    {"input": "Can you add dark mode?", "expected_intent": "FEATURE_REQUEST", "expected_behavior": "ESCALATE", "expected_escalation": True, "category": "OutOfScope"},
    {"input": "asdfghjkl random gibberish", "expected_intent": "OTHER", "expected_behavior": "ESCALATE", "expected_escalation": True, "category": "Unknown"},
    {"input": "help", "expected_intent": "GENERAL_QUESTION", "expected_behavior": "ESCALATE", "expected_escalation": True, "category": "Ambiguous"},
    {"input": "This is the third time I've contacted you!", "expected_intent": "OTHER", "expected_behavior": "ESCALATE", "expected_escalation": True, "category": "Angry"},
    {"input": "I need to speak to a human right now", "expected_intent": "OTHER", "expected_behavior": "ESCALATE", "expected_escalation": True, "category": "HumanRequest"},
    {"input": "¿Cómo puedo restablecer mi contraseña?", "expected_intent": "ACCOUNT_ACCESS", "expected_behavior": "ANSWER", "expected_answer_contains": ["contraseña"], "expected_escalation": False, "category": "Multilingual"},
    {"input": "Does your product integrate with XYZ?", "expected_intent": "GENERAL_QUESTION", "expected_behavior": "ESCALATE", "expected_escalation": True, "category": "OutOfScope"},
    {"input": "What are your business hours?", "expected_intent": "GENERAL_QUESTION", "expected_behavior": "ANSWER", "expected_escalation": False, "category": "FAQ"},
    {"input": "My login isn't working", "expected_intent": "ACCOUNT_ACCESS", "expected_behavior": "ANSWER", "expected_escalation": False, "category": "Account"},
    {"input": "Can I get a invoice copy?", "expected_intent": "BILLING", "expected_behavior": "ESCALATE", "expected_escalation": True, "category": "Billing"},
    {"input": "The export feature failed", "expected_intent": "TECHNICAL_ISSUE", "expected_behavior": "ESCALATE", "expected_escalation": True, "category": "Technical"},
    {"input": "How do I invite team members?", "expected_intent": "GENERAL_QUESTION", "expected_behavior": "ANSWER", "expected_escalation": False, "category": "FAQ"},
    {"input": "I'm furious about this service!", "expected_intent": "OTHER", "expected_behavior": "ESCALATE", "expected_escalation": True, "category": "Angry"},
    {"input": "Can you tell me about quantum physics?", "expected_intent": "OTHER", "expected_behavior": "ESCALATE", "expected_escalation": True, "category": "OutOfScope"},
    {"input": "Password reset link expired", "expected_intent": "ACCOUNT_ACCESS", "expected_behavior": "ANSWER", "expected_answer_contains": ["password"], "expected_escalation": False, "category": "Account"},
    {"input": "Connect me with billing please", "expected_intent": "BILLING", "expected_behavior": "ESCALATE", "expected_escalation": True, "category": "HumanRequest"},
]


class EvaluationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_or_create_evaluation(self, organization_id: str) -> AIEvaluation:
        row = await self.db.scalar(
            select(AIEvaluation).where(
                AIEvaluation.organization_id == organization_id,
                AIEvaluation.name == "Day 4 Baseline",
            )
        )
        if row is None:
            row = AIEvaluation(
                organization_id=organization_id,
                name="Day 4 Baseline",
                version=1,
                case_count=len(EVALUATION_CASES),
                cases=EVALUATION_CASES,
            )
            self.db.add(row)
            await self.db.flush()
        elif row.case_count != len(EVALUATION_CASES) or len(row.cases or []) != len(EVALUATION_CASES):
            row.case_count = len(EVALUATION_CASES)
            row.cases = EVALUATION_CASES
            await self.db.flush()
        return row

    async def run_suite(self, organization_id: str) -> EvaluationReport:
        evaluation = await self.get_or_create_evaluation(organization_id)
        base_config = await get_or_create_ai_config(self.db, organization_id)
        config = RuntimeAIConfig.from_config(base_config)
        llm = EchoLLMProvider()
        results: list[EvaluationCaseResult] = []
        intent_ok = grounding_ok = escalation_ok = answer_ok = 0

        for idx, raw in enumerate(EVALUATION_CASES):
            case = EvaluationCase(
                input=raw["input"],
                expected_intent=IntentLabel(raw["expected_intent"]) if raw.get("expected_intent") else None,
                expected_behavior=EvaluationBehavior(raw["expected_behavior"]),
                expected_answer_contains=raw.get("expected_answer_contains") or [],
                expected_escalation=raw.get("expected_escalation", False),
                category=raw.get("category", "FAQ"),
            )
            final_state, _, _ = await timed_support_agent(
                SupportAgentState(organization_id=organization_id, user_message=raw["input"]),
                config=config,
                llm=llm,
                db_session=None,
            )
            response_decision = final_state.decision or AgentDecision.ESCALATE
            actual = {
                "intent": final_state.intent.value if final_state.intent else IntentLabel.OTHER.value,
                "escalation_required": final_state.escalation_required,
                "grounded": final_state.grounded,
                "answer": final_state.final_response or final_state.draft_response or "",
                "decision": response_decision.value,
            }
            passed = True
            if case.expected_intent and final_state.intent != case.expected_intent:
                passed = False
            if final_state.escalation_required != case.expected_escalation:
                passed = False
            answer_text = actual["answer"]
            if case.expected_answer_contains:
                lower = answer_text.lower()
                if not all(fragment.lower() in lower for fragment in case.expected_answer_contains):
                    passed = False

            if case.expected_intent and final_state.intent == case.expected_intent:
                intent_ok += 1
            if final_state.grounded:
                grounding_ok += 1
            if final_state.escalation_required == case.expected_escalation:
                escalation_ok += 1
            if not case.expected_answer_contains or all(f.lower() in answer_text.lower() for f in case.expected_answer_contains):
                answer_ok += 1

            self.db.add(
                AIEvaluationResult(
                    id=str(uuid.uuid4()),
                    evaluation_id=evaluation.id,
                    case_index=idx,
                    input_message=raw["input"],
                    expected=case.model_dump(mode="json"),
                    actual=actual,
                    passed=passed,
                    scores={"confidence": final_state.support_confidence},
                )
            )
            results.append(
                EvaluationCaseResult(
                    case_index=idx,
                    input=raw["input"],
                    passed=passed,
                    expected=case.model_dump(mode="json"),
                    actual=actual,
                )
            )

        total = len(EVALUATION_CASES)
        await self.db.flush()
        return EvaluationReport(
            evaluation_id=evaluation.id,
            name=evaluation.name,
            total_cases=total,
            passed_cases=sum(1 for r in results if r.passed),
            failed_cases=sum(1 for r in results if not r.passed),
            intent_accuracy=round(intent_ok / total, 4),
            grounding_rate=round(grounding_ok / total, 4),
            escalation_accuracy=round(escalation_ok / total, 4),
            answer_quality=round(answer_ok / total, 4),
            results=results,
        )
