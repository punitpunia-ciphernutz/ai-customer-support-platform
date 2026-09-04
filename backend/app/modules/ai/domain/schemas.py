from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.modules.ai.domain.models import AIMode, AIRunStatus, AIRunType, EvaluationBehavior, SentimentLabel


class AIRunInput(BaseModel):
    text: str


class AIRunOutput(BaseModel):
    text: str


class IntentLabel(StrEnum):
    GENERAL_QUESTION = "GENERAL_QUESTION"
    ACCOUNT_ACCESS = "ACCOUNT_ACCESS"
    BILLING = "BILLING"
    TECHNICAL_ISSUE = "TECHNICAL_ISSUE"
    BUG_REPORT = "BUG_REPORT"
    FEATURE_REQUEST = "FEATURE_REQUEST"
    REFUND = "REFUND"
    CANCELLATION = "CANCELLATION"
    OTHER = "OTHER"


class MessageKind(StrEnum):
    """Conversational act — orthogonal to support IntentLabel. LLM-classified."""

    GREETING = "GREETING"
    IDENTITY = "IDENTITY"
    SMALL_TALK = "SMALL_TALK"
    SUPPORT_REQUEST = "SUPPORT_REQUEST"
    HUMAN_REQUEST = "HUMAN_REQUEST"
    OUT_OF_DOMAIN = "OUT_OF_DOMAIN"
    UNCLEAR = "UNCLEAR"


class PolicyAction(StrEnum):
    SAFE_REPLY = "SAFE_REPLY"
    SOFT_REFUSE = "SOFT_REFUSE"
    CONTINUE_SUPPORT = "CONTINUE_SUPPORT"
    ESCALATE = "ESCALATE"
    CLARIFY = "CLARIFY"


class SoftRefuseKind(StrEnum):
    """Why a soft refuse was chosen — never treat no-KB as automatic OOD."""

    OUT_OF_DOMAIN = "OUT_OF_DOMAIN"
    INSUFFICIENT_KNOWLEDGE = "INSUFFICIENT_KNOWLEDGE"


class AIClassification(BaseModel):
    intent: IntentLabel
    language: str = Field(default="en", min_length=2, max_length=16)
    sentiment: SentimentLabel = Field(
        default=SentimentLabel.NEUTRAL,
        description=(
            "Overall customer emotion from meaning, context, and intensity — not keyword matching. "
            "POSITIVE: thanks, praise, satisfaction. "
            "NEUTRAL: factual or no strong emotion. "
            "NEGATIVE: dissatisfaction or mild frustration without hostility. "
            "ANGRY: strong anger, hostility, aggression, or threats "
            "(even without words like angry/mad)."
        ),
    )
    confidence: float = Field(ge=0.0, le=1.0)
    requires_human: bool = False
    message_kind: MessageKind = MessageKind.SUPPORT_REQUEST
    message_kind_confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class ClassifyRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = None
    message_id: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class ClassifyResponse(BaseModel):
    classification: AIClassification
    ai_run_id: str


class Citation(BaseModel):
    document_id: str
    title: str
    chunk_id: str | None = None


class RetrievedDocument(BaseModel):
    document_id: str
    title: str
    content: str
    score: float
    chunk_id: str | None = None


class CustomerContext(BaseModel):
    customer_id: str
    name: str
    email: str | None = None
    company: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationTurn(BaseModel):
    sender_type: str
    content: str


class AgentDecision(StrEnum):
    AI_RESOLVE = "AI_RESOLVE"
    ESCALATE = "ESCALATE"
    SUGGEST_ONLY = "SUGGEST_ONLY"
    SOFT_REPLY = "SOFT_REPLY"


class ConfidenceComponents(BaseModel):
    intent: float = Field(ge=0.0, le=1.0)
    retrieval: float = Field(ge=0.0, le=1.0)
    grounding: float = Field(ge=0.0, le=1.0)
    context: float = Field(ge=0.0, le=1.0)
    policy: float = Field(ge=0.0, le=1.0)
    response_validation: float = Field(default=1.0, ge=0.0, le=1.0)


class ConfidenceBreakdown(BaseModel):
    final: float = Field(ge=0.0, le=1.0)
    components: ConfidenceComponents
    decision: AgentDecision
    reasons: list[str] = Field(default_factory=list)


