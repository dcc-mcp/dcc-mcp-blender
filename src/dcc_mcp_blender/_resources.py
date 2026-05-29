"""Blender resource publishing wiring.

Ports the Maya resource binder to Blender.  Core ships
``McpHttpServer.resources()`` → ``ResourceHandle`` with ``set_scene`` /
``register_producer`` / ``notify_updated``.  ``scene://current`` is a built-in
resource URI that returns ``status: no_scene_published`` until the embedding
adapter calls ``set_scene(...)``.  This module is that adapter for Blender.

Blender has no ``scriptJob`` API, so scene-change republishing is driven by
``bpy.app.handlers`` (``save_post`` / ``load_post`` / ``depsgraph_update_post``)
through an injectable installer.  Every Blender access is lazy and guarded so
the module is importable in plain Python (tests, ``--background``).

Opt-out: set ``DCC_MCP_BLENDER_RESOURCES=0``.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from dcc_mcp_blender import _env

logger = logging.getLogger(__name__)

ENV_RESOURCES = _env.ENV_RESOURCES

#: Throttle for ``scene://current`` republishing.  ``depsgraph_update_post``
#: fires extremely frequently, so collapse storms into one publish per window.
DEFAULT_SCENE_THROTTLE_SECS: float = 0.5

#: ``bpy.app.handlers`` names whose firing triggers a republish.
DEFAULT_SCENE_HANDLERS: tuple = (
    "save_post",
    "load_post",
    "depsgraph_update_post",
)

#: Blender-specific dynamic resource scheme exposing ``bpy.data`` counts.
SCHEME_BLENDER_DATA = "blender-data://"


def resolve_enabled(flag: Optional[bool] = None) -> bool:
    """Resolve whether resource wiring should run (``"0"`` disables)."""
    return _env.resolve_resources_enabled(flag)


# ---------------------------------------------------------------------------
# Producer callables — pure functions, lazy bpy import
# ---------------------------------------------------------------------------


def _read_text(text: str, mime: str = "text/plain") -> Dict[str, Any]:
    return {"mimeType": mime, "text": text}


def _bpy():
    """Lazy ``bpy`` import; returns ``None`` outside Blender."""
    try:
        import bpy  # noqa: PLC0415

        return bpy
    except Exception:  # noqa: BLE001
        return None


def _blender_data_producer(uri: str) -> Dict[str, Any]:  # noqa: ARG001 — single scheme
    """Producer for ``blender-data://current`` returning a ``bpy.data`` summary."""
    bpy = _bpy()
    if bpy is None:
        return _read_text(json.dumps({"status": "blender_unavailable"}), mime="application/json")
    summary: Dict[str, Any] = {}
    for collection in ("objects", "meshes", "materials", "collections", "lights", "cameras", "node_groups"):
        try:
            summary[collection] = len(getattr(bpy.data, collection))
        except Exception:  # noqa: BLE001
            continue
    try:
        summary["filepath"] = str(bpy.data.filepath or "")
    except Exception:  # noqa: BLE001
        pass
    return _read_text(json.dumps({"data": summary}), mime="application/json")


# ---------------------------------------------------------------------------
# Scene-event installer (bpy.app.handlers)
# ---------------------------------------------------------------------------


SnapshotProvider = Callable[[], Dict[str, Any]]
EventInstaller = Callable[[Callable[[], None], tuple], List[Callable]]
BusyChecker = Callable[[], bool]


def _default_event_installer(callback: Callable[[], None], handlers: tuple) -> List[Callable]:
    """Append a wrapper to each ``bpy.app.handlers`` list in *handlers*.

    Returns the list of installed wrapper callables (for cleanup).  Best
    effort: unknown handler names are skipped, a missing ``bpy`` yields ``[]``.
    """
    bpy = _bpy()
    if bpy is None:
        return []
    installed: List[Callable] = []
    for name in handlers:
        handler_list = getattr(bpy.app.handlers, name, None)
        if handler_list is None:
            continue

        def _wrapper(*_args: Any, _cb=callback) -> None:
            _cb()

        try:
            handler_list.append(_wrapper)
        except Exception as exc:  # noqa: BLE001
            logger.debug("resources: handler append(%s) refused: %s", name, exc)
            continue
        installed.append(_wrapper)
        # Stash the handler-list name on the wrapper for removal.
        setattr(_wrapper, "_dcc_handler_name", name)
    return installed


def _default_event_remover(wrappers: List[Callable]) -> None:
    """Remove wrappers installed by :func:`_default_event_installer`."""
    bpy = _bpy()
    if bpy is None:
        return
    for wrapper in wrappers:
        name = getattr(wrapper, "_dcc_handler_name", None)
        handler_list = getattr(bpy.app.handlers, name, None) if name else None
        if handler_list is None:
            continue
        try:
            handler_list.remove(wrapper)
        except Exception as exc:  # noqa: BLE001
            logger.debug("resources: handler remove(%s) failed: %s", name, exc)


# ---------------------------------------------------------------------------
# Blender-side binder
# ---------------------------------------------------------------------------


