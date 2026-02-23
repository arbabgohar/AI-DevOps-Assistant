"""
Guarded execution layer (action router) for ClawOps.

This module is the single choke-point between an LLM-generated
recommendation and any real infrastructure mutation.  Nothing in the
system executes a side-effect without passing through here first.

Security guarantees
-------------------
1. **Allowlist enforcement** – only actions enumerated in ``ALLOWLIST``
   can ever be dispatched.  The set is a hard-coded constant; it cannot
   be extended at runtime via config files or LLM output.

2. **Approval gate** – every call must supply ``approved=True``.  The
   router refuses execution and returns a structured error if it is absent
   or ``False``.  In practice, the CLI prompts the operator; the API
   endpoint requires an explicit ``"approve": true`` field in the request
   body.

3. **Audit logging** – every routing attempt (success, rejection, or
   error) is appended to ``audit.log`` with a timestamp, the action
   token, the parameters hash, and the outcome.  The audit log is append-
   only from the application's perspective.

4. **RBAC pre-check** – before dispatching to a plugin, the router calls
   ``plugin.validate_permissions()``.  If any required permission is
   missing, execution is aborted and the deficit is recorded in the audit
   log.

5. **No eval / no subprocess** – this module never calls ``eval()``,
   ``exec()``, ``subprocess``, or ``os.system()``.  Platform side-effects
   are exclusively delegated to plugin methods.
"""

from __future__ import annotations

import hashlib
import json
import logging
import logging.handlers
import os
from datetime import datetime, timezone
from typing import Any

from schemas.llm_response import AllowedAction, LLMAnalysisResponse
from plugins import registry

# --------------------------------------------------------------------------- #
# Audit logger                                                                 #
# --------------------------------------------------------------------------- #

_AUDIT_LOG_PATH = os.getenv("CLAWOPS_AUDIT_LOG", "audit.log")

_audit_logger = logging.getLogger("clawops.audit")
if not _audit_logger.handlers:
    _handler = logging.FileHandler(_AUDIT_LOG_PATH, encoding="utf-8")
    _handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    _audit_logger.addHandler(_handler)
    _audit_logger.setLevel(logging.INFO)
    _audit_logger.propagate = False  # Keep audit records out of the root logger

# Structured application logger (goes to stdout / root handler).
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Allowlist                                                                    #
# --------------------------------------------------------------------------- #

# This is the single source of truth for executable operations.
# Changing it requires a deliberate code edit and re-deploy – not a config
# change or an LLM prompt.
ALLOWLIST: frozenset[str] = frozenset(
    {
        AllowedAction.RESTART_POD.value,
        AllowedAction.RESTART_CONTAINER.value,
        # AllowedAction.NO_ACTION is intentionally absent – it is a
        # sentinel that means "do nothing" and must never be dispatched.
    }
)

# Mapping from AllowedAction tokens to the plugin name that handles them.
_ACTION_PLUGIN_MAP: dict[str, str] = {
    AllowedAction.RESTART_POD.value: "kubernetes",
    AllowedAction.RESTART_CONTAINER.value: "docker",
}


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #


class ActionRouterError(Exception):
    """Raised when the router refuses to dispatch an action."""


