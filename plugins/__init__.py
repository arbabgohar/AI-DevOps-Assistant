"""
Plugin registry for ClawOps.

Plugins are registered by name and retrieved by the action router and CLI.
Registration is lazy – a plugin's constructor is only called when first
accessed, so missing optional dependencies (kubernetes, docker) do not
crash the startup of unrelated features.

Usage
-----
    from plugins import registry

    # Register a plugin class (not an instance)
    registry.register(KubernetesPlugin)

    # Retrieve an instance (constructed on first access with kwargs)
    k8s = registry.get("kubernetes", namespace="kube-system")

    # List registered plugin names
    print(registry.names())  # ["kubernetes", "docker"]
"""

from __future__ import annotations

import logging
from typing import Any, Type

from plugins.base_plugin import BasePlugin

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Thread-safe registry that maps plugin names to their classes.

    Instances are NOT cached – callers receive a fresh instance each time
    ``get()`` is called, constructed with the supplied kwargs.  This
    keeps configuration concerns (namespace, kubeconfig path, …) local to
    the call site.
    """

    def __init__(self) -> None:
        self._classes: dict[str, Type[BasePlugin]] = {}

    def register(self, plugin_class: Type[BasePlugin]) -> None:
        """Register a plugin class.

        Parameters
        ----------
        plugin_class:
            A concrete subclass of BasePlugin.  Its ``name`` property
            (accessed on a temporary instance-less basis via the class)
            is used as the registry key.

        Raises
        ------
        TypeError
            If ``plugin_class`` is not a subclass of BasePlugin.
        """
        if not (isinstance(plugin_class, type) and issubclass(plugin_class, BasePlugin)):
            raise TypeError(
                f"{plugin_class!r} is not a subclass of BasePlugin."
            )
        # Retrieve name via a class-level call (name is a property backed
        # by an abstract method; we need an instance to read it, so we
        # derive the name from the class attribute set by the subclass).
        # Convention: the name is defined as a property that returns a
        # string literal, so we instantiate temporarily via a sentinel or
        # we read it from the docstring convention.  Instead, we just rely
        # on the class defining ``_plugin_name`` as a fallback.
        # To avoid dual-maintenance, call the property on a minimal
        # instantiation placeholder if possible, otherwise use the class
        # name lowercased.
        name = getattr(plugin_class, "_plugin_name", None) or plugin_class.__name__.lower().replace("plugin", "")
        self._classes[name] = plugin_class
        logger.debug("Registered plugin '%s' → %s", name, plugin_class.__name__)

    def register_named(self, name: str, plugin_class: Type[BasePlugin]) -> None:
        """Register a plugin class with an explicit name override.

        Parameters
        ----------
        name:
            Registry key (e.g. ``"kubernetes"``).
        plugin_class:
            A concrete subclass of BasePlugin.
        """
        if not (isinstance(plugin_class, type) and issubclass(plugin_class, BasePlugin)):
            raise TypeError(
                f"{plugin_class!r} is not a subclass of BasePlugin."
            )
        self._classes[name] = plugin_class
        logger.debug("Registered plugin '%s' → %s", name, plugin_class.__name__)

    def get(self, name: str, **kwargs: Any) -> BasePlugin:
        """Instantiate and return the plugin registered under *name*.

        Parameters
        ----------
        name:
            Registry key.
        **kwargs:
            Constructor arguments forwarded to the plugin class.

        Returns
        -------
        BasePlugin
            A fresh plugin instance.

        Raises
        ------
        KeyError
            If no plugin is registered under *name*.
        RuntimeError
            If the plugin's constructor raises (e.g. missing dependency).
        """
        if name not in self._classes:
            available = ", ".join(self._classes) or "(none)"
            raise KeyError(
                f"No plugin registered as '{name}'. Available: {available}"
            )
        plugin_class = self._classes[name]
        try:
            return plugin_class(**kwargs)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to initialise plugin '{name}': {exc}"
            ) from exc

    def names(self) -> list[str]:
        """Return the sorted list of registered plugin names."""
        return sorted(self._classes)

    def __contains__(self, name: str) -> bool:
        return name in self._classes


# --------------------------------------------------------------------------- #
# Singleton registry                                                           #
# --------------------------------------------------------------------------- #

registry = PluginRegistry()

# Register built-in plugins.  Each import is guarded so that a missing
# optional dependency (kubernetes, docker) only disables that specific
# plugin rather than crashing the whole application.

try:
    from plugins.k8s_plugin import KubernetesPlugin

    registry.register_named("kubernetes", KubernetesPlugin)
except Exception as _exc:  # noqa: BLE001
    logger.warning("Kubernetes plugin unavailable: %s", _exc)

try:
    from plugins.docker_plugin import DockerPlugin

    registry.register_named("docker", DockerPlugin)
except Exception as _exc:  # noqa: BLE001
    logger.warning("Docker plugin unavailable: %s", _exc)


__all__ = ["BasePlugin", "PluginRegistry", "registry"]
