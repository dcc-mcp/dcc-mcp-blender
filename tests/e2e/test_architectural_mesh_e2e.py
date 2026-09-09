"""Real Blender geometry, positioning, and context preservation checks."""

import pytest

bpy = pytest.importorskip("bpy")
pytestmark = pytest.mark.e2e

from dcc_mcp_blender._architectural_mesh import create_pointed_arch  # noqa: E402


def test_solid_arch_depth_bounds_and_context():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_cube_add()
    active = bpy.context.active_object
    selected = list(bpy.context.selected_objects)
    result = create_pointed_arch("Portal", 2, 3, 1.5, 0.35, 0.8, location=(1, 2, 3))
    assert result["success"], result
    obj = bpy.data.objects["Portal"]
    bpy.context.view_layer.update()
    assert list(obj.dimensions) == pytest.approx([2.7, 0.8, 4.85])
    assert list(obj.location) == [1, 2, 3]
    assert result["context"]["world_bounds"][1] == pytest.approx([2, 2.8])
    assert bpy.context.active_object == active
    assert bpy.context.selected_objects == selected
    import bmesh

    mesh = bmesh.new()
    try:
        mesh.from_mesh(obj.data)
        assert all(edge.is_manifold for edge in mesh.edges)
        assert mesh.calc_volume(signed=True) > 0
    finally:
        mesh.free()
    duplicate = create_pointed_arch("Portal", 2, 3, 1.5, 0.35, 0.8)
    assert not duplicate["success"]
    assert bpy.data.objects["Portal"] == obj
