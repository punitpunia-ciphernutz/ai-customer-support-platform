"""Deterministic support confidence scoring — delegates to Day 4 confidence service."""

from __future__ import annotations

from app.modules.ai.application.confidence_service import (
    calculate_confidence_breakdown,
    calculate_support_confidence as _calculate_final,
)
from app.modules.ai.domain.models import AIConfig
from app.modules.ai.domain.schemas import ConfidenceBreakdown, SupportAgentState

__all__ = ["calculate_confidence_breakdown", "calculate_support_confidence"]


def calculate_support_confidence(
    state: SupportAgentState,
    config: AIConfig | None = None,
) -> float:
    return _calculate_final(state, config)
