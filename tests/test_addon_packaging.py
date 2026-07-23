"""Regression tests for the packaged Blender add-on entrypoint."""

from __future__ import annotations

import ast
import importlib.util
import pathlib
import re
import sys
import zipfile
from types import SimpleNamespace

import pytest

ROOT = pathlib.Path(__file__).parent.parent
ADDON_ENTRY = ROOT / "packaging" / "addon_entry" / "__init__.py"


def _get_addon_version():
    """Extract the addon version from the __addon_version__ variable."""
    src = ADDON_ENTRY.read_text(encoding="utf-8")
    m = re.search(r'__addon_version__\s*=\s*"(\d+\.\d+\.\d+)"', src)
    assert m, "could not find __addon_version__ in packaging/addon_entry/__init__.py"
    return m.group(1)


def _parse_version_tuple(version_str: str):
    return tuple(int(x) for x in version_str.split("."))


def _load_assemble_zip_module():
    path = ROOT / "packaging" / "assemble_zip.py"
    spec = importlib.util.spec_from_file_location("assemble_zip_for_addon_tests", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _manifest_wheels(manifest: str):
    return re.findall(r'"\.\/(wheels\/dcc_mcp_core-[^"]+\.whl)"', manifest)


def _write_fake_core_wheel(path: pathlib.Path, members: tuple[str, ...] = ()) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("dcc_mcp_core/__init__.py", "")
        for member in members:
            archive.writestr(member, b"MZ")


def test_addon_entry_bl_info_version_is_static_tuple_literal():
    """Blender parses ``bl_info`` via AST, so version must not be computed."""
    tree = ast.parse(ADDON_ENTRY.read_text(encoding="utf-8"))
    bl_info = next(node for node in tree.body if isinstance(node, ast.Assign) and node.targets[0].id == "bl_info")
    version_node = next(
        value
        for key, value in zip(bl_info.value.keys, bl_info.value.values)
        if isinstance(key, ast.Constant) and key.value == "version"
    )

    assert isinstance(version_node, ast.Tuple)
    assert ast.literal_eval(version_node) == _parse_version_tuple(_get_addon_version())


def test_assembled_addon_zip_uses_flat_importable_package_layout(tmp_path, monkeypatch):
    """The add-on package root must directly contain ``server.py`` and skills."""
    assemble_zip = _load_assemble_zip_module()
    fake_wheel = tmp_path / "dcc_mcp_core-0.19.17-cp38-abi3-win_amd64.whl"
    _write_fake_core_wheel(fake_wheel)

    monkeypatch.setattr(assemble_zip, "resolve_core_version", lambda min_version="0.19.17": "0.19.17")
    monkeypatch.setattr(assemble_zip, "download_core_wheel", lambda version, platform, dest_dir: fake_wheel)

    zip_path = assemble_zip.assemble(platform="win64", output_dir=tmp_path)

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        addon_init = zf.read("__init__.py").decode("utf-8")
        manifest = zf.read("blender_manifest.toml").decode("utf-8")

    assert "__init__.py" in names
    assert "server.py" in names
    assert "host.py" in names
    assert "skills/blender-scene/SKILL.md" in names
    assert not any(name.startswith("dcc_mcp_blender/") for name in names)
    assert [name for name in sorted(names) if name.startswith("wheels/dcc_mcp_core-")] == [
        "wheels/dcc_mcp_core-0.19.17-cp38-abi3-win_amd64.whl"
    ]
    addon_tree = ast.parse(addon_init)
    addon_bl_info = next(
        node for node in addon_tree.body if isinstance(node, ast.Assign) and node.targets[0].id == "bl_info"
    )
    addon_version_node = next(
        value
        for key, value in zip(addon_bl_info.value.keys, addon_bl_info.value.values)
        if isinstance(key, ast.Constant) and key.value == "version"
    )
    assert isinstance(addon_version_node, ast.Tuple)
    assert ast.literal_eval(addon_version_node) == _parse_version_tuple(_get_addon_version())
    assert _manifest_wheels(manifest) == ["wheels/dcc_mcp_core-0.19.17-cp38-abi3-win_amd64.whl"]
    assert manifest.index("wheels = [") < manifest.index("[permissions]")

    start_server = next(
        node for node in addon_tree.body if isinstance(node, ast.FunctionDef) and node.name == "_start_server_with_host"
    )
    gate_call = next(
        node
        for node in ast.walk(start_server)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "require_compatible_core"
    )
    core_import_lines = [
        node.lineno
        for node in ast.walk(start_server)
        if isinstance(node, ast.ImportFrom) and node.module in {"dcc_mcp_blender.host", "dcc_mcp_blender.server"}
    ]
    assert core_import_lines
    assert gate_call.lineno < min(core_import_lines)


def test_validate_core_wheel_rejects_removed_capture_helper(tmp_path):
    assemble_zip = _load_assemble_zip_module()
    wheel = tmp_path / "dcc_mcp_core-0.19.63-cp38-abi3-win_amd64.whl"
    _write_fake_core_wheel(
        wheel,
        ("dcc_mcp_core/bin/dcc-mcp-capture-helper.exe",),
    )

    with pytest.raises(RuntimeError, match="removed capture helper"):
        assemble_zip.validate_core_wheel(wheel)


def test_validate_core_wheel_accepts_current_ui_control_host(tmp_path):
    assemble_zip = _load_assemble_zip_module()
    wheel = tmp_path / "dcc_mcp_core-0.19.69-cp38-abi3-win_amd64.whl"
    _write_fake_core_wheel(
        wheel,
        ("dcc_mcp_core/bin/dcc-mcp-ui-control-host.exe",),
    )

    assemble_zip.validate_core_wheel(wheel)


def test_assemble_rejects_core_wheel_with_removed_capture_helper(tmp_path, monkeypatch):
    assemble_zip = _load_assemble_zip_module()
    wheel = tmp_path / "dcc_mcp_core-0.19.63-cp38-abi3-win_amd64.whl"
    _write_fake_core_wheel(
        wheel,
        ("dcc_mcp_core/bin/dcc-mcp-capture-helper.exe",),
    )
    monkeypatch.setattr(assemble_zip, "resolve_core_version", lambda: "0.19.63")
    monkeypatch.setattr(
        assemble_zip,
        "download_core_wheel",
        lambda version, platform, dest_dir: wheel,
    )

    with pytest.raises(RuntimeError, match="removed capture helper"):
        assemble_zip.assemble(platform="win64", output_dir=tmp_path)


def test_addon_register_starts_server_with_core_backed_blender_ui_dispatcher(monkeypatch):
    """GUI add-on enable must wire the core-backed UI dispatcher before serving tools."""
    registered_classes = []
    menu_callbacks = []

    class _Menu:
        @staticmethod
        def append(fn):
            menu_callbacks.append(fn)

        @staticmethod
        def remove(fn):
            menu_callbacks.remove(fn)

    fake_bpy = SimpleNamespace(
        types=SimpleNamespace(Operator=object, Menu=object, TOPBAR_MT_blender=_Menu),
        utils=SimpleNamespace(
            register_class=lambda cls: registered_classes.append(cls),
            unregister_class=lambda cls: registered_classes.remove(cls),
        ),
    )

    spec = importlib.util.spec_from_file_location("addon_entry_for_tests", str(ADDON_ENTRY))
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "bpy", fake_bpy)
    spec.loader.exec_module(mod)

    import dcc_mcp_blender.host as host_mod
    import dcc_mcp_blender.server as server_mod

    calls = []

    class _Dispatcher:
        def start(self):
            calls.append(("dispatcher.start", self))

        def stop(self):
            calls.append(("dispatcher.stop", self))

    server = SimpleNamespace(is_running=True, mcp_url="http://127.0.0.1:8765/mcp")

    def _start_server(**kwargs):
        calls.append(("start_server", kwargs))
        return server

    monkeypatch.setattr(host_mod, "BlenderUiDispatcher", _Dispatcher)
    monkeypatch.setattr(server_mod, "get_server", lambda: None)
    monkeypatch.setattr(server_mod, "start_server", _start_server)
    monkeypatch.setattr(server_mod, "stop_server", lambda: calls.append(("stop_server", None)))
    monkeypatch.setenv("DCC_MCP_BLENDER_PORT", "18765")
    monkeypatch.setenv("DCC_MCP_GATEWAY_PORT", "19765")
    monkeypatch.setenv("DCC_MCP_REGISTRY_DIR", "/tmp/dcc-mcp-registry")

    mod.register()

    assert registered_classes == list(mod._CLASSES)
    assert len(menu_callbacks) == 1
    assert [call[0] for call in calls] == ["start_server", "dispatcher.start"]
    assert calls[0][1] == {
        "gateway_port": 19765,
        "registry_dir": "/tmp/dcc-mcp-registry",
        "dispatcher": calls[1][1],
    }

    mod.unregister()

    assert menu_callbacks == []
    assert registered_classes == []
    assert [call[0] for call in calls] == [
        "start_server",
        "dispatcher.start",
        "stop_server",
        "dispatcher.stop",
    ]


