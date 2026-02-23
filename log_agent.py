"""
LLM analysis chains for ClawOps.

Provides two analysis modes:

1. ``analyze_log(log_text)``   – free-form text response (existing behaviour,
                                  untouched for backwards compatibility).

2. ``analyze_log_structured(log_text)`` – returns a validated
   ``LLMAnalysisResponse`` Pydantic model, or ``None`` if the LLM output
   fails schema validation.  The action router only accepts the latter;
   free-form text NEVER reaches the execution layer.
"""

from __future__ import annotations

import json
import logging
import re
import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from pydantic import ValidationError

load_dotenv()

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Shared LLM instance                                                         #
# --------------------------------------------------------------------------- #

_llm = ChatOpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    model="gpt-4o-mini",
    temperature=0,
)

# --------------------------------------------------------------------------- #
# Chain 1 – Free-form analysis (original, unchanged)                          #
# --------------------------------------------------------------------------- #

_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        (
            "You are a senior DevOps engineer. "
            "Analyze the provided system log and give concise, actionable recommendations. "
            "Identify errors, warnings, and performance issues. "
            "Format your response with clear sections: Summary, Issues Found, and Recommended Actions."
        ),
    ),
    ("human", "{log_text}"),
])

_chain = _prompt | _llm

# --------------------------------------------------------------------------- #
# Chain 2 – Structured JSON analysis                                          #
# --------------------------------------------------------------------------- #

_ALLOWED_ACTIONS = '["restart_pod", "restart_container", "no_action"]'

_structured_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        (
            "You are a senior DevOps engineer AI assistant.\n"
            "Analyze the provided system log and respond with ONLY a JSON object "
            "that matches this exact schema (no markdown fences, no extra text):\n\n"
            "{\n"
            '  "issue_summary": "<one-sentence summary of the main issue>",\n'
            '  "probable_cause": "<concise root-cause explanation>",\n'
            '  "suggested_action": {\n'
            f'    "action": <one of {_ALLOWED_ACTIONS}>,\n'
            '    "parameters": {<key-value pairs needed by the action, e.g. "pod", "namespace">}\n'
            "  }\n"
            "}\n\n"
            "Rules:\n"
            "- Choose 'no_action' when you are uncertain or no remediation is needed.\n"
            "- For 'restart_pod', include 'pod' and 'namespace' in parameters.\n"
            "- For 'restart_container', include 'container' in parameters.\n"
            "- Output ONLY the JSON object. No commentary, no markdown."
        ),
    ),
    ("human", "{log_text}"),
])

_structured_chain = _structured_prompt | _llm


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #


def analyze_log(log_text: str) -> str:
    """Analyze log text and return a free-form recommendation string.

    This is the original analysis function.  Its output is displayed to
    the user but NEVER passed to the action router.

    Args:
        log_text: The log text to analyze.

    Returns:
        AI's recommendations as a plain string.

    Raises:
        Exception: Propagates any LLM or network errors to the caller.
    """
    response = _chain.invoke({"log_text": log_text})
    return response.content


def analyze_log_structured(log_text: str) -> "LLMAnalysisResponse | None":
    """Analyze log text and return a validated, structured LLM response.

    The LLM is instructed to output a strict JSON object.  The raw text is
    parsed, then validated against ``LLMAnalysisResponse``.  If either step
    fails the function returns ``None`` – callers must never act on a ``None``
    result.

    Args:
        log_text: The log text to analyze.

    Returns:
        A validated ``LLMAnalysisResponse`` on success, or ``None`` if the
        LLM output cannot be parsed or fails schema validation.
    """
    # Import here to avoid a circular dependency at module load time when
    # schemas imports log_agent (which it currently does not, but guard anyway).
    from schemas.llm_response import LLMAnalysisResponse

    try:
        response = _structured_chain.invoke({"log_text": log_text})
        raw: str = response.content.strip()
    except Exception as exc:
        logger.error("LLM invocation failed in structured analysis: %s", exc)
        return None

    # Strip optional markdown code fences that some model versions add.
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    raw = raw.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning(
            "LLM structured output is not valid JSON. "
            "Rejecting safely.  Error: %s  Raw output (first 300 chars): %s",
            exc,
            raw[:300],
        )
        return None

    try:
        return LLMAnalysisResponse(**data)
    except ValidationError as exc:
        logger.warning(
            "LLM JSON output failed Pydantic validation. "
            "Rejecting safely.  Errors: %s",
            exc.errors(),
        )
        return None
