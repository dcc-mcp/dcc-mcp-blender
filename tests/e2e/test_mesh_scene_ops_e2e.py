"""E2E tests for expanded Blender scene/object and mesh operation skills.

Requires a real Blender Python interpreter.
"""

from __future__ import annotations

import pytest

bpy = pytest.importorskip("bpy", reason="bpy not available - run inside Blender Python interpreter")

pytestmark = pytest.mark.e2e

from tests.e2e.conftest import load_skill  # noqa: E402


def _new_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


class TestMeshSceneOpsE2E:
    def setup_method(self):
        _new_scene()

    def test_scene_selection_visibility_bounds_and_mesh_mutation(self):
        bpy.ops.mesh.primitive_cube_add()
        cube_name = bpy.context.active_object.name

        rename_mod = load_skill("blender-objects", "rename_object")
        renamed = rename_mod.rename_object(object_name=cube_name, new_name="AgentCube")
        assert renamed["success"] is True

        selection_mod = load_skill("blender-objects", "set_selection")
        selection = selection_mod.set_selection(object_names=["AgentCube"])
        assert selection["success"] is True
        assert selection["context"]["selected"] == ["AgentCube"]

        bounds_mod = load_skill("blender-objects", "get_bounding_box")
        bounds = bounds_mod.get_bounding_box(object_name="AgentCube", world_space=True)
        assert bounds["success"] is True
        assert bounds["context"]["size"] == [2.0, 2.0, 2.0]

        visibility_mod = load_skill("blender-objects", "set_visibility")
        visibility = visibility_mod.set_visibility(object_name="AgentCube", visible=False, viewport=False, render=True)
        assert visibility["success"] is True
        assert bpy.data.objects["AgentCube"].hide_render is True

        count_mod = load_skill("blender-mesh-ops", "get_poly_count")
        before = count_mod.get_poly_count(object_name="AgentCube")
        assert before["success"] is True
        assert before["context"]["face_count"] == 6

        triangulate_mod = load_skill("blender-mesh-ops", "triangulate_mesh")
        triangulated = triangulate_mod.triangulate_mesh(object_name="AgentCube")
        assert triangulated["success"] is True

        after = count_mod.get_poly_count(object_name="AgentCube")
        assert after["success"] is True
        assert after["context"]["face_count"] == 12
        assert after["context"]["triangle_count"] == 12
