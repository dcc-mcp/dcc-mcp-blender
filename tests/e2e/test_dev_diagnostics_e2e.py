"""E2E tests for Blender development diagnostics."""

from __future__ import annotations

import pytest

bpy = pytest.importorskip("bpy", reason="bpy not available - run inside Blender Python interpreter")

pytestmark = pytest.mark.e2e

from tests.e2e.conftest import load_skill  # noqa: E402


class TestDevDiagnosticsE2E:
    def test_environment_addon_status_and_ui_snapshot(self):
        env_mod = load_skill("blender-dev", "get_python_environment")
        env_result = env_mod.get_python_environment(include_sys_path=False)
        assert env_result["success"] is True
        assert env_result["context"]["blender"]["version"]

        status_mod = load_skill("blender-dev", "get_addon_status")
        status_result = status_mod.get_addon_status(addon_module="io_scene_fbx")
        assert status_result["success"] is True
        assert status_result["context"]["addon_module"] == "io_scene_fbx"

        snapshot_mod = load_skill("blender-dev", "capture_ui_snapshot")
        snapshot_result = snapshot_mod.capture_ui_snapshot()
        assert snapshot_result["success"] is True
        assert "screens" in snapshot_result["context"]