class GroundingResult(BaseModel):
    grounded: bool
    score: float = Field(ge=0.0, le=1.0)
    unsupported_claims: list[str] = Field(default_factory=list)


class AIRunTraceStep(BaseModel):
    name: str
    status: str
    duration_ms: int = 0
    input_summary: str | None = None
    output_summary: str | None = None
    error: str | None = None


class AIHandoffPackage(BaseModel):
    customer_name: str
    customer_company: str | None = None
    issue_summary: str
    intent: str
    ai_confidence: float
    confidence_breakdown: ConfidenceBreakdown | None = None
    knowledge_searched: list[str] = Field(default_factory=list)
    what_ai_tried: str
    why_escalated: str
    recommended_action: str
    sentiment: str | None = None
    language: str | None = None


class EvaluationCase(BaseModel):
    input: str
    expected_intent: IntentLabel | None = None
    expected_behavior: EvaluationBehavior
    expected_answer_contains: list[str] = Field(default_factory=list)
    expected_escalation: bool = False
    knowledge_documents: list[str] = Field(default_factory=list)
    category: str = "FAQ"


class EvaluationCaseResult(BaseModel):
    case_index: int
    input: str
    passed: bool
    expected: dict[str, Any]
    actual: dict[str, Any]
    scores: dict[str, float] = Field(default_factory=dict)


class EvaluationReport(BaseModel):
    evaluation_id: str
    name: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    intent_accuracy: float
    grounding_rate: float
    escalation_accuracy: float
    answer_quality: float
    results: list[EvaluationCaseResult] = Field(default_factory=list)


class BotConfigurationOut(BaseModel):
    channel: str
    mode: AIMode | None = None
    auto_reply_threshold: float | None = None
    escalation_threshold: float | None = None
    min_relevance_score: float | None = None
    require_knowledge: bool | None = None
    multilingual_enabled: bool | None = None

    model_config = {"from_attributes": True}


class BotConfigurationUpdate(BaseModel):
    channel: str = Field(min_length=1, max_length=32)
    mode: AIMode | None = None
    auto_reply_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    escalation_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    min_relevance_score: float | None = Field(default=None, ge=0.0, le=1.0)
    require_knowledge: bool | None = None
    multilingual_enabled: bool | None = None


class SupportAgentState(BaseModel):
    conversation_id: str | None = None
    message_id: str | None = None
    organization_id: str | None = None
    customer_context: CustomerContext | None = None
    conversation_history: list[ConversationTurn] = Field(default_factory=list)
    conversation_summary: str | None = None
    previous_ai_responses: list[str] = Field(default_factory=list)
    ticket_context: dict[str, Any] | None = None
    channel: str | None = None
    ai_control_mode: str = "AI_CONTROL"
    language: str = "en"
    user_message: str = ""
    prepared_query: str = ""
    intent: IntentLabel | None = None
    intent_confidence: float = 0.0
    message_kind: MessageKind | None = None
    message_kind_confidence: float = 0.0
    retrieved_documents: list[RetrievedDocument] = Field(default_factory=list)
    retrieval_score: float = 0.0
    knowledge_available: bool = True
    draft_response: str = ""
    grounded: bool = False
    grounding_score: float = 0.0
    citations: list[Citation] = Field(default_factory=list)
    support_confidence: float = 0.0
    confidence_breakdown: ConfidenceBreakdown | None = None
    sentiment: str = SentimentLabel.NEUTRAL.value
    escalation_required: bool = False
    escalation_reason: str | None = None
    escalation_summary: str | None = None
    decision: AgentDecision | None = None
    final_response: str | None = None
    human_requested: bool = False
    policy_action: PolicyAction | None = None
    policy_allows_ungrounded_send: bool = False
    soft_refuse_kind: SoftRefuseKind | None = None
    trace_steps: list[AIRunTraceStep] = Field(default_factory=list)
    prompt_version: str | None = None

    model_config = {"extra": "ignore"}


class AIResponse(BaseModel):
    answer: str
    intent: IntentLabel
    confidence: float = Field(ge=0.0, le=1.0)
    grounded: bool
    escalation_required: bool
    escalation_reason: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    decision: AgentDecision
    ai_run_id: str | None = None
    message_kind: MessageKind | None = None
    policy_action: PolicyAction | None = None