class BlenderResourceBinder:
    """Compose every ``server._server.resources()`` call for Blender."""

    def __init__(
        self,
        *,
        snapshot_provider: Optional[SnapshotProvider] = None,
        event_installer: Optional[EventInstaller] = None,
        busy_checker: Optional[BusyChecker] = None,
        throttle_secs: float = DEFAULT_SCENE_THROTTLE_SECS,
        handlers: tuple = DEFAULT_SCENE_HANDLERS,
    ) -> None:
        self.snapshot_provider: Optional[SnapshotProvider] = snapshot_provider
        self.event_installer: EventInstaller = event_installer or _default_event_installer
        self.busy_checker: Optional[BusyChecker] = busy_checker
        self.throttle_secs: float = max(0.0, float(throttle_secs))
        self.handlers: tuple = handlers

        self.bound_server: Any = None
        self.handle: Any = None
        self.registered_producers: List[str] = []
        self.scene_event_handles: List[Callable] = []
        self.scene_publish_count: int = 0

        self._lock = threading.Lock()
        self._pending_publish: bool = False
        self._last_publish_at: float = 0.0
        self._publish_timer: Optional[threading.Timer] = None
        self._unbound: bool = False

    # ── Public API ──────────────────────────────────────────────────────

    def bind(self, server: Any) -> bool:
        """Resolve the resource handle, register producers, publish a snapshot."""
        if self.bound_server is server:
            return True
        self.bound_server = server
        self._unbound = False

        try:
            self.handle = server._server.resources()
        except Exception as exc:  # noqa: BLE001
            logger.debug("resources: server.resources() unavailable: %s", exc)
            return False

        self._register_producer(SCHEME_BLENDER_DATA, _blender_data_producer)

        if self.snapshot_provider is not None:
            self._publish_scene_now()
        return True

    def install_scene_events(self) -> List[Callable]:
        """Hook ``bpy.app.handlers`` so scene mutations republish ``scene://current``."""
        if self.bound_server is None:
            return []
        if self.scene_event_handles:
            return list(self.scene_event_handles)
        handles = self.event_installer(self._on_scene_event, self.handlers)
        self.scene_event_handles = list(handles)
        return list(self.scene_event_handles)

    def unbind(self) -> None:
        """Detach handlers and stop pending publishes.  Idempotent."""
        if self._unbound:
            return
        self._unbound = True

        with self._lock:
            timer = self._publish_timer
            self._publish_timer = None
            self._pending_publish = False
        if timer is not None:
            try:
                timer.cancel()
            except Exception:  # noqa: BLE001
                pass

        if self.scene_event_handles:
            try:
                _default_event_remover(self.scene_event_handles)
            except Exception as exc:  # noqa: BLE001
                logger.debug("resources: event remover raised: %s", exc)
            self.scene_event_handles = []

    def publish_scene(self, payload: Optional[Dict[str, Any]] = None) -> None:
        """Publish a scene snapshot now, bypassing throttling."""
        if self.handle is None:
            return
        if payload is None:
            if self.snapshot_provider is None:
                return
            try:
                payload = self.snapshot_provider()
            except Exception as exc:  # noqa: BLE001
                logger.debug("resources: snapshot provider raised: %s", exc)
                return
        try:
            self.handle.set_scene(payload)
            self.scene_publish_count += 1
            self._last_publish_at = time.monotonic()
        except Exception as exc:  # noqa: BLE001
            logger.debug("resources: set_scene raised: %s", exc)

    # ── Internals ───────────────────────────────────────────────────────

    def _register_producer(self, scheme: str, producer: Callable[[str], Dict[str, Any]]) -> None:
        if self.handle is None:
            return
        try:
            self.handle.register_producer(scheme, producer)
        except Exception as exc:  # noqa: BLE001
            logger.debug("resources: register_producer(%s) raised: %s", scheme, exc)
            return
        self.registered_producers.append(scheme)

    def _is_executor_busy(self) -> bool:
        if self.busy_checker is None:
            return False
        try:
            return bool(self.busy_checker())
        except Exception as exc:  # noqa: BLE001
            logger.debug("resources: busy checker raised: %s", exc)
            return False

    def _on_scene_event(self) -> None:
        """Handler callback: schedule a throttled scene republish."""
        if self._unbound or self._is_executor_busy():
            return
        with self._lock:
            now = time.monotonic()
            since = now - self._last_publish_at
            if since >= self.throttle_secs:
                schedule_now = True
                self._pending_publish = False
            else:
                schedule_now = False
                if not self._pending_publish:
                    delay = self.throttle_secs - since
                    self._pending_publish = True
                    self._publish_timer = threading.Timer(delay, self._on_throttle_fire)
                    self._publish_timer.daemon = True
                    self._publish_timer.start()
        if schedule_now:
            self._publish_scene_now()

    def _on_throttle_fire(self) -> None:
        if self._unbound or self._is_executor_busy():
            return
        with self._lock:
            self._pending_publish = False
            self._publish_timer = None
        self._publish_scene_now()

    def _publish_scene_now(self) -> None:
        self.publish_scene()


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------


def install_resources(
    server: Any,
    *,
    enabled: Optional[bool] = None,
    snapshot_provider: Optional[SnapshotProvider] = None,
    install_scene_events: bool = True,
    busy_checker: Optional[BusyChecker] = None,
    throttle_secs: float = DEFAULT_SCENE_THROTTLE_SECS,
) -> Optional[BlenderResourceBinder]:
    """One-shot helper called from :meth:`BlenderMcpServer.register_builtin_actions`.

    Returns the :class:`BlenderResourceBinder` when installation succeeded, or
    ``None`` when resources were disabled (``DCC_MCP_BLENDER_RESOURCES=0``) or
    the inner Rust ``McpHttpServer.resources()`` raised.
    """
    if not resolve_enabled(enabled):
        logger.debug("resources: disabled via env var")
        return None
    binder = BlenderResourceBinder(
        snapshot_provider=snapshot_provider,
        busy_checker=busy_checker,
        throttle_secs=throttle_secs,
    )
    if not binder.bind(server):
        return None
    if install_scene_events:
        binder.install_scene_events()
    return binder
