"""Native query-to-edit preconditions and post-edit invalidation on real meshes."""

from __future__ import annotations

import pytest

bpy = pytest.importorskip("bpy", reason="Requires native Blender")
pytestmark = pytest.mark.e2e

from tests.e2e.conftest import load_skill  # noqa: E402

EDITS = [
    ("extrude_faces", {"face_indices": [0], "distance": 0.25}),
    ("bevel_edges", {"edge_indices": [0], "width": 0.1}),
    ("inset", {"face_indices": [0], "thickness": 0.1}),
    ("add_edge_loop", {"edge_indices": [0], "cuts": 1}),
]


def _selection(obj):
    return {
        "active": bpy.context.view_layer.objects.active.as_pointer(),
        "objects": [item.as_pointer() for item in bpy.context.selected_objects],
        "mode": obj.mode,
        "vertex": [item.select for item in obj.data.vertices],
        "edge": [item.select for item in obj.data.edges],
        "face": [item.select for item in obj.data.polygons],
    }


@pytest.mark.parametrize(("tool_name", "arguments"), EDITS)
def test_fresh_revision_allows_edit_then_rejects_old_indices_without_context_changes(tool_name, arguments):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.object
    query = load_skill("blender-mesh-ops", "inspect_mesh_components")
    edit = load_skill("blender-mesh-ops", tool_name)
    before = query.main(object_name=obj.name)
    assert before["success"], before
    revision = before["context"]["revision"]

    result = edit.main(object_name=obj.name, expected_revision=revision, **arguments)
    assert result["success"], result
    assert result["context"]["parameters"]["expected_revision"] == revision
    assert result["context"]["readback"]["verified"] is True
    after = query.main(object_name=obj.name)
    assert after["success"], after
    assert after["context"]["revision"] != revision
    assert after["context"]["counts"]["vertex"] > before["context"]["counts"]["vertex"]

    selection_before = _selection(obj)
    stale = edit.main(object_name=obj.name, expected_revision=revision, **arguments)
    assert not stale["success"], stale
    assert stale["context"]["error_code"] == "stale_mesh_revision"
    assert stale["context"]["mutation_applied"] is False
    assert _selection(obj) == selection_before
    unchanged = query.main(object_name=obj.name, expected_revision=after["context"]["revision"])
    assert unchanged["success"], unchanged
    assert unchanged["context"]["counts"] == after["context"]["counts"]


def test_guard_rejection_preserves_an_explicit_edit_mode():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.object
    query = load_skill("blender-mesh-ops", "inspect_mesh_components")
    revision = query.main(object_name=obj.name)["context"]["revision"]
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        result = load_skill("blender-mesh-ops", "extrude_faces").main(
            object_name=obj.name, face_indices=[0], distance=0.25, expected_revision=revision
        )
        assert not result["success"], result
        assert result["context"]["error_code"] == "mesh_revision_mode_required"
        assert result["context"]["mutation_applied"] is False
        assert obj.mode == "EDIT"
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
    assert len(obj.data.polygons) == 6
