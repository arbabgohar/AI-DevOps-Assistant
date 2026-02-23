"""
Abstract base class for all ClawOps plugins.

Every infrastructure plugin (Kubernetes, Docker, …) must subclass
BasePlugin and implement the four interface methods below.  The plugin
registry in __init__.py discovers and stores instances by name, giving
the action router and CLI a uniform API regardless of the underlying
platform.

Design notes
------------
- `get_state()` is always read-only and safe to call at any time.
- `analyze()` may call the LLM; it NEVER executes actions.
- `execute_action()` is the only write path; it receives the already-
  validated AllowedAction token and must refuse unknown tokens.
- `validate_permissions()` should be cheap (no side-effects) and is
  called by the action router before every execute_action() call.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BasePlugin(ABC):
    """Uniform interface every platform plugin must satisfy."""

    # ------------------------------------------------------------------ #
    # Identity                                                             #
    # ------------------------------------------------------------------ #

    @property
    @abstractmethod
    def name(self) -> str:
        """Short, lowercase identifier used as the registry key.

        Examples: ``"kubernetes"``, ``"docker"``.
        """

    # ------------------------------------------------------------------ #
    # Read path (safe, no mutations)                                       #
    # ------------------------------------------------------------------ #

    @abstractmethod
    def get_state(self) -> dict[str, Any]:
        """Return a snapshot of the current platform state.

        Must be read-only.  The result is displayed by the CLI and fed
        into the ``analyze()`` prompt as context.

        Returns
        -------
        dict
            Arbitrary key/value snapshot; structure is plugin-specific.
        """

    @abstractmethod
    def analyze(self) -> dict[str, Any]:
        """Inspect the current state and produce a structured diagnosis.

        This method may call the LLM.  It must NOT execute any mutations.
        The return value is plugin-specific but should at minimum include
        ``"issues"`` (list) and ``"recommendations"`` (list) keys.

        Returns
        -------
        dict
            Structured analysis result.
        """

    # ------------------------------------------------------------------ #
    # Write path (guarded by action_router)                                #
    # ------------------------------------------------------------------ #

    @abstractmethod
    def execute_action(
        self,
        action: str,
        parameters: dict[str, Any],
        *,
        approved: bool,
    ) -> dict[str, Any]:
        """Execute a single pre-validated, pre-approved action.

        Parameters
        ----------
        action:
            Token from ``AllowedAction`` enum (already validated upstream).
        parameters:
            Typed key/value pairs required by the action (e.g. pod name).
        approved:
            Must be ``True`` or the method must raise ``PermissionError``.
            This flag is set by the action router only after the approval
            gate has been satisfied.

        Returns
        -------
        dict
            Execution result including ``"success"`` (bool) and
            ``"message"`` (str) keys.

        Raises
        ------
        PermissionError
            If ``approved`` is ``False`` or RBAC check fails.
        ValueError
            If ``action`` is not supported by this plugin.
        """

    @abstractmethod
    def validate_permissions(self) -> dict[str, bool]:
        """Check whether the current credentials allow required operations.

        Returns
        -------
        dict[str, bool]
            Mapping of ``"<verb>:<resource>"`` → ``allowed``.
            The action router calls this before every ``execute_action()``.
        """
