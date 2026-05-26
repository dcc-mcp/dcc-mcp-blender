"""E2E tests for blender-uv-ops skill.

Requires a real Blender Python interpreter.
"""

from __future__ import annotations

import pytest

bpy = pytest.importorskip("bpy", reason="bpy not available - run inside Blender Python interpreter")

pytestmark = pytest.mark.e2e

from tests.e2e.conftest import load_skill  # noqa: E402


def _new_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


class TestUvOpsE2E:
    def setup_method(self):
        _new_scene()

    def test_project_inspect_and_normalize_uvs(self):
        bpy.ops.mesh.primitive_cube_add()
        cube_name = bpy.context.active_object.name

        create_mod = load_skill("blender-uv-ops", "create_uv_map")
        create_result = create_mod.create_uv_map(object_name=cube_name, name="AgentUV")
        assert create_result["success"] is True

        project_mod = load_skill("blender-uv-ops", "project_uvs")
        project_result = project_mod.project_uvs(object_name=cube_name, method="cube", axis="z", margin=0.05)
        assert project_result["success"] is True

        info_mod = load_skill("blender-uv-ops", "get_uv_info")
        info_result = info_mod.get_uv_info(object_name=cube_name)
        assert info_result["success"] is True
        assert info_result["context"]["active_uv_map"] == "AgentUV"
        assert info_result["context"]["uv_coordinate_count"] > 0

        normalize_mod = load_skill("blender-uv-ops", "normalize_uvs")
        normalize_result = normalize_mod.normalize_uvs(object_name=cube_name, uv_map="AgentUV")
        assert normalize_result["success"] is True
        assert normalize_result["context"]["bounds"]["min"] == [0.0, 0.0]
        assert normalize_result["context"]["bounds"]["max"] == [1.0, 1.0]
