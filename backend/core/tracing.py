"""
backend/core/tracing.py

Central LangSmith tracing configuration for GTM Intelligence.

Usage:

from backend.core.tracing import (
    traceable,
    trace_run,
    add_metadata
)

@traceable(name="planner")
def planner(state):
    return plan


with trace_run(
    name="groq_call",
    metadata={
        "provider": "groq",
        "model": "llama-3.3-70b-versatile"
    }
) as run:

    response = llm.invoke(prompt)

    add_metadata(
        run,
        {
            "latency_seconds": 0.42
        }
    )
"""

import os
from contextlib import contextmanager
from typing import Any, Optional

from langsmith import Client
from langsmith.run_helpers import traceable
from langsmith import trace


# =====================================================
# Environment
# =====================================================

LANGCHAIN_API_KEY = os.getenv(
    "LANGCHAIN_API_KEY"
)

LANGCHAIN_PROJECT = os.getenv(
    "LANGCHAIN_PROJECT",
    "gtm-intelligence"
)


# =====================================================
# Client initialization
# =====================================================

client: Optional[Client] = None

if LANGCHAIN_API_KEY:

    client = Client(
        api_key=LANGCHAIN_API_KEY
    )


# =====================================================
# Manual trace helper
# =====================================================

@contextmanager
def trace_run(
    name: str,
    metadata: dict[str, Any] | None = None,
):
    """
    Manual trace block.

    Example:

    with trace_run(
        "groq_call",
        metadata={
            "provider":"groq",
            "model":"llama-3.3-70b-versatile"
        }
    ):
        response = llm.invoke(...)
    """

    with trace(
        name=name,
        project_name=LANGCHAIN_PROJECT
    ) as run:

        if metadata:

            existing = getattr(
                run,
                "metadata",
                {}
            )

            run.metadata = {
                **existing,
                **metadata
            }

        yield run


# =====================================================
# Metadata updater
# =====================================================

def add_metadata(
    run: Any,
    metadata: dict[str, Any],
) -> None:
    """
    Safely merge metadata.

    Example:

    add_metadata(
        run,
        {
            "latency_seconds": 1.3,
            "confidence": 0.74,
            "results_count": 8
        }
    )
    """

    if not run:
        return

    existing = getattr(
        run,
        "metadata",
        {}
    )

    run.metadata = {
        **existing,
        **metadata
    }


# =====================================================
# Convenience helper
# =====================================================

def tracing_enabled() -> bool:

    return (
        client is not None
    )


# =====================================================
# Exports
# =====================================================

__all__ = [
    "client",
    "traceable",
    "trace_run",
    "add_metadata",
    "tracing_enabled",
]