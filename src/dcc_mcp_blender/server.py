"""Blender MCP server — embeds a Streamable HTTP MCP server inside Blender.

Extends :class:`dcc_mcp_core.server_base.DccServerBase` with Blender-specific
skill path discovery and version detection.

All generic logic (skill registration, hot-reload, gateway failover,
action registry, lifecycle) is provided by the base class.

Usage (inside Blender Python console or startup script)::

    import dcc_mcp_blender

    # Start with default port (auto-gateway: first instance wins 8765)
    server = dcc_mcp_blender.start_server()

    # Progressive loading — discover skills without loading them immediately
    n = server.discover_skills()        # scan paths, register tool metadata
    server.load_skill("blender-scene")  # lazy-load a specific skill on demand

    dcc_mcp_blender.stop_server()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from dcc_mcp_core import DccServerOptions, HostExecutionBridge
from dcc_mcp_core.server_base import DccServerBase

from dcc_mcp_blender import (
    _capability_manifest,
    _env,
    _project_tools,
    _readiness,
    _resources,
    _semantic_index,
)
from dcc_mcp_blender.__version__ import __version__
from dcc_mcp_blender.context_snapshot import BlenderContextSnapshotProvider
from dcc_mcp_blender.host import BlenderInlineCallableDispatcher

logger = logging.getLogger(__name__)

# ── constants ────────────────────────────────────────────────────────────────

SERVER_NAME = "dcc-mcp-blender"
SERVER_VERSION = __version__
DEFAULT_PORT = 8765

# Built-in skills directory shipped with this package
_BUILTIN_SKILLS_DIR = Path(__file__).resolve().parent / "skills"

# Environment variable for extra skill paths (colon/semicolon separated)
_ENV_EXTRA_SKILL_PATHS = "DCC_MCP_BLENDER_SKILL_PATHS"
_ENV_GENERIC_SKILL_PATHS = "DCC_MCP_SKILL_PATHS"

_DCC_NAME = "blender"


def _is_host_queue_dispatcher(dispatcher: Any) -> bool:
    """Return True for core QueueDispatcher / BlockingDispatcher-like objects."""
    return callable(getattr(dispatcher, "post", None)) and callable(getattr(dispatcher, "tick", None))


def _host_dispatcher_from(dispatcher: Any) -> Any | None:
    """Resolve the core host dispatcher hidden behind adapter wrappers."""
    if _is_host_queue_dispatcher(dispatcher):
        return dispatcher
    host_dispatcher = getattr(dispatcher, "host_dispatcher", None)
    if host_dispatcher is not None and _is_host_queue_dispatcher(host_dispatcher):
        return host_dispatcher
    return None


# ── options ─────────────────────────────────────────────────────────────────


@dataclass
class BlenderServerOptions:
    """Adapter-local options collapsed for the dcc-mcp-core 0.17+ server contract."""

    port: int = DEFAULT_PORT
    extra_skill_paths: Optional[List[str]] = None
    server_name: str = SERVER_NAME
    server_version: str = SERVER_VERSION
    # Gateway options
    gateway_port: Optional[int] = None
    registry_dir: Optional[str] = None
    dcc_version: Optional[str] = None
    scene: Optional[str] = None
    enable_gateway_failover: Optional[bool] = None
    # Observability options
    metrics_enabled: Optional[bool] = None
    job_storage_path: Optional[str] = None
    enable_workflows: Optional[bool] = None
    # Diagnostics options (new in 0.17+)
    dcc_pid: Optional[int] = None
    dcc_window_title: Optional[str] = None
    dcc_window_handle: Optional[int] = None
    snapshot_provider: Optional[Any] = None
    # Execution options (new in 0.17+)
    dispatcher: Optional[Any] = None  # BaseDccCallableDispatcher
    execution_bridge: Optional[Any] = None  # HostExecutionBridge

    def to_core_options(self) -> DccServerOptions:
        """Convert to core DccServerOptions using from_env()."""
        dispatcher = self.dispatcher
        execution_bridge = self.execution_bridge
        if execution_bridge is None and dispatcher is not None:
            host_dispatcher = _host_dispatcher_from(dispatcher)
            bridge_dispatcher = (
                BlenderInlineCallableDispatcher(host_dispatcher) if host_dispatcher is not None else dispatcher
            )
            execution_bridge = HostExecutionBridge(
                dispatcher=bridge_dispatcher,
                host_dispatcher=host_dispatcher,
                default_thread_affinity="main",
            )
            dispatcher = None
        elif execution_bridge is not None:
            dispatcher = None

        return DccServerOptions.from_env(
            dcc_name=_DCC_NAME,
            builtin_skills_dir=_BUILTIN_SKILLS_DIR,
            port=self.port,
            server_name=self.server_name,
            server_version=self.server_version,
            # Gateway kwargs
            gateway_port=self.gateway_port,
            registry_dir=self.registry_dir,
            dcc_version=self.dcc_version,
            scene=self.scene,
            enable_gateway_failover=_env.resolve_enable_gateway_failover(self.enable_gateway_failover),
            # Observability kwargs
            enable_file_logging=True,  # default
            enable_job_persistence=_env.resolve_job_storage(self.job_storage_path) is not None,
            enable_telemetry=True,  # default
            # Diagnostics kwargs (new in 0.17+)
            dcc_pid=self.dcc_pid,
            dcc_window_title=self.dcc_window_title,
            dcc_window_handle=self.dcc_window_handle,
            snapshot_provider=self.snapshot_provider,
            # Execution kwargs (new in 0.17+)
            dispatcher=dispatcher,
            execution_bridge=execution_bridge,
        )


# ── server class ─────────────────────────────────────────────────────────────


class BlenderMcpServer(DccServerBase):
    """MCP server embedded inside Blender.

    Thin subclass of :class:`~dcc_mcp_core.server_base.DccServerBase`.
    All skill management, hot-reload, and gateway election logic is
    inherited.  This class adds only:

    - Blender built-in skills directory (``skills/``)
    - Blender version detection via ``bpy.app.version_string``
    - Progressive loading helpers: :meth:`discover_skills`, :meth:`loaded_skill_count`

    Multi-instance / gateway
    ------------------------
    dcc-mcp-core implements an **auto-gateway** with first-wins port competition:
    the first Blender process to bind the well-known port (8765) becomes the
    gateway; subsequent instances start on ephemeral ports and register
    themselves automatically.

    Progressive loading
    -------------------
    Skills can be discovered (metadata only, no Python import) and loaded
    on demand::

        server.discover_skills()             # fast: scan SKILL.md files
        server.load_skill("blender-scene")   # lazy: import scripts only now
        server.unload_skill("blender-scene") # unload to free memory

    Attributes:
        port: TCP port the server is listening on (updated after :meth:`start`).
    """

    def __init__(
        self,
        port: int = DEFAULT_PORT,
        extra_skill_paths: Optional[List[str]] = None,
        server_name: str = SERVER_NAME,
        server_version: str = SERVER_VERSION,
        gateway_port: Optional[int] = None,
        registry_dir: Optional[str] = None,
        dcc_version: Optional[str] = None,
        scene: Optional[str] = None,
        enable_gateway_failover: Optional[bool] = None,
        metrics_enabled: Optional[bool] = None,
        job_storage_path: Optional[str] = None,
        enable_workflows: Optional[bool] = None,
        dispatcher: Optional[Any] = None,
        execution_bridge: Optional[Any] = None,
        options: Optional[BlenderServerOptions] = None,
    ) -> None:
        if options is None:
            if dispatcher is None and execution_bridge is None:
                # Default to a UI or standalone dispatcher if none provided
                # (essential for workers started via CLI)
                try:
                    from dcc_mcp_blender.dispatcher import create_dispatcher

                    dispatcher = create_dispatcher(ui_mode=not self.is_background())
                except Exception as exc:  # noqa: BLE001
                    logger.debug("[%s] Failed to create default dispatcher: %s", _DCC_NAME, exc)

            options = BlenderServerOptions(
                port=port,
                extra_skill_paths=extra_skill_paths,
                server_name=server_name,
                server_version=server_version,
                gateway_port=gateway_port,
                registry_dir=registry_dir,
                dcc_version=dcc_version,
                scene=scene,
                enable_gateway_failover=enable_gateway_failover,
                metrics_enabled=metrics_enabled,
                job_storage_path=job_storage_path,
                enable_workflows=enable_workflows,
                dispatcher=dispatcher,
                execution_bridge=execution_bridge,
            )

        super().__init__(options=options.to_core_options())

        self._extra_skill_paths: List[str] = list(options.extra_skill_paths or [])

        if _env.resolve_metrics_enabled(options.metrics_enabled):
            self._config.enable_prometheus = True
            logger.info("[%s] Prometheus /metrics endpoint enabled", _DCC_NAME)

        effective_job_path = _env.resolve_job_storage(options.job_storage_path)
        if effective_job_path:
            self._config.job_storage_path = effective_job_path
            logger.info("[%s] Job storage: %s", _DCC_NAME, effective_job_path)
        elif effective_job_path == "":
            self._config.job_storage_path = ""

        if _env.resolve_enable_workflows(options.enable_workflows):
            try:
                self._config.enable_workflows = True
                logger.info(
                    "[%s] Workflow engine enabled (workflows.run / .resume / .list_runs)",
                    _DCC_NAME,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("[%s] Could not enable workflows on inner config: %s", _DCC_NAME, exc)

        gateway_port_arg = options.gateway_port
        enable_gw = _env.resolve_enable_gateway_failover(options.enable_gateway_failover)
        if gateway_port_arg == 0 or (gateway_port_arg is None and not enable_gw):
            self._config.gateway_port = 0

        # Host dispatcher (if any) is owned by core's execution bridge; expose
        # it under a stable attribute so the readiness binder can schedule its
        # main-thread probe.  ``None`` in background / standalone mode.
        self._blender_dispatcher: Any = getattr(self, "_dcc_dispatcher", None)

        # ── Context snapshot + capability manifest ──────────────────────────
        self._snapshot_provider_impl: BlenderContextSnapshotProvider = BlenderContextSnapshotProvider()
        try:
            self.set_context_snapshot_provider(self._snapshot_provider_impl)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[%s] set_context_snapshot_provider failed: %s", _DCC_NAME, exc)

        self._capability_builder = _capability_manifest.BlenderCapabilityManifestBuilder(
            dcc_name=_DCC_NAME,
            skill_lister=self.list_skills,
            action_lister=getattr(self, "list_actions", None),
            is_loaded=self.is_skill_loaded,
            skill_info_lister=getattr(self, "get_skill_info", None),
        )

        # Populated by :meth:`register_builtin_actions`; ``None`` means the
        # surface was disabled by env var or the core call failed.
        self._project_tools: Optional[_project_tools.ProjectToolsIntegration] = None
        self._resources: Optional[_resources.BlenderResourceBinder] = None

        # ── Runtime readiness probe (three-state) ───────────────────────────
        self._readiness_timeout_secs: Optional[int] = _readiness.resolve_readiness_timeout_secs(None)
        self.readiness: Optional[_readiness.ReadinessBinder] = _readiness.install_readiness(self)

        # ── Morphology-aware semantic recall (opt-in) ───────────────────────
        try:
            self._semantic: Optional[_semantic_index.BlenderSemanticIndex] = _semantic_index.build_semantic_index()
        except Exception as exc:  # noqa: BLE001
            logger.debug("[%s] semantic index init failed: %s", _DCC_NAME, exc)
            self._semantic = None
        if self._semantic is not None:
            logger.info("[%s] semantic skill recall enabled (embedder=%s)", _DCC_NAME, self._semantic.embedder_kind)

    # ── Blender version detection ──────────────────────────────────────────────

    def _version_string(self) -> str:
        """Return the Blender version via ``bpy.app.version_string``."""
        try:
            import bpy  # noqa: PLC0415

            return bpy.app.version_string
        except ImportError:
            return "unknown"

    # ── Port property ──────────────────────────────────────────────────────────

    @property
    def port(self) -> int:
        """TCP port the server is listening on."""
        if self._handle is not None:
            try:
                return int(self._handle.port)
            except Exception:
                pass
        return int(self._options.port)

    # ── Skill search path helpers ──────────────────────────────────────────────

    def _collect_skill_paths(self) -> List[str]:
        """Collect and deduplicate existing skill paths.

        Delegates to :meth:`~dcc_mcp_core.server_base.DccServerBase.collect_skill_search_paths`
        with ``filter_existing=True`` so only directories that exist on disk are
        returned.  This prevents ``McpHttpServer.discover()`` from logging warnings
        about missing paths.
        """
        return self.collect_skill_search_paths(
            extra_paths=self._extra_skill_paths,
            filter_existing=True,
        )

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self, *, install_atexit_hook: bool = True) -> "BlenderMcpServer":
        """Start the MCP HTTP server and the attached host dispatcher.

        Returns *self* for chaining.
        """
        super().start(install_atexit_hook=install_atexit_hook)
        if self._blender_dispatcher is not None:
            start_fn = getattr(self._blender_dispatcher, "start", None)
            if callable(start_fn):
                start_fn()
        return self

    def stop(self) -> None:
        """Detach MCP resource handlers, stop the HTTP server and the dispatcher."""
        if self._resources is not None:
            try:
                self._resources.unbind()
            except Exception as exc:  # noqa: BLE001
                logger.debug("[%s] resources.unbind failed: %s", _DCC_NAME, exc)

        super().stop()

        if self._blender_dispatcher is not None:
            stop_fn = getattr(self._blender_dispatcher, "stop", None)
            if callable(stop_fn):
                stop_fn()

    # ── Builtin action registration + core integrations ────────────────────────

    def register_builtin_actions(
        self,
        extra_skill_paths: Optional[List[str]] = None,
        include_bundled: bool = True,
        minimal_mode: Any = None,
    ) -> "BlenderMcpServer":
        """Discover skills and attach Blender-specific core integrations.

        Runs core's discovery first, then wires the optional adapter
        integrations (recipes/docs/introspect/feedback/capability manifest/
        project tools/resources).  Every integration degrades gracefully so a
        missing optional core API never breaks startup.
        """
        super().register_builtin_actions(
            extra_skill_paths=extra_skill_paths,
            include_bundled=include_bundled,
            minimal_mode=minimal_mode,
        )
        self._register_metadata_driven_tools(extra_skill_paths, include_bundled)
        self._register_introspect_tools()
        self._register_feedback_tool()
        self._register_capability_manifest_tool()
        self._attach_project_tools()
        self._attach_resources()
        return self

    def _register_metadata_driven_tools(
        self,
        extra_skill_paths: Optional[List[str]] = None,
        include_bundled: bool = True,
    ) -> None:
        """Register ``recipes__*`` and ``skill_refs__*`` via core metadata registration."""
        try:
            from dcc_mcp_core.metadata_registration import register_metadata_driven_tools  # noqa: PLC0415
        except ImportError as exc:
            logger.debug("[%s] metadata_driven_tools skipped (import): %s", _DCC_NAME, exc)
            return

        extra = list(extra_skill_paths) if extra_skill_paths else []
        paths = self.collect_skill_search_paths(
            extra_paths=extra + self._extra_skill_paths,
            include_bundled=include_bundled,
            filter_existing=True,
        )
        try:
            report = register_metadata_driven_tools(
                self._server,
                dcc_name=_DCC_NAME,
                extra_paths=paths,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("[%s] metadata_driven_tools registration failed: %s", _DCC_NAME, exc)
            return
        if not report.ok:
            logger.debug(
                "[%s] metadata_driven_tools: %d registered, %d skipped, %d failed",
                _DCC_NAME,
                report.registered_count,
                report.skipped_count,
                report.failed_count,
            )

    def _register_introspect_tools(self) -> None:
        """Register the shared core ``dcc_introspect__*`` tools."""
        try:
            from dcc_mcp_core import register_introspect_tools  # noqa: PLC0415

            register_introspect_tools(self._server, dcc_name=_DCC_NAME)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[%s] introspect tools registration failed: %s", _DCC_NAME, exc)

    def _register_feedback_tool(self) -> None:
        """Register the shared core ``dcc_feedback__report`` tool."""
        try:
            from dcc_mcp_core import register_feedback_tool  # noqa: PLC0415

            register_feedback_tool(self._server, dcc_name=_DCC_NAME)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[%s] feedback tool registration failed: %s", _DCC_NAME, exc)

    def _register_capability_manifest_tool(self) -> None:
        try:
            _capability_manifest.register_capability_mcp_tool(self, builder=self._capability_builder)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[%s] capability manifest MCP tool registration failed: %s", _DCC_NAME, exc)

    def _attach_project_tools(self) -> None:
        try:
            self._project_tools = _project_tools.attach_to_server(self)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[%s] project tools registration failed: %s", _DCC_NAME, exc)

    def _attach_resources(self) -> None:
        try:
            self._resources = _resources.install_resources(
                self,
                snapshot_provider=self._snapshot_provider_impl.collect,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("[%s] resources registration failed: %s", _DCC_NAME, exc)

    # ── Readiness + capability manifest (programmatic access) ──────────────────

    def readiness_report(self) -> dict:
        """Return the current three-state readiness snapshot as a dict."""
        if self.readiness is None:
            return {"process": True, "dispatcher": False, "dcc": False}
        return self.readiness.report()

    def build_capability_manifest(self, *, loaded_only: bool = False) -> dict:
        """Return the compact Blender capability manifest as a dict."""
        records = self._capability_builder.build()
        if loaded_only:
            records = [r for r in records if r.loaded]
        instance_id = getattr(self, "instance_id", None)
        scene = getattr(self._config, "scene", None)
        version = getattr(self._config, "dcc_version", None)
        return _capability_manifest.build_manifest_payload(
            records,
            dcc_name=_DCC_NAME,
            dcc_version=version,
            scene=scene,
            instance_id=instance_id,
        )

    # ── Progressive skill loading ──────────────────────────────────────────────

    def discover_skills(
        self,
        extra_paths: Optional[List[str]] = None,
    ) -> int:
        """Scan skill directories and register tool metadata without importing scripts.

        This is the *discover* phase of progressive loading — only SKILL.md
        metadata is parsed; no Python skill scripts are imported yet.  Call
        :meth:`load_skill` to import a specific skill on demand.

        Args:
            extra_paths: Additional directories to scan beyond the configured paths.

        Returns:
            Number of newly discovered skills (0 if server is not running).
        """
        if self._handle is None:
            logger.warning("discover_skills called before server was started")
            return 0
        paths = self._collect_skill_paths()
        if extra_paths:
            paths = list(extra_paths) + paths
        count = self._server.discover(extra_paths=paths, dcc_name=_DCC_NAME)
        logger.debug("BlenderMcpServer: discovered %d new skill(s)", count)
        return count

    def load_skill(self, skill_name: str) -> bool:
        """Load a skill by name.

        Args:
            skill_name: Skill name as declared in ``SKILL.md`` (e.g. ``"blender-scene"``).

        Returns:
            ``True`` when the core server accepted the load request.
        """
        try:
            self._server.load_skill(skill_name)
        except Exception as exc:  # noqa: BLE001
            logger.debug("BlenderMcpServer: load_skill(%r) failed: %s", skill_name, exc)
            return False
        return True

    def unload_skill(self, skill_name: str) -> bool:
        """Unload a skill, removing its tools from the registry.

        Args:
            skill_name: Skill name to unload.

        Returns:
            ``True`` when the core server accepted the unload request.
        """
        try:
            self._server.unload_skill(skill_name)
        except Exception as exc:  # noqa: BLE001
            logger.debug("BlenderMcpServer: unload_skill(%r) failed: %s", skill_name, exc)
            return False
        return True

    def list_skills(self, status: Optional[str] = None) -> List[Dict[str, Any]]:  # type: ignore[override]
        """List all discovered skills with their load status.

        Args:
            status: Optional filter — ``"loaded"`` or ``"unloaded"``.

        Returns:
            List of dicts with skill status information, or ``[]`` if not running.
        """
        if self._handle is None:
            return []
        return list(self._server.list_skills(status=status))  # type: ignore[arg-type]

    def search_skills(  # type: ignore[override]
        self,
        query: Optional[str] = None,
        tags: Optional[List[str]] = None,
        dcc: Optional[str] = None,
        scope: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Search for skills matching the given criteria.

        Args:
            query: Free-text query matched against skill name/description.
            tags: Required tags (skill must have all).
            dcc: DCC filter (defaults to ``"blender"``).
            scope: Optional skill scope filter (``"system"``, ``"project"``, etc.).
            limit: Optional maximum number of results.

        Returns:
            List of matching skill metadata dicts, or ``[]`` if not running.
        """
        if self._handle is None:
            return []
        try:
            base = list(
                self._server.search_skills(
                    query=query,
                    tags=tags or [],
                    dcc=dcc or _DCC_NAME,
                    scope=scope,
                    limit=limit,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("BlenderMcpServer: search_skills failed: %s", exc)
            return []

        # Opt-in semantic augmentation: append morphology recalls after the
        # canonical BM25 results. Base ordering is preserved (promote, never
        # demote); vector-only hits are appended.
        if self._semantic is not None and query:
            try:
                return self._semantic.augment(base, query, self.list_skills())
            except Exception as exc:  # noqa: BLE001
                logger.debug("BlenderMcpServer: semantic augment failed: %s", exc)
        return base

    def find_skills(
        self,
        query: Optional[str] = None,
        tags: Optional[List[str]] = None,
        dcc: Optional[str] = None,
        scope: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Backward-compatible alias for :meth:`search_skills`."""
        return self.search_skills(query=query, tags=tags, dcc=dcc, scope=scope, limit=limit)

    def is_skill_loaded(self, skill_name: str) -> bool:  # type: ignore[override]
        """Return ``True`` if the named skill is currently loaded."""
        if self._handle is None:
            return False
        return self._server.is_loaded(skill_name)

    def loaded_skill_count(self) -> int:
        """Return the number of currently loaded skills."""
        if self._handle is None:
            return 0
        return self._server.loaded_count()


# ── module-level singleton helpers ────────────────────────────────────────────

_server_instance: Optional[BlenderMcpServer] = None


def start_server(
    port: int = DEFAULT_PORT,
    extra_skill_paths: Optional[List[str]] = None,
    register_builtins: bool = True,
    include_bundled: bool = True,
    enable_hot_reload: bool = False,
    gateway_port: Optional[int] = None,
    registry_dir: Optional[str] = None,
    dcc_version: Optional[str] = None,
    scene: Optional[str] = None,
    enable_gateway_failover: Optional[bool] = None,
    metrics_enabled: Optional[bool] = None,
    job_storage_path: Optional[str] = None,
    enable_workflows: Optional[bool] = None,
    dispatcher: Optional[Any] = None,
    execution_bridge: Optional[Any] = None,
) -> BlenderMcpServer:
    """Start the Blender MCP server (creates a process-level singleton).

    The first call creates and starts the server.  Subsequent calls return the
    existing instance without restarting it.

    Multi-instance support (gateway mode)
    --------------------------------------
    dcc-mcp-core implements first-wins port competition: if port 8765 is already
    taken by another Blender process, this instance starts on a random port and
    registers with the gateway automatically.

    Args:
        port: Preferred TCP port (default 8765; use 0 for a random port).
        extra_skill_paths: Additional skill directories beyond built-ins.
        register_builtins: If ``True``, discover and load all skills.
        include_bundled: Include dcc-mcp-core bundled skills.
        enable_hot_reload: Enable skill hot-reload on file changes.
        gateway_port: Gateway competition port.
        registry_dir: Shared registry directory.
        dcc_version: Blender version for gateway registry.
        scene: Currently open scene file path for the gateway registry.
        enable_gateway_failover: Enable automatic gateway failover.
        metrics_enabled: Force Prometheus ``/metrics`` (``None`` = env ``DCC_MCP_BLENDER_METRICS``).
        job_storage_path: SQLite job DB path (``None`` = env / default).
        enable_workflows: Enable workflow MCP tools (``None`` = env).
        dispatcher: Optional host dispatcher for main-thread execution.
        execution_bridge: Optional execution bridge supplied by dcc-mcp-core.

    Returns:
        The running :class:`BlenderMcpServer` instance.
    """
    global _server_instance  # noqa: PLW0603
    if _server_instance is not None and _server_instance.is_running:
        return _server_instance

    _server_instance = BlenderMcpServer(
        port=port,
        extra_skill_paths=extra_skill_paths,
        gateway_port=gateway_port,
        registry_dir=registry_dir,
        dcc_version=dcc_version,
        scene=scene,
        enable_gateway_failover=enable_gateway_failover,
        metrics_enabled=metrics_enabled,
        job_storage_path=job_storage_path,
        enable_workflows=enable_workflows,
        dispatcher=dispatcher,
        execution_bridge=execution_bridge,
    )
    if register_builtins:
        _server_instance.register_builtin_actions(include_bundled=include_bundled)
    if enable_hot_reload:
        _server_instance.enable_hot_reload()
    _server_instance.start()
    return _server_instance


def stop_server() -> None:
    """Stop the running Blender MCP server."""
    global _server_instance  # noqa: PLW0603
    if _server_instance is None:
        return
    _server_instance.stop()
    _server_instance = None


def get_server() -> Optional[BlenderMcpServer]:
    """Return the current server instance, or ``None`` if not started."""
    return _server_instance
