"""Estimated LLM cost from token usage."""

from __future__ import annotations

from decimal import Decimal

# USD per 1M tokens (approximate dev pricing)
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "gemini-3.1-flash-lite": (0.10, 0.40),
    "echo-heuristic": (0.0, 0.0),
    "default": (0.15, 0.60),
}


def estimate_cost_usd(model: str | None, token_usage: dict | None) -> float:
    if not token_usage:
        return 0.0
    input_tokens = int(token_usage.get("input_tokens") or token_usage.get("prompt_tokens") or 0)
    output_tokens = int(token_usage.get("output_tokens") or token_usage.get("completion_tokens") or 0)
    key = model if model in MODEL_PRICING else "default"
    in_price, out_price = MODEL_PRICING[key]
    cost = (input_tokens * in_price + output_tokens * out_price) / 1_000_000
    return float(Decimal(str(cost)).quantize(Decimal("0.000001")))
