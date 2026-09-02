"""In-process context for nested automation execution."""

from __future__ import annotations

import contextvars

automation_execution_depth: contextvars.ContextVar[int] = contextvars.ContextVar(
    "automation_execution_depth",
    default=0,
)
