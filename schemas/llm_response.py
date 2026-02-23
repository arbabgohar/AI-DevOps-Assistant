"""
Pydantic schemas for LLM structured output.

The LLM is instructed to return JSON that EXACTLY matches LLMAnalysisResponse.
Any response that fails validation is silently rejected by the caller – the
system never acts on unvalidated text.

Security contract
-----------------
- AllowedAction is the single source of truth for executable operations.
- Adding a new action requires an explicit code change here AND in
  action_router.ALLOWLIST – two independent gates.
- 'no_action' is the safe fallback that the LLM should choose whenever
  it is uncertain.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AllowedAction(str, Enum):
    """Enumeration of every action the system is permitted to execute.

    Only values listed here can ever reach the execution layer.
    The LLM is instructed to pick from this set; any other string will
    fail Pydantic validation and be rejected before routing.
    """

    RESTART_POD = "restart_pod"
    RESTART_CONTAINER = "restart_container"
    NO_ACTION = "no_action"  # Safe, explicit do-nothing sentinel


class SuggestedAction(BaseModel):
    """The concrete remediation step the LLM recommends."""

    action: AllowedAction = Field(
        ...,
        description="Machine-readable action token from the AllowedAction enum.",
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Key/value pairs required by the action handler, "
            "e.g. {'namespace': 'default', 'pod': 'web-abc123'}."
        ),
    )


class LLMAnalysisResponse(BaseModel):
    """Top-level structured response returned by the AI analysis chain.

    The entire object must be present and valid before any action is
    considered.  Partial or malformed JSON is rejected outright.
    """

    issue_summary: str = Field(
        ...,
        min_length=1,
        description="One-sentence summary of the detected issue.",
    )
    probable_cause: str = Field(
        ...,
        min_length=1,
        description="Concise explanation of the root cause.",
    )
    suggested_action: SuggestedAction = Field(
        ...,
        description="The single recommended remediation action.",
    )
