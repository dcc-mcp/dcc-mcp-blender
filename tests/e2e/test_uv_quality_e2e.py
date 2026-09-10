"""Real Blender UV audit and polygon-edge SVG export acceptance."""

from __future__ import annotations

from xml.etree import ElementTree

import pytest

bpy = pytest.importorskip("bpy")
pytestmark = pytest.mark.e2e

from tests.e2e.conftest import load_skill  # noqa: E402


def test_uv_quality_named_map_and_source_state(tmp_path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_plane_add()
    obj = bpy.context.object
    layer = obj.data.uv_layers.new(name="Named")
    for dst, src in zip(layer.data, obj.data.uv_layers[0].data):
        dst.uv = src.uv
    obj.data.uv_layers.active_index = 0
    active = bpy.context.view_layer.objects.active
    selected = list(bpy.context.selected_objects)
    coordinates = [tuple(v.uv) for v in layer.data]
    audit = load_skill("blender-uv-ops", "audit_uv_layout").audit_uv_layout
    export = load_skill("blender-uv-ops", "export_uv_layout").export_uv_layout
    report = audit([obj.name], uv_map="Named")
    assert report["success"], report
    assert report["context"]["passed"], report
    path = tmp_path / "named.svg"
    result = export([obj.name], str(path), uv_map="Named")
    assert result["success"], result
    assert result["context"]["edge_count"] == 4  # no tessellation diagonal
    ElementTree.parse(path)
    atlas = export([obj.name], str(tmp_path / "atlas.svg"), uv_map="Named", layout_mode="overlay")
    assert atlas["success"] and atlas["context"]["panel_count"] == 1
    assert atlas["context"]["edge_count"] == 4
    assert bpy.context.view_layer.objects.active == active
    assert list(bpy.context.selected_objects) == selected
    assert obj.data.uv_layers.active_index == 0
    assert [tuple(v.uv) for v in layer.data] == coordinates
    for item in layer.data:
        item.uv = (0, 0)
    result = audit([obj.name], uv_map="Named")
    assert result["context"]["issue_counts"]["degenerate_triangles"] == 2
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        assert not audit([obj.name])["success"]
        assert obj.mode == "EDIT"
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")


def test_real_triangle_stacks(tmp_path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mesh = bpy.data.meshes.new("Stacked")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (0, 1, 1)], [], [(0, 1, 2), (3, 4, 5)])
    obj = bpy.data.objects.new("Stacked", mesh)
    bpy.context.scene.collection.objects.link(obj)
    layer = mesh.uv_layers.new()
    for i, point in enumerate([(0, 0), (1, 0), (0, 1)] * 2):
        layer.data[i].uv = point
    audit = load_skill("blender-uv-ops", "audit_uv_layout").audit_uv_layout
    result = audit([obj.name])
    assert result["context"]["issue_counts"] == {"overlap_pairs": 1}
    assert audit([obj.name], allow_stacked=True)["context"]["passed"]


@pytest.mark.parametrize("tool", ["audit_uv_layout", "export_uv_layout"])
def test_shared_edit_mesh_rejected_without_flushing_uvs_or_exporting(tool, tmp_path):
    import bmesh

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_plane_add()
    editor = bpy.context.object
    alias = bpy.data.objects.new("SharedMeshAlias", editor.data)
    bpy.context.scene.collection.objects.link(alias)
    alias.select_set(False)
    bpy.ops.object.mode_set(mode="EDIT")
    path = tmp_path / "shared.svg"
    try:
        assert editor.mode == "EDIT" and alias.mode == "OBJECT"
        assert alias.data.is_editmode is True
        edit_mesh = bmesh.from_edit_mesh(editor.data)
        uv_layer = edit_mesh.loops.layers.uv.active
        assert uv_layer is not None
        loops = [loop for face in edit_mesh.faces for loop in face.loops]
        loops[0][uv_layer].uv = (0.25, 0.75)
        coordinates = [tuple(loop[uv_layer].uv) for loop in loops]
        active = bpy.context.view_layer.objects.active
        selected = list(bpy.context.selected_objects)
        arguments = {"object_names": [alias.name]}
        if tool == "export_uv_layout":
            arguments["output_path"] = str(path)

        result = load_skill("blender-uv-ops", tool).main(**arguments)

        assert result["success"] is False, result
        assert "OBJECT mode" in result["_meta"]["dcc.error"]["message"]
        assert editor.mode == "EDIT" and alias.mode == "OBJECT"
        assert alias.data.is_editmode is True
        assert bpy.context.view_layer.objects.active == active
        assert list(bpy.context.selected_objects) == selected
        assert [tuple(loop[uv_layer].uv) for loop in loops] == coordinates
        assert not path.exists()
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