class GeneratedAnswer(BaseModel):
    answer: str
    grounded: bool = False
    needs_clarification: bool = False


class AITestRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = None
    organization_id: str | None = None


class AITestResponse(BaseModel):
    intent: IntentLabel
    confidence: float
    grounded: bool
    answer: str
    sources: list[Citation] = Field(default_factory=list)
    escalation_required: bool
    escalation_reason: str | None = None
    decision: AgentDecision
    message_kind: MessageKind | None = None
    policy_action: PolicyAction | None = None


class LLMModelOption(BaseModel):
    id: str
    label: str


class AIConfigOut(BaseModel):
    enabled: bool
    mode: AIMode
    mode_display: str | None = None
    auto_reply_threshold: float
    escalation_threshold: float
    min_relevance_score: float = 0.35
    require_knowledge: bool = True
    escalate_if_unknown: bool = True
    multilingual_enabled: bool = True
    hybrid_keyword_weight: float = 0.3
    missed_chat_timeout_minutes: int = 5
    ai_response_timeout_seconds: int = 60
    llm_model: str = "gemini-3.1-flash-lite"
    available_llm_models: list[LLMModelOption] = Field(default_factory=list)
    business_hours: dict[str, Any] | None = None
    allowed_intents: list[str] | None = None
    restricted_intents: list[str] | None = None
    intent_team_map: dict[str, str] | None = None
    channel_overrides: list[BotConfigurationOut] = Field(default_factory=list)
    response_policy_enabled: bool = True
    soft_reply_greetings: bool = True
    ood_soft_refuse: bool = True
    ood_escalates: bool = False
    safe_reply_min_kind_confidence: float = 0.55
    assistant_scope_summary: str = (
        "password resets, account access, billing questions, and other topics in our help center"
    )
    assistant_display_name: str = "Support Assistant"

    model_config = {"from_attributes": True}


class AIConfigUpdate(BaseModel):
    enabled: bool | None = None
    mode: AIMode | None = None
    auto_reply_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    escalation_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    min_relevance_score: float | None = Field(default=None, ge=0.0, le=1.0)
    require_knowledge: bool | None = None
    escalate_if_unknown: bool | None = None
    multilingual_enabled: bool | None = None
    hybrid_keyword_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    missed_chat_timeout_minutes: int | None = Field(default=None, ge=1, le=1440)
    ai_response_timeout_seconds: int | None = Field(default=None, ge=15, le=600)
    llm_model: str | None = Field(default=None, min_length=1, max_length=128)
    business_hours: dict[str, Any] | None = None
    allowed_intents: list[str] | None = None
    restricted_intents: list[str] | None = None
    intent_team_map: dict[str, str] | None = None
    channel_overrides: list[BotConfigurationUpdate] | None = None
    response_policy_enabled: bool | None = None
    soft_reply_greetings: bool | None = None
    ood_soft_refuse: bool | None = None
    ood_escalates: bool | None = None
    safe_reply_min_kind_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    assistant_scope_summary: str | None = Field(default=None, max_length=1000)
    assistant_display_name: str | None = Field(default=None, max_length=128)


class AIRunSummary(BaseModel):
    id: str
    conversation_id: str | None
    message_id: str | None
    type: AIRunType
    status: AIRunStatus
    model: str | None
    graph_version: str | None
    prompt_version: str | None = None
    intent: str | None
    retrieval_count: int | None
    retrieval_score: float | None = None
    grounding_score: float | None = None
    confidence: float | None
    decision: str | None = None
    language: str | None = None
    sentiment: str | None = None
    estimated_cost_usd: float | None = None
    latency_ms: int | None
    error: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AIRunDetail(AIRunSummary):
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] | None = None
    token_usage: dict[str, Any] | None = None
    confidence_components: dict[str, Any] | None = None
    trace: list[dict[str, Any]] | None = None

    model_config = {"from_attributes": True}


class AIUsageSummary(BaseModel):
    conversation_id: str | None = None
    period_days: int | None = None
    total_runs: int
    total_cost_usd: float
    total_tokens: dict[str, int]
