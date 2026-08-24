"""Blender add-on / extension entry for DCC MCP Blender.

Shipped at the root of the add-on folder next to ``blender_manifest.toml``.
Keeps ``bl_info`` for legacy ``scripts/addons`` installs and supplies the
extension manifest for Blender 4.2+ extension workflows.
"""

from __future__ import annotations

import importlib
import logging
import os
import webbrowser
from contextlib import suppress
from typing import Any, List, Tuple

import bpy

logger = logging.getLogger(__name__)

bl_info = {
    "name": "DCC MCP Blender",
    "author": "Long Hao",
    "version": (
        0,  # x-release-please-major
        2,  # x-release-please-minor
        2,  # x-release-please-patch
    ),
    "blender": (4, 2, 0),
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


def _addon_module(name: str):
    """Import a bundled module through the active add-on package namespace."""
    package = __package__ if (__package__ or "").startswith("bl_ext.") else "dcc_mcp_blender"
    return importlib.import_module(f"{package}.{name}")


def _install_runtime_import_aliases() -> None:
    """Expose public skill imports without mutating Blender's ``sys.path``."""
    global _runtime_import_aliases  # noqa: PLW0603
    package = __package__ or ""
    if not package.startswith("bl_ext.") or _runtime_import_aliases is not None:
        return
    installer = _addon_module("_extension_imports").install_extension_import_aliases
    _runtime_import_aliases = installer(package)


def _remove_runtime_import_aliases() -> None:
    global _runtime_import_aliases  # noqa: PLW0603
    aliases = _runtime_import_aliases
    _runtime_import_aliases = None
    if aliases is not None:
        aliases.uninstall()


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
        _remove_runtime_import_aliases()


__addon_version__ = "0.2.2"  # x-release-please-version
