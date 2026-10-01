"""E2E tests for blender-uv-ops skill.

Requires a real Blender Python interpreter.
"""

from __future__ import annotations

from math import isfinite

import pytest

bpy = pytest.importorskip("bpy", reason="bpy not available - run inside Blender Python interpreter")

pytestmark = pytest.mark.e2e

from dcc_mcp_blender import _uv_ops  # noqa: E402
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

    def test_uv_operators_preserve_named_layer_and_native_reopen(self, tmp_path):
        bpy.ops.mesh.primitive_cube_add()
        obj = bpy.context.active_object
        object_name = obj.name
        for edge in obj.data.edges:
            edge.use_seam = True
        original_name = obj.data.uv_layers.active.name
        sentinel_name = "UntouchedUV"
        obj.data.uv_layers.new(name=sentinel_name)
        for loop in obj.data.uv_layers[sentinel_name].data:
            loop.uv = (-2.5, 3.5)
        obj.data.uv_layers.active = obj.data.uv_layers[original_name]
        loop_count = len(obj.data.loops)

        operations = [
            (_uv_ops.project_uvs, {"method": "smart"}),
            (_uv_ops.project_uvs, {"method": "sphere"}),
            (_uv_ops.project_uvs, {"method": "cylinder"}),
            (_uv_ops.unwrap_uvs, {"method": "smart"}),
            (_uv_ops.unwrap_uvs, {"method": "angle_based"}),
            (_uv_ops.unwrap_uvs, {"method": "conformal"}),
            (_uv_ops.pack_uvs, {"margin": 0.004, "normalize": True}),
        ]
        for operation, arguments in operations:
            result = operation(object_name=object_name, **arguments)
            assert result["success"], result
            assert result["context"]["uv_map"] == original_name
            obj = bpy.data.objects[object_name]
            assert obj.mode == "OBJECT"
            coords = [tuple(loop.uv) for loop in obj.data.uv_layers[original_name].data]
            assert len(coords) == loop_count
            assert all(isfinite(value) for uv in coords for value in uv)
            assert [tuple(loop.uv) for loop in obj.data.uv_layers[sentinel_name].data] == [(-2.5, 3.5)] * loop_count

        assert result["context"]["normalized_coordinate_count"] == loop_count
        assert result["context"]["bounds"]["min"] == pytest.approx([0.004, 0.004])
        assert result["context"]["bounds"]["max"] == pytest.approx([0.996, 0.996])
        path = str(tmp_path / "uv-operator-roundtrip.blend")
        bpy.ops.wm.save_as_mainfile(filepath=path)
        bpy.ops.wm.open_mainfile(filepath=path)
        obj = bpy.data.objects[object_name]
        reopened = [tuple(loop.uv) for loop in obj.data.uv_layers[original_name].data]
        assert reopened == coords
        assert [tuple(loop.uv) for loop in obj.data.uv_layers[sentinel_name].data] == [(-2.5, 3.5)] * loop_count

    @pytest.mark.parametrize("operation", [_uv_ops.project_uvs, _uv_ops.unwrap_uvs, _uv_ops.pack_uvs])
    def test_uv_operator_rejects_edit_entry_before_mutation(self, operation):
        bpy.ops.mesh.primitive_cube_add()
        obj = bpy.context.active_object
        object_name = obj.name
        uv_before = [tuple(loop.uv) for loop in obj.data.uv_layers.active.data]
        bpy.ops.object.mode_set(mode="EDIT")
        arguments = {"method": "smart"} if operation is not _uv_ops.pack_uvs else {}
        result = operation(object_name=object_name, **arguments)
        assert result["success"] is False
        assert result["context"]["mutation_applied"] is False
        assert obj.mode == "EDIT"
        bpy.ops.object.mode_set(mode="OBJECT")
        assert [tuple(loop.uv) for loop in obj.data.uv_layers.active.data] == uv_before
