"""Blender add-on / extension entry for DCC MCP Blender.

Shipped at the root of the add-on folder next to ``blender_manifest.toml``.
Keeps ``bl_info`` for legacy ``scripts/addons`` installs and supplies the
extension manifest for Blender extension workflows.
"""

from __future__ import annotations

import importlib
import logging
import os
import re
import webbrowser
from contextlib import suppress
from typing import Any, List, Optional, Tuple

import bpy

logger = logging.getLogger(__name__)

_ECHO_PREFIX = "[DCC MCP Blender]"

bl_info = {
    "name": "DCC MCP Blender",
    "author": "Long Hao",
    "version": (
        0,  # x-release-please-major
        2,  # x-release-please-minor
        12,  # x-release-please-patch
    ),
    "blender": (4, 5, 0),
    "location": "Top Bar > DCC MCP",
    "description": "Embeds an MCP HTTP server inside Blender for AI-driven 3D workflows",
    "category": "System",
    "doc_url": "https://github.com/dcc-mcp/dcc-mcp-blender",
    "tracker_url": "https://github.com/dcc-mcp/dcc-mcp-blender/issues",
}

_DEFAULT_GATEWAY_PORT = 9765
_BACKGROUND_RENDER_ENV = "DCC_MCP_BACKGROUND_RENDER"
_UI_CONTROL_PROCESS_ID_ENV = "DCC_MCP_UI_CONTROL_PROCESS_ID"

_draw_handlers: List[Tuple[str, object]] = []
_server_dispatcher: Any = None
_server_host: Any = None
_runtime_import_aliases: Any = None
_canonical_package: Optional[str] = None


def _normalised(path: str) -> str:
    return os.path.normcase(os.path.realpath(str(path)))


def _own_package_dir() -> str:
    """Return the directory this entry point's own package code lives in."""
    locations = [str(entry) for entry in (globals().get("__path__") or ())]
    if locations:
        return os.path.abspath(locations[0])
    return os.path.dirname(os.path.abspath(__file__))


def _version_tuple(version: str) -> Tuple[int, int, int]:
    """Parse a ``major.minor.patch`` prefix; only the leading digits count.

    A pre-release or local suffix must never rank above the release it belongs
    to, so ``1.0.0-rc1`` is ``(1, 0, 0)`` rather than ``(1, 0, 1)``.
    """
    parts: List[int] = []
    for chunk in str(version).split(".")[:3]:
        digits = ""
        for character in chunk:
            if not character.isdigit():
                break
            digits += character
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return (parts[0], parts[1], parts[2])


