"""
Kubernetes plugin for ClawOps.

Provides read and (guarded) write access to a Kubernetes cluster via the
official ``kubernetes`` Python client.  All destructive operations require
``approved=True`` to be passed explicitly by the action router – they are
never invoked directly from LLM output.

RBAC requirements (minimum viable, namespace-scoped)
------------------------------------------------------
The service account or kubeconfig user needs at minimum:

    apiVersion: rbac.authorization.k8s.io/v1
    kind: Role
    rules:
      - apiGroups: [""]
        resources: ["pods"]
        verbs: ["get", "list", "delete"]
      - apiGroups: [""]
        resources: ["pods/log"]
        verbs: ["get"]

    # For permission self-check (validate_permissions):
    apiVersion: rbac.authorization.k8s.io/v1
    kind: ClusterRole
    rules:
      - apiGroups: ["authorization.k8s.io"]
        resources: ["selfsubjectaccessreviews"]
        verbs: ["create"]

Do NOT grant cluster-admin.  Namespace-scope the Role binding.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from plugins.base_plugin import BasePlugin

logger = logging.getLogger(__name__)

# Lazily import kubernetes so that the rest of the app still boots when
# the package is not installed (e.g. in a Docker-only environment).
try:
    from kubernetes import client as k8s_client
    from kubernetes import config as k8s_config
    from kubernetes.client.rest import ApiException

    _K8S_AVAILABLE = True
except ImportError:  # pragma: no cover
    _K8S_AVAILABLE = False
    ApiException = Exception  # type: ignore[assignment,misc]


# Container wait-states that indicate a pod is unhealthy.
_CRASH_REASONS: frozenset[str] = frozenset(
    {
        "CrashLoopBackOff",
        "OOMKilled",
        "Error",
        "ImagePullBackOff",
        "ErrImagePull",
        "CreateContainerConfigError",
    }
)


class KubernetesPlugin(BasePlugin):
    """Interact with a Kubernetes cluster for observation and remediation.

    Parameters
    ----------
    namespace:
        Default namespace for all operations.  Can be overridden per-call.
    kubeconfig_path:
        Explicit path to a kubeconfig file.  If ``None``, the plugin first
        tries the ``KUBECONFIG`` env-var, then ``~/.kube/config``, and
        finally attempts in-cluster configuration (pod service-account).
    """

    def __init__(
        self,
        namespace: str = "default",
        kubeconfig_path: str | None = None,
    ) -> None:
        if not _K8S_AVAILABLE:
            raise RuntimeError(
                "kubernetes package is not installed. "
                "Run: pip install kubernetes"
            )

        self._namespace = namespace
        self._kubeconfig_path = kubeconfig_path or os.getenv("KUBECONFIG")
        self._load_kubeconfig()

    # ------------------------------------------------------------------ #
    # BasePlugin identity                                                  #
    # ------------------------------------------------------------------ #

    @property
    def name(self) -> str:
        return "kubernetes"

    # ------------------------------------------------------------------ #
    # Kubeconfig loading                                                   #
    # ------------------------------------------------------------------ #

    def _load_kubeconfig(self) -> None:
        """Load kubeconfig from file, env-var, or in-cluster service account."""
        try:
            if self._kubeconfig_path:
                k8s_config.load_kube_config(config_file=self._kubeconfig_path)
                logger.info("Loaded kubeconfig from %s", self._kubeconfig_path)
            else:
                try:
                    k8s_config.load_kube_config()
                    logger.info("Loaded default kubeconfig (~/.kube/config)")
                except k8s_config.ConfigException:
                    # Fall back to in-cluster config (running inside a pod).
                    k8s_config.load_incluster_config()
                    logger.info("Loaded in-cluster kubeconfig")
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load Kubernetes configuration: {exc}"
            ) from exc

    # ------------------------------------------------------------------ #
    # Pod listing                                                          #
    # ------------------------------------------------------------------ #

    def get_pods(self, namespace: str | None = None) -> list[dict[str, Any]]:
        """List pods in *namespace* with their phase and container statuses.

        Parameters
        ----------
        namespace:
            Kubernetes namespace.  Defaults to the instance namespace.

        Returns
        -------
        list[dict]
            Each entry contains ``name``, ``phase``, ``ready``, ``restarts``,
            and ``issues`` (list of detected problem strings).
        """
        ns = namespace or self._namespace
        v1 = k8s_client.CoreV1Api()
        try:
            pod_list = v1.list_namespaced_pod(namespace=ns)
        except ApiException as exc:
            logger.error("Failed to list pods in namespace %s: %s", ns, exc)
            raise

        results: list[dict[str, Any]] = []
        for pod in pod_list.items:
            issues = self._detect_pod_issues(pod)
            ready = self._is_pod_ready(pod)
            restart_count = sum(
                (cs.restart_count or 0)
                for cs in (pod.status.container_statuses or [])
            )
            results.append(
                {
                    "name": pod.metadata.name,
                    "namespace": ns,
                    "phase": pod.status.phase,
                    "ready": ready,
                    "restart_count": restart_count,
                    "issues": issues,
                }
            )
        return results

    # ------------------------------------------------------------------ #
    # Log retrieval                                                        #
    # ------------------------------------------------------------------ #

    def get_pod_logs(
        self,
        pod: str,
        namespace: str | None = None,
        tail_lines: int = 200,
        container: str | None = None,
    ) -> str:
        """Fetch recent logs from a pod.

        Parameters
        ----------
        pod:
            Pod name.
        namespace:
            Kubernetes namespace.  Defaults to the instance namespace.
        tail_lines:
            Number of lines to fetch from the tail.
        container:
            Specific container name inside the pod (optional).

        Returns
        -------
        str
            Raw log text.
        """
        ns = namespace or self._namespace
        v1 = k8s_client.CoreV1Api()
        kwargs: dict[str, Any] = {
            "name": pod,
            "namespace": ns,
            "tail_lines": tail_lines,
            "timestamps": True,
        }
        if container:
            kwargs["container"] = container

        try:
            return v1.read_namespaced_pod_log(**kwargs)
        except ApiException as exc:
            logger.error("Failed to read logs for pod %s/%s: %s", ns, pod, exc)
            raise

    # ------------------------------------------------------------------ #
    # Analysis                                                             #
    # ------------------------------------------------------------------ #

    def analyze_pod(
        self, pod: str, namespace: str | None = None
    ) -> dict[str, Any]:
        """Analyse a single pod's health without modifying anything.

        Checks for CrashLoopBackOff, OOMKilled, excessive restarts, and
        other common failure modes.

        Parameters
        ----------
        pod:
            Pod name.
        namespace:
            Kubernetes namespace.

        Returns
        -------
        dict
            ``healthy`` (bool), ``issues`` (list[str]),
            ``recommendations`` (list[str]), ``phase``, ``restart_count``.
        """
        ns = namespace or self._namespace
        v1 = k8s_client.CoreV1Api()

        try:
            pod_obj = v1.read_namespaced_pod(name=pod, namespace=ns)
        except ApiException as exc:
            logger.error("Failed to read pod %s/%s: %s", ns, pod, exc)
            raise

        issues = self._detect_pod_issues(pod_obj)
        restart_count = sum(
            (cs.restart_count or 0)
            for cs in (pod_obj.status.container_statuses or [])
        )

        recommendations: list[str] = []
        if "CrashLoopBackOff" in issues:
            recommendations.append(
                "Pod is crash-looping. Inspect logs and consider restarting "
                "after fixing the underlying application error."
            )
        if "OOMKilled" in issues:
            recommendations.append(
                "Pod was OOM-killed. Increase memory limits or fix a memory leak."
            )
        if restart_count > 5:
            recommendations.append(
                f"Pod has restarted {restart_count} times. Investigate root cause."
            )
        if not issues:
            recommendations.append("Pod appears healthy.")

        return {
            "pod": pod,
            "namespace": ns,
            "phase": pod_obj.status.phase,
            "healthy": len(issues) == 0,
            "restart_count": restart_count,
            "issues": issues,
            "recommendations": recommendations,
        }

    # ------------------------------------------------------------------ #
    # Remediation (write path – requires approved=True)                   #
    # ------------------------------------------------------------------ #

    def restart_pod(
        self,
        pod: str,
        namespace: str | None = None,
        *,
        approved: bool = False,
    ) -> dict[str, Any]:
        """Delete a pod so its controller recreates it.

        This is safe only for pods managed by a Deployment, ReplicaSet,
        StatefulSet, or DaemonSet.  Bare pods will NOT be recreated.

        Parameters
        ----------
        pod:
            Pod name.
        namespace:
            Kubernetes namespace.
        approved:
            Must be ``True`` or the call is rejected.  The action router
            sets this flag after the approval gate has been satisfied.

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
                "restart_pod requires explicit approval (approved=True)."
            )

        ns = namespace or self._namespace
        v1 = k8s_client.CoreV1Api()
        try:
            v1.delete_namespaced_pod(name=pod, namespace=ns)
            logger.info("Deleted pod %s/%s – controller will recreate it.", ns, pod)
            return {
                "success": True,
                "message": f"Pod '{pod}' deleted from namespace '{ns}'. "
                "The owning controller will recreate it.",
            }
        except ApiException as exc:
            logger.error("Failed to delete pod %s/%s: %s", ns, pod, exc)
            return {"success": False, "message": str(exc)}

    # ------------------------------------------------------------------ #
    # BasePlugin interface implementation                                  #
    # ------------------------------------------------------------------ #

    def get_state(self) -> dict[str, Any]:
        """Return a snapshot of all pods in the default namespace."""
        return {
            "namespace": self._namespace,
            "pods": self.get_pods(self._namespace),
        }

    def analyze(self) -> dict[str, Any]:
        """Analyse every pod in the default namespace for health issues."""
        pods = self.get_pods(self._namespace)
        pod_analyses = [
            self.analyze_pod(pod["name"], self._namespace) for pod in pods
        ]
        unhealthy = [a for a in pod_analyses if not a["healthy"]]
        return {
            "namespace": self._namespace,
            "total_pods": len(pods),
            "unhealthy_pods": len(unhealthy),
            "analyses": pod_analyses,
        }

    def execute_action(
        self,
        action: str,
        parameters: dict[str, Any],
        *,
        approved: bool,
    ) -> dict[str, Any]:
        """Route validated actions to the correct handler.

        Only ``restart_pod`` is currently supported.
        """
        if action == "restart_pod":
            pod = parameters.get("pod")
            namespace = parameters.get("namespace", self._namespace)
            if not pod:
                raise ValueError("'pod' is required in parameters for restart_pod.")
            return self.restart_pod(pod=pod, namespace=namespace, approved=approved)

        raise ValueError(
            f"KubernetesPlugin does not support action '{action}'. "
            "Supported: restart_pod"
        )

    def validate_permissions(self) -> dict[str, bool]:
        """Use SelfSubjectAccessReview to probe required RBAC permissions.

        Checks: list pods, get pods, delete pods (for restart), get pod logs.
        Returns a mapping of ``"<verb>:<resource>"`` → ``allowed``.
        """
        auth_api = k8s_client.AuthorizationV1Api()

        checks: list[tuple[str, str]] = [
            ("list", "pods"),
            ("get", "pods"),
            ("delete", "pods"),
            ("get", "pods/log"),
        ]

        permissions: dict[str, bool] = {}
        for verb, resource in checks:
            key = f"{verb}:{resource}"
            try:
                sar = k8s_client.V1SelfSubjectAccessReview(
                    spec=k8s_client.V1SelfSubjectAccessReviewSpec(
                        resource_attributes=k8s_client.V1ResourceAttributes(
                            namespace=self._namespace,
                            resource=resource,
                            verb=verb,
                        )
                    )
                )
                result = auth_api.create_self_subject_access_review(sar)
                permissions[key] = bool(result.status.allowed)
            except ApiException as exc:
                logger.warning("Permission check failed for %s: %s", key, exc)
                permissions[key] = False

        missing = [k for k, v in permissions.items() if not v]
        if missing:
            logger.warning(
                "Insufficient Kubernetes permissions: %s", ", ".join(missing)
            )

        return permissions

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _detect_pod_issues(pod: Any) -> list[str]:
        """Inspect a V1Pod object and return a list of detected problem strings."""
        issues: list[str] = []

        for cs in pod.status.container_statuses or []:
            # Waiting state (CrashLoopBackOff, ImagePullBackOff, …)
            if cs.state and cs.state.waiting:
                reason = cs.state.waiting.reason or ""
                if reason in _CRASH_REASONS:
                    issues.append(reason)

            # Terminated with non-zero exit code
            if cs.state and cs.state.terminated:
                term = cs.state.terminated
                if term.exit_code and term.exit_code != 0:
                    reason = term.reason or f"ExitCode={term.exit_code}"
                    if reason not in issues:
                        issues.append(reason)

            # High restart count is a smell even without a current crash
            if (cs.restart_count or 0) > 5:
                tag = f"HighRestarts({cs.name}={cs.restart_count})"
                if tag not in issues:
                    issues.append(tag)

        if pod.status.phase in {"Failed", "Unknown"}:
            tag = f"Phase={pod.status.phase}"
            if tag not in issues:
                issues.append(tag)

        return issues

    @staticmethod
    def _is_pod_ready(pod: Any) -> bool:
        """Return True if all containers in the pod report Ready."""
        for condition in pod.status.conditions or []:
            if condition.type == "Ready":
                return condition.status == "True"
        return False
