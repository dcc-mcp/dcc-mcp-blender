"""Native component coordinates, adjacency, paging and stale revision evidence."""

from __future__ import annotations

import pytest

bpy = pytest.importorskip("bpy", reason="Requires native Blender")
pytestmark = pytest.mark.e2e

from tests.e2e.conftest import load_skill  # noqa: E402


def test_cube_components_and_revision_pinned_pages():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.object
    query = load_skill("blender-mesh-ops", "inspect_mesh_components")
    first = query.main(object_name=obj.name, component="vertex", limit=4)
    assert first["success"], first
    context = first["context"]
    assert context["counts"] == {"vertex": 8, "edge": 12, "face": 6}
    assert len(context["records"]) == 4
    record = context["records"][0]
    assert record["position"] == list(obj.data.vertices[0].co)
    assert record["edge_count"] == 3
    second = query.main(object_name=obj.name, offset=context["next_offset"], expected_revision=context["revision"])
    assert second["success"], second
    assert [record["index"] for record in second["context"]["records"]] == [4, 5, 6, 7]
    assert second["context"]["next_offset"] is None
    faces = query.main(object_name=obj.name, component="face", normal_direction=[0, 0, 1], normal_min_dot=0.99)
    assert faces["success"], faces
    assert len(faces["context"]["records"]) == 1
    assert faces["context"]["records"][0]["vertex_count"] == 4
    edges = query.main(object_name=obj.name, component="edge", limit=1)
    assert edges["context"]["records"][0]["vertex_count"] == 2
    assert edges["context"]["records"][0]["face_count"] == 2
    obj.data.vertices[0].co.x += 0.125
    obj.data.update()
    stale = query.main(object_name=obj.name, expected_revision=context["revision"])
    assert not stale["success"]
    assert stale["context"]["error_code"] == "stale_mesh_revision"
    assert obj.mode == "OBJECT"
