"""
Docker plugin for ClawOps.

Provides read access to a local Docker daemon and guarded container
restart capability.  Uses the official ``docker`` Python SDK; falls back
gracefully if the SDK is not installed or if the Docker daemon is not
reachable.

Supported actions
-----------------
- ``restart_container`` – restart a named/ID'd container (requires
  ``approved=True`` from the action router).

RBAC / security notes
---------------------
- The user running ClawOps must belong to the ``docker`` UNIX group or be
  root (Linux) / have Docker Desktop permissions (macOS/Windows).
- The plugin performs NO exec into containers and NO image builds.
- Container names accepted at the CLI are validated against the live
  container list before any action is executed.
"""

from __future__ import annotations

import logging
from typing import Any

from plugins.base_plugin import BasePlugin

logger = logging.getLogger(__name__)

try:
    import docker
    from docker.errors import DockerException, NotFound, APIError

    _DOCKER_AVAILABLE = True
except ImportError:  # pragma: no cover
    _DOCKER_AVAILABLE = False
    DockerException = Exception  # type: ignore[assignment,misc]
    NotFound = Exception  # type: ignore[assignment,misc]
    APIError = Exception  # type: ignore[assignment,misc]


class DockerPlugin(BasePlugin):
    """Inspect and selectively remediate Docker containers.

    Parameters
    ----------
    base_url:
        Docker daemon socket URL.  Defaults to the platform default
        (``unix:///var/run/docker.sock`` on Linux/macOS,
        ``npipe:////./pipe/docker_engine`` on Windows).
    """

    def __init__(self, base_url: str | None = None) -> None:
        if not _DOCKER_AVAILABLE:
            raise RuntimeError(
                "docker package is not installed. "
                "Run: pip install docker"
            )
        try:
            self._client = (
                docker.DockerClient(base_url=base_url)
                if base_url
                else docker.from_env()
            )
            self._client.ping()
            logger.info("Docker daemon reachable.")
        except DockerException as exc:
            raise RuntimeError(
                f"Cannot connect to Docker daemon: {exc}"
            ) from exc

    # ------------------------------------------------------------------ #
    # BasePlugin identity                                                  #
    # ------------------------------------------------------------------ #

    @property
    def name(self) -> str:
        return "docker"

    # ------------------------------------------------------------------ #
    # Read path                                                            #
    # ------------------------------------------------------------------ #

    def get_state(self) -> dict[str, Any]:
        """Return a list of all containers with status and health info."""
        containers = self._client.containers.list(all=True)
        return {
            "containers": [self._container_summary(c) for c in containers],
            "total": len(containers),
        }

    def analyze(self) -> dict[str, Any]:
        """Identify unhealthy, exited, or restarting containers."""
        state = self.get_state()
        containers = state["containers"]

        unhealthy = [
            c for c in containers
            if c["status"] in {"exited", "dead"}
            or c.get("health") in {"unhealthy", "starting"}
        ]

        issues: list[str] = []
        recommendations: list[str] = []

        for c in unhealthy:
            issues.append(
                f"Container '{c['name']}' is in state '{c['status']}'"
                + (f" (health: {c['health']})" if c.get("health") else "")
            )
            recommendations.append(
                f"Consider restarting container '{c['name']}' "
                "after investigating logs."
            )

        if not issues:
            recommendations.append("All containers appear healthy.")

        return {
            "total_containers": len(containers),
            "unhealthy_count": len(unhealthy),
            "issues": issues,
            "recommendations": recommendations,
            "containers": containers,
        }

    # ------------------------------------------------------------------ #
    # Write path                                                           #
    # ------------------------------------------------------------------ #

    def execute_action(
        self,
        action: str,
        parameters: dict[str, Any],
        *,
        approved: bool,
    ) -> dict[str, Any]:
        """Route validated actions to the correct handler.

        Only ``restart_container`` is currently supported.
        """
        if action == "restart_container":
            container_id = parameters.get("container") or parameters.get("name")
            if not container_id:
                raise ValueError(
                    "'container' (name or ID) is required for restart_container."
                )
            return self.restart_container(container=container_id, approved=approved)

        raise ValueError(
            f"DockerPlugin does not support action '{action}'. "
            "Supported: restart_container"
        )

    def restart_container(
        self,
        container: str,
        *,
        approved: bool = False,
    ) -> dict[str, Any]:
        """Restart a Docker container by name or ID.

        Parameters
        ----------
        container:
            Container name or short/long ID.
        approved:
            Must be ``True`` or the call is rejected.

        Returns
        -------
        dict
            ``success`` (bool) and ``message`` (str).

        Raises
        ------
        PermissionError
            If ``approved`` is ``False``.
        """
        if not approved:
            raise PermissionError(
                "restart_container requires explicit approval (approved=True)."
            )

        try:
            c = self._client.containers.get(container)
            c.restart()
            logger.info("Restarted Docker container '%s'.", container)
            return {
                "success": True,
                "message": f"Container '{container}' restarted successfully.",
            }
        except NotFound:
            return {
                "success": False,
                "message": f"Container '{container}' not found.",
            }
        except APIError as exc:
            logger.error("Failed to restart container '%s': %s", container, exc)
            return {"success": False, "message": str(exc)}

    # ------------------------------------------------------------------ #
    # Permissions                                                          #
    # ------------------------------------------------------------------ #

    def validate_permissions(self) -> dict[str, bool]:
        """Verify Docker daemon connectivity and basic API access.

        Returns
        -------
        dict[str, bool]
            ``ping`` and ``list_containers`` permission flags.
        """
        perms: dict[str, bool] = {}
        try:
            self._client.ping()
            perms["ping"] = True
        except DockerException:
            perms["ping"] = False

        try:
            self._client.containers.list(all=True, limit=1)
            perms["list_containers"] = True
        except DockerException:
            perms["list_containers"] = False

        return perms

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _container_summary(container: Any) -> dict[str, Any]:
        """Extract relevant fields from a docker Container object."""
        health: str | None = None
        if hasattr(container, "attrs"):
            health_info = (
                container.attrs.get("State", {}).get("Health", {})
            )
            if health_info:
                health = health_info.get("Status")

        return {
            "id": container.short_id,
            "name": container.name,
            "image": (
                container.image.tags[0]
                if container.image.tags
                else container.image.short_id
            ),
            "status": container.status,
            "health": health,
        }
