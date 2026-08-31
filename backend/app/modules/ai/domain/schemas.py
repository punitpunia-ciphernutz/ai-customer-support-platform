from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.modules.ai.domain.models import AIMode, AIRunStatus, AIRunType


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


class AIClassification(BaseModel):
    intent: IntentLabel
    language: str = Field(default="en", min_length=2, max_length=16)
    sentiment: str = Field(default="neutral")
    confidence: float = Field(ge=0.0, le=1.0)
    requires_human: bool = False


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


class SupportAgentState(BaseModel):
    conversation_id: str | None = None
    message_id: str | None = None
    organization_id: str | None = None
    customer_context: CustomerContext | None = None
    conversation_history: list[ConversationTurn] = Field(default_factory=list)
    user_message: str = ""
    intent: IntentLabel | None = None
    intent_confidence: float = 0.0
    retrieved_documents: list[RetrievedDocument] = Field(default_factory=list)
    retrieval_score: float = 0.0
    draft_response: str = ""
    grounded: bool = False
    citations: list[Citation] = Field(default_factory=list)
    support_confidence: float = 0.0
    sentiment: str = "neutral"
    escalation_required: bool = False
    escalation_reason: str | None = None
    escalation_summary: str | None = None
    decision: AgentDecision | None = None
    final_response: str | None = None
    human_requested: bool = False

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


class AIConfigOut(BaseModel):
    enabled: bool
    mode: AIMode
    auto_reply_threshold: float
    escalation_threshold: float
    allowed_intents: list[str] | None = None
    restricted_intents: list[str] | None = None
    intent_team_map: dict[str, str] | None = None

    model_config = {"from_attributes": True}


class AIConfigUpdate(BaseModel):
    enabled: bool | None = None
    mode: AIMode | None = None
    auto_reply_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    escalation_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    allowed_intents: list[str] | None = None
    restricted_intents: list[str] | None = None
    intent_team_map: dict[str, str] | None = None


class AIRunSummary(BaseModel):
    id: str
    conversation_id: str | None
    message_id: str | None
    type: AIRunType
    status: AIRunStatus
    model: str | None
    graph_version: str | None
    intent: str | None
    retrieval_count: int | None
    confidence: float | None
    latency_ms: int | None
    error: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AIRunDetail(AIRunSummary):
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] | None = None
    token_usage: dict[str, Any] | None = None

    model_config = {"from_attributes": True}