def test_addon_register_does_not_start_server_in_background_render_worker(monkeypatch):
    registered_classes = []

    class _Menu:
        @staticmethod
        def append(_fn):
            pass

        @staticmethod
        def remove(_fn):
            pass

    fake_bpy = SimpleNamespace(
        types=SimpleNamespace(Operator=object, Menu=object, TOPBAR_MT_blender=_Menu),
        utils=SimpleNamespace(
            register_class=lambda cls: registered_classes.append(cls),
            unregister_class=lambda cls: registered_classes.remove(cls),
        ),
    )
    spec = importlib.util.spec_from_file_location("addon_entry_background_render_test", str(ADDON_ENTRY))
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "bpy", fake_bpy)
    spec.loader.exec_module(mod)
    starts = []
    monkeypatch.setattr(mod, "_start_server_with_host", lambda: starts.append(True))
    monkeypatch.setenv("DCC_MCP_BACKGROUND_RENDER", "1")

    mod.register()

    assert registered_classes == list(mod._CLASSES)
    assert starts == []


def test_addon_register_skips_server_autostart_in_background_render_worker(monkeypatch):
    """Isolated render workers must not claim the interactive MCP endpoint."""
    registered_classes = []

    class _Menu:
        @staticmethod
        def append(_fn):
            pass

        @staticmethod
        def remove(_fn):
            pass

    fake_bpy = SimpleNamespace(
        types=SimpleNamespace(Operator=object, Menu=object, TOPBAR_MT_blender=_Menu),
        utils=SimpleNamespace(
            register_class=lambda cls: registered_classes.append(cls),
            unregister_class=lambda cls: registered_classes.remove(cls),
        ),
    )

    spec = importlib.util.spec_from_file_location("addon_entry_worker_test", str(ADDON_ENTRY))
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "bpy", fake_bpy)
    spec.loader.exec_module(mod)
    monkeypatch.setenv("DCC_MCP_BACKGROUND_RENDER", "1")
    monkeypatch.setattr(mod, "_start_server_with_host", lambda: (_ for _ in ()).throw(AssertionError("started")))

    mod.register()

    assert registered_classes == list(mod._CLASSES)
    mod.unregister()
    assert registered_classes == []