def _package_version(package_dir: str) -> Optional[str]:
    """Read a package directory's declared version without importing it."""
    candidate = os.path.join(str(package_dir), "__version__.py")
    try:
        with open(candidate, encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        logger.debug("version file unreadable at %s: %s", candidate, exc)
        return None
    match = re.search(r"__version__\s*=\s*[\"']([^\"']+)[\"']", text)
    return match.group(1) if match else None


def _resolve_canonical_package() -> str:
    """Return the package the runtime must run from: the resolved copy wins.

    Blender loads user-level extensions before a package environment is visible,
    so a stale extension copy -- left behind by an earlier install under the same
    Blender major version -- keeps answering ``import dcc_mcp_blender`` even when
    a package manager resolved a newer copy for this session. The stale copy
    satisfies its own, older compatibility gate, starts a server, and reports an
    old version without a single error, so every capability captured from that
    host silently describes the wrong runtime.

    Whenever a real distribution is importable from ``sys.path`` and is at least
    as new as the copy this entry point belongs to, the runtime hands over to
    it. Otherwise the extension keeps control and says so out loud.

    The comparison is against the version of the extension copy actually on
    disk, not against ``__addon_version__``: an older extension that ships a
    newer entry point would otherwise always win and keep serving silently.
    """
    global _canonical_package  # noqa: PLW0603
    if _canonical_package is not None:
        return _canonical_package
    package = __package__ or ""
    if not package.startswith("bl_ext."):
        # Legacy add-on installs and the library package both serve the public
        # distribution name. Only an extension namespace is a distinct tree.
        _canonical_package = "dcc_mcp_blender"
        return _canonical_package
    _canonical_package = package
    origin = None
    try:
        origin = importlib.import_module(f"{package}._extension_imports").public_package_origin("dcc_mcp_blender")
    except Exception as exc:  # noqa: BLE001 - provenance is best effort, never fatal here
        logger.debug("package origin lookup failed: %s", exc)
    if not origin:
        return _canonical_package
    distribution_dir = os.path.dirname(str(origin))
    if _normalised(distribution_dir) == _normalised(_own_package_dir()):
        # Same source tree: this extension is the distribution (ZIP install).
        return _canonical_package
    resolved_version = _package_version(distribution_dir)
    extension_version = _package_version(_own_package_dir())
    if (
        resolved_version is None
        or extension_version is None
        or _version_tuple(resolved_version) >= _version_tuple(extension_version)
    ):
        print(
            f"{_ECHO_PREFIX} Running dcc_mcp_blender {resolved_version or 'unknown'} resolved by the environment at "
            f"{distribution_dir} instead of this extension copy {extension_version or 'unknown'}."
        )
        _canonical_package = "dcc_mcp_blender"
    else:
        print(
            f"{_ECHO_PREFIX} WARNING: dcc_mcp_blender {resolved_version} at {distribution_dir} is older than this "
            f"extension copy ({extension_version}); keeping the extension. Remove the stale copy to let the "
            "environment resolve the runtime, or export DCC_MCP_BLENDER_PACKAGE_ROOT to fail closed."
        )
    return _canonical_package


def _reset_canonical_package() -> None:
    """Drop the cached package resolution after ``sys.path`` changed."""
    global _canonical_package  # noqa: PLW0603
    _canonical_package = None


# Blender imports every add-on module just to read ``bl_info``, so the public
# adapter surface is re-exported lazily (PEP 562) instead of eagerly. ``__all__``
# is served by ``__getattr__`` on purpose: a module-level ``__all__`` global
# would shadow the lazy hook and hide the adapter surface.
_ADDON_EXPORTS = (
    "bl_info",
    "register",
    "unregister",
)

# Public names that start with an underscore. Kept explicit on purpose: the
# ``__getattr__`` hook below must reject underscore-prefixed names *before*
# touching ``_public_api``, because ``from . import _capability_manifest`` in a
# bundled module relies on ``AttributeError`` to fall back to the real submodule
# loader. Consulting the public surface first would recurse into it.
# ``test_addon_entry_dunder_exports_match_the_library_surface`` guards drift.
_DUNDER_EXPORTS = frozenset({"__version__"})


def _addon_module(name: str):
    """Import a bundled module through the active add-on package namespace."""
    package = _resolve_canonical_package()
    return importlib.import_module(f"{package}.{name}")


def _public_api_module():
    """Return the bundled public-surface module in this add-on namespace."""
    # Blender 5.x boots an isolated Python that ignores PYTHONPATH, so injected
    # dependencies are invisible from inside the host. Repair it before the
    # public surface imports core; on other hosts this is a no-op.
    _addon_module("_isolated_path").repair_sys_path()
    module = _addon_module("_public_api")
    # Importing the ``__version__`` submodule leaves the *module* bound as the
    # package attribute. The wheel channel rebinds it to the version string via
    # ``import *``; do the same here so both channels answer identically.
    for name in _DUNDER_EXPORTS:
        value = getattr(module, name, None)
        if value is not None:
            globals()[name] = value
    return module


def _install_runtime_import_aliases(*, strict: bool = True) -> None:
    """Expose public skill imports without mutating Blender's ``sys.path``."""
    global _runtime_import_aliases  # noqa: PLW0603
    package = __package__ or ""
    if not package.startswith("bl_ext."):
        return
    if _resolve_canonical_package() != package:
        # The resolved distribution drives the runtime, so the public name already
        # resolves to it. Bridging would shadow it with this extension copy.
        # A bridge installed earlier (the best-effort import-time one, before
        # the package environment was on ``sys.path``) must go too, or the
        # extension copy keeps answering ``import dcc_mcp_blender``.
        _remove_runtime_import_aliases()
        return
    installer = _addon_module("_extension_imports").install_extension_import_aliases
    aliases = installer(package, strict=strict)
    if aliases is not None and getattr(aliases, "installed", False):
        _runtime_import_aliases = aliases


def _remove_runtime_import_aliases() -> None:
    """Fully withdraw the public import bridge (only on a failed/aborted enable).

    An ordinary ``unregister()`` calls :func:`_detach_runtime_import_aliases`
    instead: Blender disables add-ons on ``wm.read_factory_settings``, and
    headless pipeline scripts import ``dcc_mcp_blender`` right after that.
    """
    global _runtime_import_aliases  # noqa: PLW0603
    aliases = _runtime_import_aliases
    _runtime_import_aliases = None
    if aliases is not None:
        aliases.uninstall()


def _detach_runtime_import_aliases() -> None:
    """Drop stale public facades while keeping the import contract resolvable."""
    global _runtime_import_aliases  # noqa: PLW0603
    aliases = _runtime_import_aliases
    if aliases is not None:
        aliases.detach()


def __getattr__(name: str):
    """Expose the wheel channel's top-level surface from the add-on entrypoint.

    The Blender extension package root *is* ``dcc_mcp_blender``, so this module
    is what ``import dcc_mcp_blender`` resolves to in that channel. Without this
    hook, ``dcc_mcp_blender.BlenderHost`` and friends exist only in the wheel
    channel and skill scripts break on one of the two distributions.
    """
    if name == "__all__":
        public_api = _public_api_module()
        return list(_ADDON_EXPORTS) + [n for n in public_api.__all__ if n not in _ADDON_EXPORTS]
    # Fail fast for submodule and private lookups. ``from . import <submodule>``
    # and every ``_<private>`` name must raise AttributeError without importing
    # anything, or the import machinery never reaches the submodule loader and
    # ``_public_api`` recurses into itself.
    if name.startswith("_") and name not in _DUNDER_EXPORTS:
        raise AttributeError(name)
    if name in _ADDON_EXPORTS:
        raise AttributeError(name)
    public_api = _public_api_module()
    if name in public_api.__all__:
        return getattr(public_api, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> List[str]:
    names = set(globals()) | set(_ADDON_EXPORTS) | {"__all__"}
    try:
        names |= set(_public_api_module().__all__)
    except Exception:  # noqa: BLE001 - Blender must never fail listing a module
        pass
    return sorted(names)


def _bind_ui_control_to_host_process() -> None:
    """Fail closed unless UI control is scoped to this Blender process."""
    current_process_id = os.getpid()
    configured = os.environ.get(_UI_CONTROL_PROCESS_ID_ENV, "").strip()
    if configured:
        try:
            configured_process_id = int(configured, 10)
        except ValueError as exc:
            raise RuntimeError(f"Invalid {_UI_CONTROL_PROCESS_ID_ENV}={configured!r}") from exc
        if configured_process_id != current_process_id:
            raise RuntimeError(
                f"{_UI_CONTROL_PROCESS_ID_ENV} must identify the current Blender process "
                f"({current_process_id}), got {configured_process_id}"
            )
    os.environ[_UI_CONTROL_PROCESS_ID_ENV] = str(current_process_id)


def _restore_isolated_pythonpath() -> None:
    """Re-expose launcher-injected ``PYTHONPATH`` entries inside Blender.

    Blender 5.x starts its embedded interpreter with an isolated configuration
    that never reads ``PYTHONPATH``, so dependencies supplied by a studio
    package manager are invisible from inside the host and the add-on would
    fail on its first adapter import. The environment is still readable, so the
    directories are restored here — a no-op on hosts that honour ``PYTHONPATH``.
    """
    try:
        repair = _addon_module("_isolated_path").repair_sys_path
    except Exception as exc:  # noqa: BLE001
        logger.debug("PYTHONPATH restore unavailable: %s", exc)
        return
    try:
        restored = repair()
    except Exception as exc:  # noqa: BLE001
        logger.debug("PYTHONPATH restore failed: %s", exc)
        return
    # The repair can expose a resolved distribution that was invisible when this
    # entry point loaded, so the package resolution has to be recomputed.
    _reset_canonical_package()
    if restored:
        print(f"{_ECHO_PREFIX} Restored {len(restored)} PYTHONPATH entries ignored by isolated Blender Python")


def _env_port(name: str, default: int) -> int:
    """Read a TCP port while preserving zero as the random-port request."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        port = int(raw, 10)
    except ValueError:
        logger.warning("Ignoring invalid %s=%r", name, raw)
        return default
    if not 0 <= port <= 65535:
        logger.warning("Ignoring out-of-range %s=%r", name, raw)
        return default
    return port


def _start_server_with_host():
    """Start the MCP server with a Blender main-thread dispatcher attached."""
    global _server_dispatcher, _server_host  # noqa: PLW0603

    _bind_ui_control_to_host_process()
    _restore_isolated_pythonpath()
    _install_runtime_import_aliases()
    try:
        # The release ZIP replaces the library package entrypoint with this
        # Blender add-on entrypoint. Enforce the same compatibility contract
        # before importing host/server modules that bind dcc-mcp-core.
        _addon_module("_core_compat").require_compatible_core()
        host = _addon_module("host")
        server_module = _addon_module("server")
        BlenderUiDispatcher = host.BlenderUiDispatcher
        get_server = server_module.get_server
        start_server = server_module.start_server
        stop_server = server_module.stop_server

        existing = get_server()
        if existing is not None and getattr(existing, "is_running", False):
            if _server_host is not None:
                return existing
            stop_server()

        dispatcher = BlenderUiDispatcher()
        try:
            server = start_server(
                gateway_port=_env_port("DCC_MCP_GATEWAY_PORT", _DEFAULT_GATEWAY_PORT),
                registry_dir=os.environ.get("DCC_MCP_REGISTRY_DIR") or None,
                dispatcher=dispatcher,
            )
            dispatcher.start()
        except Exception:
            with suppress(Exception):
                stop_server()
            with suppress(Exception):
                dispatcher.stop()
            raise

        _server_dispatcher = dispatcher
        _server_host = dispatcher
        return server
    except Exception:
        _remove_runtime_import_aliases()
        raise


def _stop_server_with_host() -> None:
    """Stop the MCP server and detach the Blender timer/dispatcher."""
    global _server_dispatcher, _server_host  # noqa: PLW0603

    host = _server_host
    try:
        _addon_module("server").stop_server()
    finally:
        if host is not None:
            with suppress(Exception):
                host.stop()
        _server_host = None
        _server_dispatcher = None


def _running_server():
    try:
        return _addon_module("server").get_server()
    except Exception as exc:  # noqa: BLE001
        logger.debug("get_server failed: %s", exc)
        return None


def _mcp_url() -> str:
    srv = _running_server()
    if srv is None:
        return ""
    url = getattr(srv, "mcp_url", None)
    return url or ""


def _http_base() -> str:
    url = _mcp_url()
    if not url:
        return ""
    return url.replace("/mcp", "").rstrip("/")


def _gateway_base() -> str:
    raw = os.environ.get("DCC_MCP_GATEWAY_PORT", str(_DEFAULT_GATEWAY_PORT)).strip()
    if not raw.isdigit():
        return ""
    port = int(raw, 10)
    if port <= 0:
        return ""
    return f"http://127.0.0.1:{port}"


class DCCMCP_OT_open_mcp(bpy.types.Operator):
    bl_idname = "dcc_mcp.open_mcp_endpoint"
    bl_label = "Open MCP Endpoint"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context) -> bool:
        return bool(_mcp_url())

    def execute(self, context):
        url = _mcp_url()
        if url:
            webbrowser.open(url)
            self.report({"INFO"}, f"Opened {url}")
        return {"FINISHED"}


class DCCMCP_OT_open_openapi(bpy.types.Operator):
    bl_idname = "dcc_mcp.open_openapi_docs"
    bl_label = "OpenAPI Docs"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context) -> bool:
        return bool(_http_base())

    def execute(self, context):
        base = _http_base()
        if base:
            webbrowser.open(base + "/docs")
            self.report({"INFO"}, "Opened /docs")
        return {"FINISHED"}


class DCCMCP_OT_open_admin(bpy.types.Operator):
    bl_idname = "dcc_mcp.open_admin_panel"
    bl_label = "Gateway Admin"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context) -> bool:
        return bool(_gateway_base())

    def execute(self, context):
        gw = _gateway_base()
        if gw:
            webbrowser.open(gw + "/admin")
            self.report({"INFO"}, "Opened gateway /admin")
        return {"FINISHED"}


class DCCMCP_OT_open_metrics(bpy.types.Operator):
    bl_idname = "dcc_mcp.open_metrics"
    bl_label = "Prometheus Metrics"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context) -> bool:
        return bool(_http_base())

    def execute(self, context):
        base = _http_base()
        if base:
            webbrowser.open(base + "/metrics")
            self.report({"INFO"}, "Opened /metrics")
        return {"FINISHED"}


class DCCMCP_OT_show_urls(bpy.types.Operator):
    bl_idname = "dcc_mcp.show_server_urls"
    bl_label = "Show Server URLs…"
    bl_options = {"REGISTER"}

    def execute(self, context):
        srv = _running_server()
        lines: List[str] = []
        if srv is None:
            lines.append("MCP server is not running.")
        else:
            url = getattr(srv, "mcp_url", None) or "<unknown>"
            lines.append(f"MCP: {url}")
            gw = getattr(srv, "gateway_url", None)
            if gw:
                lines.append(f"Gateway: {gw}")
            lines.append("Instances: MCP resources/read uri=gateway://instances")

        def draw(menu, ctx):
            col = menu.layout.column(align=True)
            for line in lines:
                col.label(text=line)

        context.window_manager.popup_menu(draw, title="DCC MCP Blender")
        return {"FINISHED"}


class DCCMCP_OT_restart(bpy.types.Operator):
    bl_idname = "dcc_mcp.restart_server"
    bl_label = "Restart MCP Server"
    bl_options = {"REGISTER"}

    def execute(self, context):
        try:
            _stop_server_with_host()
            _start_server_with_host()
            self.report({"INFO"}, "MCP server restarted")
        except Exception as exc:  # noqa: BLE001
            logger.exception("restart failed")
            self.report({"ERROR"}, str(exc))
        return {"FINISHED"}


class DCCMCP_OT_toggle_hot_reload(bpy.types.Operator):
    bl_idname = "dcc_mcp.toggle_hot_reload"
    bl_label = "Toggle Skill Hot-Reload"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context) -> bool:
        return _running_server() is not None

    def execute(self, context):
        srv = _running_server()
        if srv is None:
            return {"CANCELLED"}
        try:
            if srv.is_hot_reload_enabled:
                srv.disable_hot_reload()
                self.report({"INFO"}, "Hot-reload disabled")
            else:
                if srv.enable_hot_reload():
                    self.report({"INFO"}, "Hot-reload enabled")
                else:
                    self.report({"WARNING"}, "Could not enable hot-reload")
        except Exception as exc:  # noqa: BLE001
            self.report({"ERROR"}, str(exc))
        return {"FINISHED"}


class DCCMCP_OT_copy_instance_id(bpy.types.Operator):
    bl_idname = "dcc_mcp.copy_instance_id"
    bl_label = "Copy Instance ID"
    bl_description = "Copy the DCC instance UUID to the clipboard"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context) -> bool:
        return _running_server() is not None

    def execute(self, context):
        srv = _running_server()
        instance_id = None
        if srv is not None:
            # Resolve instance_id following the same chain as _extract_instance_id
            instance_id = getattr(srv, "instance_id", None)
            if not instance_id:
                cfg = getattr(srv, "_config", None)
                instance_id = getattr(cfg, "instance_id", None) if cfg is not None else None
            if not instance_id:
                handle = getattr(srv, "_handle", None)
                instance_id = getattr(handle, "instance_id", None) if handle is not None else None
        if instance_id:
            bpy.context.window_manager.clipboard = str(instance_id)
            self.report({"INFO"}, f"Instance ID copied: {instance_id}")
        else:
            self.report({"WARNING"}, "Instance ID not available — is the server fully started?")
        return {"FINISHED"}


class DCCMCP_OT_server_info(bpy.types.Operator):
    bl_idname = "dcc_mcp.show_server_info"
    bl_label = "Server Info"
    bl_description = "Show DCC MCP server status and connection details"
    bl_options = {"REGISTER"}

    def execute(self, context):
        srv = _running_server()

        # Gather instance identity
        instance_id = None
        if srv is not None:
            instance_id = getattr(srv, "instance_id", None)
            if not instance_id:
                cfg = getattr(srv, "_config", None)
                instance_id = getattr(cfg, "instance_id", None) if cfg is not None else None
            if not instance_id:
                handle = getattr(srv, "_handle", None)
                instance_id = getattr(handle, "instance_id", None) if handle is not None else None

        # Gather URLs
        mcp_url = _mcp_url() or "<not running>"
        gw = None
        if srv is not None:
            gw = getattr(srv, "gateway_url", None)
        gateway_url = gw or "<no gateway>"

        # Gather ports
        server_port = None
        if srv is not None:
            server_port = getattr(srv, "port", None)
        gateway_port = os.environ.get("DCC_MCP_GATEWAY_PORT", str(_DEFAULT_GATEWAY_PORT)).strip()

        # Gather versions
        try:
            import bpy as _bpy

            blender_version = _bpy.app.version_string
        except Exception:
            blender_version = "unknown"

        core_version = None
        try:
            from dcc_mcp_core.server_base import _package_version

            core_version = _package_version()
        except Exception:
            core_version = "unknown"

        lines: List[str] = [
            f"Instance ID:  {instance_id or '<not available>'}",
            f"Blender:      {blender_version}",
            f"Core:         {core_version}",
            f"MCP URL:      {mcp_url}",
            f"Gateway:      {gateway_url}",
        ]
        if server_port is not None:
            lines.insert(4, f"Server Port:  {server_port}")
        lines.insert(6, f"Gateway Port: {gateway_port}")

        def draw(menu, ctx):
            col = menu.layout.column(align=True)
            for line in lines:
                col.label(text=line)

        context.window_manager.popup_menu(draw, title="DCC MCP Server Info")
        return {"FINISHED"}


class DCCMCP_OT_about(bpy.types.Operator):
    bl_idname = "dcc_mcp.about"
    bl_label = "About DCC MCP"
    bl_description = "Show DCC MCP version and project information"
    bl_options = {"REGISTER"}

    def execute(self, context):
        addon_version = ".".join(str(x) for x in bl_info["version"])

        # Try to resolve dcc-mcp-core version
        core_version = None
        try:
            from dcc_mcp_core.server_base import _package_version

            core_version = _package_version()
        except Exception:
            core_version = "unknown"

        lines: List[str] = [
            f"Add-on:   dcc-mcp-blender {addon_version}",
            f"Core:     dcc-mcp-core {core_version}",
            "Protocol: MCP Streamable HTTP (2025-03-26)",
            "",
            f"Author:   {bl_info['author']}",
            f"Docs:     {bl_info['doc_url']}",
        ]

        def draw(menu, ctx):
            col = menu.layout.column(align=True)
            for line in lines:
                if line:
                    col.label(text=line)
                else:
                    col.separator()

        context.window_manager.popup_menu(draw, title="About DCC MCP")
        return {"FINISHED"}


class DCCMCP_MT_main_menu(bpy.types.Menu):
    bl_label = "DCC MCP"
    bl_idname = "DCCMCP_MT_main_menu"

    def draw(self, context):
        layout = self.layout.column(align=True)
        layout.operator("dcc_mcp.copy_instance_id", icon="COPYDOWN")
        layout.separator()
        layout.operator("dcc_mcp.show_server_info", icon="INFO")
        layout.separator()
        layout.operator("dcc_mcp.open_mcp_endpoint", icon="URL")
        layout.operator("dcc_mcp.open_openapi_docs", icon="DOCUMENTS")
        layout.operator("dcc_mcp.open_metrics", icon="GRAPH")
        layout.separator()
        layout.operator("dcc_mcp.open_admin_panel", icon="SETTINGS")
        layout.separator()
        layout.operator("dcc_mcp.restart_server", icon="FILE_REFRESH")
        layout.operator("dcc_mcp.toggle_hot_reload", icon="FILE_CACHE")
        layout.separator()
        layout.operator("dcc_mcp.about", icon="BLANK1")


def _draw_topbar_menu(self, context):
    self.layout.menu(DCCMCP_MT_main_menu.bl_idname, text="DCC MCP")


_CLASSES = (
    DCCMCP_OT_open_mcp,
    DCCMCP_OT_open_openapi,
    DCCMCP_OT_open_admin,
    DCCMCP_OT_open_metrics,
    DCCMCP_OT_show_urls,
    DCCMCP_OT_restart,
    DCCMCP_OT_toggle_hot_reload,
    DCCMCP_OT_copy_instance_id,
    DCCMCP_OT_server_info,
    DCCMCP_OT_about,
    DCCMCP_MT_main_menu,
)


def register() -> None:
    global _draw_handlers  # noqa: PLW0603

    # Version and provenance self-checks run before anything is registered: a
    # server started on a stale core is worse than an add-on that refuses to
    # load, because the first one produces plausible but wrong evidence.
    _restore_isolated_pythonpath()
    _addon_module("_core_compat").require_compatible_core()
    # Gate the package that will actually serve, not the public name: when the
    # extension keeps control (its copy is newer than the resolve) the runtime
    # runs from ``bl_ext.<repository>.dcc_mcp_blender``, and the public name is
    # only bridged onto it later, in ``_start_server_with_host()``. Checking
    # ``dcc_mcp_blender`` here would inspect the distribution on ``sys.path`` --
    # or skip the check entirely when there is none -- and let the extension
    # copy serve from outside a declared root without ever being examined.
    _addon_module("_provenance").require_expected_origin(
        names=(_resolve_canonical_package(), "dcc_mcp_core"),
        echo=True,
    )

    for cls in _CLASSES:
        bpy.utils.register_class(cls)

    if hasattr(bpy.types, "TOPBAR_MT_blender"):
        bpy.types.TOPBAR_MT_blender.append(_draw_topbar_menu)
        _draw_handlers.append(("TOPBAR_MT_blender", _draw_topbar_menu))
    else:
        logger.warning("TOPBAR_MT_blender missing — DCC MCP top-bar menu not attached")

    if os.environ.get(_BACKGROUND_RENDER_ENV, "").strip().lower() in {"1", "true", "yes", "on"}:
        print("[DCC MCP Blender] Background render worker detected; server autostart skipped")
        return

    from dcc_mcp_core import capture_bootstrap_errors

    try:
        with capture_bootstrap_errors(
            "blender",
            adapter_version=__addon_version__,
            min_core_version="0.20.0",
            phase="startup",
        ):
            srv = _start_server_with_host()
            url = getattr(srv, "mcp_url", None) if srv is not None else None
            if url:
                print("[DCC MCP Blender] Server started —", url)
            else:
                print("[DCC MCP Blender] Server start requested (URL not yet available)")
    except Exception as exc:  # noqa: BLE001
        print(f"[DCC MCP Blender] Failed to start server: {exc}")
        raise


def unregister() -> None:
    global _draw_handlers  # noqa: PLW0603
    for target, fn in reversed(_draw_handlers):
        menu = getattr(bpy.types, target, None)
        if menu is not None and fn is not None:
            try:
                menu.remove(fn)
            except Exception as exc:  # noqa: BLE001
                logger.debug("menu remove %s: %s", target, exc)
    _draw_handlers.clear()

    for cls in reversed(_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception as exc:  # noqa: BLE001
            logger.debug("unregister %s: %s", cls, exc)

    try:
        _stop_server_with_host()
        print("[DCC MCP Blender] Server stopped")
    except Exception as exc:  # noqa: BLE001
        print(f"[DCC MCP Blender] Failed to stop server: {exc}")
    finally:
        # Keep the public import bridge installed: Blender disables add-ons on
        # ``wm.read_factory_settings``, and batch scripts import
        # ``dcc_mcp_blender`` immediately afterwards.
        _detach_runtime_import_aliases()


# Deliberately no import-time install of the public import bridge. Blender
# imports every add-on module just to read ``bl_info``, long before a package
# environment is on ``sys.path``: resolving the canonical package here would
# cache a premature decision (pinning the runtime to this extension copy and so
# defeating the handover to a newer resolved distribution) and would echo a
# provenance warning against whatever stale copy happens to be importable at
# scan time. ``register()`` installs the bridge once the host is real, and
# ``unregister()`` detaches rather than uninstalls it, which is what keeps
# ``import dcc_mcp_blender`` working after ``wm.read_factory_settings``.

__addon_version__ = "0.2.12"  # x-release-please-version