def route_action(
    analysis: LLMAnalysisResponse,
    *,
    approved: bool,
    plugin_kwargs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate, approve, and dispatch a single action from an LLM analysis.

    Parameters
    ----------
    analysis:
        A fully-validated ``LLMAnalysisResponse`` object produced by the
        structured LLM chain.  Raw text is never accepted here.
    approved:
        Explicit operator approval flag.  Must be ``True`` for any
        destructive action to proceed.
    plugin_kwargs:
        Optional constructor kwargs forwarded to the plugin (e.g.
        ``namespace``, ``kubeconfig_path``).

    Returns
    -------
    dict
        ``{"success": bool, "message": str, "action": str, "parameters": dict}``

    Raises
    ------
    ActionRouterError
        For allowlist violations, missing approval, RBAC failures, or
        plugin initialisation errors.  The exception message is audit-logged
        before being raised.
    """
    action_token = analysis.suggested_action.action.value
    parameters = analysis.suggested_action.parameters
    param_hash = _hash_parameters(parameters)

    _audit_logger.info(
        "ATTEMPT | action=%s | params_sha256=%s | approved=%s",
        action_token,
        param_hash,
        approved,
    )

    # ---- Gate 1: allowlist check ----------------------------------------- #
    if action_token not in ALLOWLIST:
        msg = (
            f"Action '{action_token}' is not in the execution allowlist. "
            f"Allowed actions: {sorted(ALLOWLIST)}"
        )
        _audit_logger.warning("DENIED (allowlist) | action=%s", action_token)
        raise ActionRouterError(msg)

    # ---- Gate 2: explicit approval --------------------------------------- #
    if not approved:
        msg = (
            f"Action '{action_token}' requires explicit operator approval. "
            "Pass approved=True after reviewing the suggested action."
        )
        _audit_logger.warning("DENIED (no approval) | action=%s", action_token)
        raise ActionRouterError(msg)

    # ---- Gate 3: resolve plugin ------------------------------------------ #
    plugin_name = _ACTION_PLUGIN_MAP.get(action_token)
    if not plugin_name:
        msg = f"No plugin mapped to action '{action_token}'."
        _audit_logger.error("ERROR (no plugin map) | action=%s", action_token)
        raise ActionRouterError(msg)

    if plugin_name not in registry:
        msg = (
            f"Plugin '{plugin_name}' required for action '{action_token}' "
            "is not registered.  Check plugin availability."
        )
        _audit_logger.error(
            "ERROR (plugin not registered) | action=%s | plugin=%s",
            action_token,
            plugin_name,
        )
        raise ActionRouterError(msg)

    try:
        plugin = registry.get(plugin_name, **(plugin_kwargs or {}))
    except Exception as exc:
        msg = f"Failed to initialise plugin '{plugin_name}': {exc}"
        _audit_logger.error(
            "ERROR (plugin init) | action=%s | plugin=%s | error=%s",
            action_token,
            plugin_name,
            exc,
        )
        raise ActionRouterError(msg) from exc

    # ---- Gate 4: RBAC pre-check ------------------------------------------ #
    try:
        permissions = plugin.validate_permissions()
    except Exception as exc:
        msg = f"Permission check for plugin '{plugin_name}' failed: {exc}"
        _audit_logger.warning(
            "WARN (permission check error) | plugin=%s | error=%s",
            plugin_name,
            exc,
        )
        # Treat permission check failure as a hard block.
        raise ActionRouterError(msg) from exc

    denied = [k for k, v in permissions.items() if not v]
    if denied:
        msg = (
            f"Insufficient permissions for plugin '{plugin_name}'. "
            f"Missing: {denied}. Aborting."
        )
        _audit_logger.warning(
            "DENIED (rbac) | action=%s | plugin=%s | missing=%s",
            action_token,
            plugin_name,
            denied,
        )
        raise ActionRouterError(msg)

    # ---- Dispatch --------------------------------------------------------- #
    try:
        result = plugin.execute_action(
            action=action_token,
            parameters=parameters,
            approved=approved,
        )
    except PermissionError as exc:
        _audit_logger.error(
            "DENIED (permission error in plugin) | action=%s | error=%s",
            action_token,
            exc,
        )
        raise ActionRouterError(str(exc)) from exc
    except Exception as exc:
        _audit_logger.error(
            "ERROR (execution) | action=%s | error=%s",
            action_token,
            exc,
        )
        raise ActionRouterError(
            f"Plugin raised an unexpected error: {exc}"
        ) from exc

    outcome = "SUCCESS" if result.get("success") else "FAILURE"
    _audit_logger.info(
        "%s | action=%s | params_sha256=%s | message=%s",
        outcome,
        action_token,
        param_hash,
        result.get("message", ""),
    )
    logger.info(
        "Action '%s' executed. success=%s message=%s",
        action_token,
        result.get("success"),
        result.get("message", ""),
    )

    return {
        "success": result.get("success", False),
        "message": result.get("message", ""),
        "action": action_token,
        "parameters": parameters,
    }


def dry_run(analysis: LLMAnalysisResponse) -> dict[str, Any]:
    """Return what *would* happen without executing anything.

    Useful for previewing an action in the CLI or in tests.

    Parameters
    ----------
    analysis:
        A validated ``LLMAnalysisResponse``.

    Returns
    -------
    dict
        Human-readable preview of the routing decision.
    """
    action_token = analysis.suggested_action.action.value
    in_allowlist = action_token in ALLOWLIST
    plugin_name = _ACTION_PLUGIN_MAP.get(action_token, "(none)")

    return {
        "dry_run": True,
        "action": action_token,
        "parameters": analysis.suggested_action.parameters,
        "in_allowlist": in_allowlist,
        "plugin": plugin_name,
        "issue_summary": analysis.issue_summary,
        "probable_cause": analysis.probable_cause,
        "would_execute": in_allowlist and plugin_name in registry,
    }


# --------------------------------------------------------------------------- #
# Internal helpers                                                             #
# --------------------------------------------------------------------------- #


def _hash_parameters(parameters: dict[str, Any]) -> str:
    """Return a SHA-256 hex digest of the JSON-serialised parameters.

    Logged in the audit trail to allow correlation without storing raw
    potentially-sensitive values (pod names, namespaces, etc.) in plain
    text in a world-readable log file.
    """
    serialised = json.dumps(parameters, sort_keys=True, default=str).encode()
    return hashlib.sha256(serialised).hexdigest()[:16]
