from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


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
