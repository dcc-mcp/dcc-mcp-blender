"""Blender add-on / extension entry for DCC MCP Blender.

Shipped at the root of the add-on folder next to ``blender_manifest.toml``.
Keeps ``bl_info`` for legacy ``scripts/addons`` installs and supplies the
extension manifest for Blender 4.2+ extension workflows.
"""

from __future__ import annotations

import logging
import os
import sys
import webbrowser
from contextlib import suppress
from typing import Any, List, Tuple

import bpy

# Do not mutate sys.path — Blender extensions forbid injecting the add-on root into
# sys.path (policy violation). Dependencies are loaded via blender_manifest.toml wheels.
_self_module = sys.modules.get(__name__)
if __name__ != "dcc_mcp_blender" and globals().get("__path__") is not None and _self_module is not None:
    sys.modules.setdefault("dcc_mcp_blender", _self_module)

logger = logging.getLogger(__name__)

bl_info = {
    "name": "DCC MCP Blender",
    "author": "Long Hao",
    "version": (0, 1, 5),
    "blender": (4, 2, 0),
    "location": "Top Bar > DCC MCP",
    "description": "Embeds an MCP HTTP server inside Blender for AI-driven 3D workflows",
    "category": "System",
    "doc_url": "https://github.com/dcc-mcp/dcc-mcp-blender",
    "tracker_url": "https://github.com/dcc-mcp/dcc-mcp-blender/issues",
}

_DEFAULT_GATEWAY_PORT = 9765

_draw_handlers: List[Tuple[str, object]] = []
_server_dispatcher: Any = None
_server_host: Any = None


def _start_server_with_host():
    """Start the MCP server with a Blender main-thread dispatcher attached."""
    global _server_dispatcher, _server_host  # noqa: PLW0603

    from dcc_mcp_blender.host import BlenderUiDispatcher  # noqa: PLC0415
    from dcc_mcp_blender.server import get_server, start_server, stop_server  # noqa: PLC0415

    existing = get_server()
    if existing is not None and getattr(existing, "is_running", False):
        if _server_host is not None:
            return existing
        stop_server()

    dispatcher = BlenderUiDispatcher()
    try:
        server = start_server(dispatcher=dispatcher)
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


def _stop_server_with_host() -> None:
    """Stop the MCP server and detach the Blender timer/dispatcher."""
    global _server_dispatcher, _server_host  # noqa: PLW0603

    host = _server_host
    try:
        from dcc_mcp_blender.server import stop_server  # noqa: PLC0415

        stop_server()
    finally:
        if host is not None:
            with suppress(Exception):
                host.stop()
        _server_host = None
        _server_dispatcher = None


def _running_server():
    try:
        from dcc_mcp_blender.server import get_server  # noqa: PLC0415

        return get_server()
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


class DCCMCP_MT_main_menu(bpy.types.Menu):
    bl_label = "DCC MCP"
    bl_idname = "DCCMCP_MT_main_menu"

    def draw(self, context):
        layout = self.layout.column(align=True)
        layout.operator("dcc_mcp.show_server_urls", icon="INFO")
        layout.separator()
        layout.operator("dcc_mcp.open_mcp_endpoint", icon="URL")
        layout.operator("dcc_mcp.open_openapi_docs", icon="DOCUMENTS")
        layout.operator("dcc_mcp.open_metrics", icon="GRAPH")
        layout.separator()
        layout.operator("dcc_mcp.open_admin_panel", icon="SETTINGS")
        layout.separator()
        layout.operator("dcc_mcp.restart_server", icon="FILE_REFRESH")
        layout.operator("dcc_mcp.toggle_hot_reload", icon="FILE_CACHE")


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

    try:
        srv = _start_server_with_host()
        url = getattr(srv, "mcp_url", None) if srv is not None else None
        if url:
            print("[DCC MCP Blender] Server started —", url)
        else:
            print("[DCC MCP Blender] Server start requested (URL not yet available)")
    except Exception as exc:  # noqa: BLE001
        print(f"[DCC MCP Blender] Failed to start server: {exc}")


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
