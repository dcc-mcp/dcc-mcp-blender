"""Blender integration for ``dcc_mcp_core.register_project_tools``.

Ports :mod:`dcc_mcp_maya._project_tools` to Blender.  Wires the four
project-persistence MCP/REST tools from ``dcc-mcp-core``:

* ``project_save``   — persist current Blender project state to ``.dcc-mcp/project.json``
* ``project_load``   — read an existing ``project.json`` back
* ``project_resume`` — return the rehydration payload an agent needs to restore
  scene, assets, active skills, tool groups and checkpoint IDs
* ``project_status`` — pure-read snapshot of the current state

The scene resolver discovers the current ``.blend`` file through
``bpy.data.filepath`` inside a guarded import so this module stays usable
outside Blender (tests, ``--background`` with no file open, gateway-only
deployments).

Opt-out: set ``DCC_MCP_BLENDER_PROJECT_TOOLS=0``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Optional

from dcc_mcp_blender import _env

logger = logging.getLogger(__name__)

ENV_PROJECT_TOOLS = _env.ENV_PROJECT_TOOLS

_DCC_NAME = "blender"


class BlenderSceneResolver:
    """Resolve the *current* Blender file path, if one is open.

    Returns ``None`` when no file is saved (unsaved ``.blend`` has an empty
    ``bpy.data.filepath``).  The default implementation guards the ``bpy``
    import so the module remains importable in plain Python.
    """

    def current_scene(self) -> Optional[str]:
        """Return the absolute ``.blend`` path, or ``None`` when unavailable."""
        try:
            import bpy  # noqa: PLC0415
        except Exception:  # noqa: BLE001 — Blender unavailable
            return None
        try:
            filepath = bpy.data.filepath
        except Exception as exc:  # noqa: BLE001 — Blender in odd state
            logger.debug("BlenderSceneResolver: bpy.data.filepath failed: %s", exc)
            return None
        filepath = (filepath or "").strip()
        return filepath or None


def resolve_enabled(flag: Optional[bool] = None) -> bool:
    """Resolve whether project tools should be wired in (``"0"`` disables)."""
    return _env.resolve_project_tools_enabled(flag)


class ProjectToolsIntegration:
    """Bind ``register_project_tools`` against a :class:`BlenderMcpServer`."""

    def __init__(
        self,
        *,
        dcc_name: str = _DCC_NAME,
        scene_resolver: Optional[BlenderSceneResolver] = None,
    ) -> None:
        self.dcc_name = dcc_name
        self.scene_resolver = scene_resolver or BlenderSceneResolver()
        self.bound_scene: Optional[str] = None
        self.bound_project: Any = None
        self.registered: bool = False

    # ── Public API ──────────────────────────────────────────────────────

    def bind(
        self,
        server: Any,
        *,
        project_factory: Optional[Callable[[str], Any]] = None,
        explicit_project: Any = None,
    ) -> bool:
        """Register the four project tools on *server*. Returns success."""
        from dcc_mcp_core import DccProject, register_project_tools  # noqa: PLC0415

        inner = self._inner_server(server)
        if inner is None:
            return False

        project = explicit_project
        if project is None:
            scene = self._safe_resolve_scene()
            if scene:
                factory = project_factory or DccProject.open
                try:
                    project = factory(scene)
                except Exception as exc:  # noqa: BLE001 — unwriteable dir, etc.
                    logger.debug("ProjectToolsIntegration.bind: DccProject.open(%s) failed: %s", scene, exc)
                    project = None

        try:
            register_project_tools(inner, dcc_name=self.dcc_name, project=project)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ProjectToolsIntegration.bind: register_project_tools raised: %s", exc)
            return False

        self.bound_scene = getattr(project, "state", None) and project.state.scene_path
        self.bound_project = project
        self.registered = True
        logger.info(
            "[%s] project tools registered (default scene=%s)",
            self.dcc_name,
            self.bound_scene or "<none>",
        )
        return True

    # ── Internals ───────────────────────────────────────────────────────

    @staticmethod
    def _inner_server(server: Any) -> Any:
        """Return the inner Rust ``McpHttpServer`` exposing registry + handler."""
        inner = getattr(server, "_server", None)
        if inner is None:
            return None
        if not hasattr(inner, "register_handler") or not hasattr(inner, "registry"):
            return None
        return inner

    def _safe_resolve_scene(self) -> Optional[str]:
        try:
            scene = self.scene_resolver.current_scene()
        except Exception as exc:  # noqa: BLE001
            logger.debug("ProjectToolsIntegration: scene resolver raised: %s", exc)
            return None
        if not scene:
            return None
        try:
            scene = str(Path(scene))
        except Exception:  # noqa: BLE001
            scene = str(scene)
        return scene


def attach_to_server(
    server: Any,
    *,
    enabled: Optional[bool] = None,
    dcc_name: str = _DCC_NAME,
    scene_resolver: Optional[BlenderSceneResolver] = None,
    project_factory: Optional[Callable[[str], Any]] = None,
    explicit_project: Any = None,
) -> Optional[ProjectToolsIntegration]:
    """One-shot helper used by :meth:`BlenderMcpServer.register_builtin_actions`.

    Returns the bound :class:`ProjectToolsIntegration`, or ``None`` when the
    env var disabled the surface or registration failed.
    """
    if not resolve_enabled(enabled):
        return None
    integration = ProjectToolsIntegration(dcc_name=dcc_name, scene_resolver=scene_resolver)
    if integration.bind(server, project_factory=project_factory, explicit_project=explicit_project):
        return integration
    return None
