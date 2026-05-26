"""Unit tests for blender-dev skill scripts."""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace

from tests.conftest import load_and_call, make_mock_bpy


class _Spaces(list):
    pass


def _install_fake_addon_utils(monkeypatch, enabled=False):
    addon = types.ModuleType("fake_addon")
    addon.__file__ = "/addons/fake_addon.py"
    addon.bl_info = {
        "name": "Fake Addon",
        "version": (1, 2, 3),
        "category": "Development",
        "description": "Fake diagnostics add-on",
    }
    state = {"enabled": enabled, "loaded": enabled}
    addon_utils = types.ModuleType("addon_utils")
    addon_utils.modules = lambda refresh=False: [addon]
    addon_utils.check = lambda name: (state["loaded"], state["enabled"]) if name == "fake_addon" else (False, False)
    addon_utils.module_bl_info = lambda module: getattr(module, "bl_info", {})
    monkeypatch.setitem(sys.modules, "addon_utils", addon_utils)
    return state


class TestDevPathAndReload:
    def test_attach_project_adds_existing_path(self, tmp_path, monkeypatch):
        original_path = list(sys.path)
        monkeypatch.setattr(sys, "path", list(original_path))

        result = load_and_call(
            "blender-dev/scripts/attach_project.py",
            make_mock_bpy(),
            project_root=str(tmp_path),
        )

        assert result["success"] is True
        assert str(tmp_path.resolve()) in result["context"]["added"]
        assert sys.path[0] == str(tmp_path.resolve())

    def test_reload_modules_reloads_loaded_module(self):
        result = load_and_call(
            "blender-dev/scripts/reload_modules.py",
            make_mock_bpy(),
            module_names=["json"],
        )

        assert result["success"] is True
        assert "json" in result["context"]["reloaded"] or "json" in result["context"]["imported"]


class TestDevChecks:
    def test_run_check_reports_unknown_command(self):
        result = load_and_call(
            "blender-dev/scripts/run_check.py",
            make_mock_bpy(),
            command_name="missing",
        )

        assert result["success"] is False
        assert "available" in result["context"]

    def test_run_check_timeout_returns_failure_envelope(self):
        result = load_and_call(
            "blender-dev/scripts/run_check.py",
            make_mock_bpy(),
            command_name="sleep",
            args={"seconds": 0.2},
            timeout_secs=0.01,
        )

        assert result["success"] is False
        assert result["context"]["command_name"] == "sleep"
        assert "timed out" in result["message"].lower()

    def test_run_check_import_module_succeeds(self):
        result = load_and_call(
            "blender-dev/scripts/run_check.py",
            make_mock_bpy(),
            command_name="import_module",
            args={"module": "json"},
        )

        assert result["success"] is True
        assert result["context"]["module"] == "json"


class TestDevEntrypoints:
    def test_run_entrypoint_calls_function_with_args(self):
        result = load_and_call(
            "blender-dev/scripts/run_entrypoint.py",
            make_mock_bpy(),
            module="math",
            function="pow",
            args=[2, 3],
        )

        assert result["success"] is True
        assert result["context"]["result"] == 8.0

    def test_run_script_returns_stdout_and_result(self, tmp_path):
        script = tmp_path / "check.py"
        script.write_text("print('dev check')\nresult = {'ok': True, 'args': ARGS}\n", encoding="utf-8")

        result = load_and_call(
            "blender-dev/scripts/run_script.py",
            make_mock_bpy(),
            path=str(script),
            args=["--quick"],
        )

        assert result["success"] is True
        assert "dev check" in result["context"]["stdout"]
        assert result["context"]["result"]["ok"] is True


