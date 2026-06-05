"""Regression tests for the packaged Blender add-on entrypoint."""

from __future__ import annotations

import ast
import importlib.util
import pathlib
import re
import sys
import zipfile
from types import SimpleNamespace

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
    fake_wheel = tmp_path / "dcc_mcp_core-0.18.2-cp38-abi3-win_amd64.whl"
    fake_wheel.write_bytes(b"fake wheel")

    monkeypatch.setattr(assemble_zip, "resolve_core_version", lambda min_version="0.18.2": "0.18.2")
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
    assert '"version": (%s)' % ", ".join(_get_addon_version().split(".")) in addon_init
    assert "./wheels/dcc_mcp_core-0.18.2-cp38-abi3-win_amd64.whl" in manifest
    assert manifest.index("wheels = [") < manifest.index("[permissions]")


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

    def _start_server(*, dispatcher):
        calls.append(("start_server", dispatcher))
        return server

    monkeypatch.setattr(host_mod, "BlenderUiDispatcher", _Dispatcher)
    monkeypatch.setattr(server_mod, "get_server", lambda: None)
    monkeypatch.setattr(server_mod, "start_server", _start_server)
    monkeypatch.setattr(server_mod, "stop_server", lambda: calls.append(("stop_server", None)))

    mod.register()

    assert registered_classes == list(mod._CLASSES)
    assert len(menu_callbacks) == 1
    assert [call[0] for call in calls] == ["start_server", "dispatcher.start"]
    assert calls[0][1] is calls[1][1]

    mod.unregister()

    assert menu_callbacks == []
    assert registered_classes == []
    assert [call[0] for call in calls] == [
        "start_server",
        "dispatcher.start",
        "stop_server",
        "dispatcher.stop",
    ]
