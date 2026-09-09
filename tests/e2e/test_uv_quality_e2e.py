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