class TestAddonDiagnostics:
    def test_get_addon_status_returns_structured_state(self, monkeypatch):
        _install_fake_addon_utils(monkeypatch, enabled=True)

        result = load_and_call(
            "blender-dev/scripts/get_addon_status.py",
            make_mock_bpy(),
            addon_module="fake_addon",
        )

        assert result["success"] is True
        assert result["context"]["installed"] is True
        assert result["context"]["enabled"] is True
        assert result["context"]["name"] == "Fake Addon"

    def test_enable_addon_returns_before_after_state(self, monkeypatch):
        state = _install_fake_addon_utils(monkeypatch, enabled=False)
        bpy = make_mock_bpy()

        def _enable(module):
            assert module == "fake_addon"
            state.update({"enabled": True, "loaded": True})

        bpy.ops.preferences.addon_enable.side_effect = _enable

        result = load_and_call(
            "blender-dev/scripts/enable_addon.py",
            bpy,
            addon_module="fake_addon",
        )

        assert result["success"] is True
        assert result["context"]["before"]["enabled"] is False
        assert result["context"]["after"]["enabled"] is True

    def test_disable_addon_returns_before_after_state(self, monkeypatch):
        state = _install_fake_addon_utils(monkeypatch, enabled=True)
        bpy = make_mock_bpy()

        def _disable(module):
            assert module == "fake_addon"
            state.update({"enabled": False, "loaded": False})

        bpy.ops.preferences.addon_disable.side_effect = _disable

        result = load_and_call(
            "blender-dev/scripts/disable_addon.py",
            bpy,
            addon_module="fake_addon",
        )

        assert result["success"] is True
        assert result["context"]["before"]["enabled"] is True
        assert result["context"]["after"]["enabled"] is False

    def test_list_addons_filters_by_name(self, monkeypatch):
        _install_fake_addon_utils(monkeypatch, enabled=True)

        result = load_and_call(
            "blender-dev/scripts/list_addons.py",
            make_mock_bpy(),
            filter="fake",
        )

        assert result["success"] is True
        assert result["context"]["count"] == 1
        assert result["context"]["addons"][0]["addon_module"] == "fake_addon"


class TestUiDiagnostics:
    def test_capture_ui_snapshot_returns_structured_metadata(self):
        bpy = make_mock_bpy(app_attrs={"background": False})
        spaces = _Spaces([SimpleNamespace(type="VIEW_3D")])
        spaces.active = spaces[0]
        area = SimpleNamespace(type="VIEW_3D", regions=[SimpleNamespace(type="WINDOW")], spaces=spaces)
        screen = SimpleNamespace(name="Layout", areas=[area])
        bpy.data.screens = [screen]
        bpy.context.window_manager.windows = [SimpleNamespace(screen=screen)]

        result = load_and_call("blender-dev/scripts/capture_ui_snapshot.py", bpy)

        assert result["success"] is True
        assert result["context"]["window_count"] == 1
        assert result["context"]["screens"][0]["areas"][0]["area_type"] == "VIEW_3D"

    def test_find_ui_elements_searches_structured_metadata(self):
        bpy = make_mock_bpy(app_attrs={"background": False})
        spaces = _Spaces([SimpleNamespace(type="NODE_EDITOR")])
        spaces.active = spaces[0]
        area = SimpleNamespace(type="NODE_EDITOR", regions=[SimpleNamespace(type="WINDOW")], spaces=spaces)
        bpy.data.screens = [SimpleNamespace(name="Compositing", areas=[area])]

        result = load_and_call("blender-dev/scripts/find_ui_elements.py", bpy, query="node")

        assert result["success"] is True
        assert result["context"]["count"] >= 1


class TestEnvironmentDiagnostics:
    def test_get_python_environment_reports_blender_context(self):
        bpy = make_mock_bpy(app_attrs={"version_string": "4.4.3", "background": True})

        result = load_and_call(
            "blender-dev/scripts/get_python_environment.py",
            bpy,
            include_sys_path=False,
        )

        assert result["success"] is True
        assert result["context"]["blender"]["version"] == "4.4.3"
        assert "sys_path" not in result["context"]
