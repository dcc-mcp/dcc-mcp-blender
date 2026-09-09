"""Public skill behavior for bounded, read-only mesh component discovery."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tests.conftest import load_and_call

SCRIPT = "blender-mesh-ops/scripts/inspect_mesh_components.py"


def mesh_host():
    """A small host boundary fixture with real collections and numeric values."""
    coordinates = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    mesh = SimpleNamespace(
        name="TriangleMesh",
        is_editmode=False,
        vertices=[SimpleNamespace(index=i, co=co, normal=(0.0, 0.0, 1.0)) for i, co in enumerate(coordinates)],
        edges=[SimpleNamespace(index=i, vertices=pair) for i, pair in enumerate([(0, 1), (1, 2), (2, 0)])],
        polygons=[SimpleNamespace(index=0, vertices=(0, 1, 2), normal=(0.0, 0.0, 1.0))],
        loops=[SimpleNamespace(vertex_index=i, edge_index=i) for i in range(3)],
    )
    obj = SimpleNamespace(name="Triangle", type="MESH", mode="OBJECT", data=mesh)
    return SimpleNamespace(data=SimpleNamespace(objects={obj.name: obj})), obj


def test_query_discovers_one_vertex_page_without_mutating_the_host():
    host, obj = mesh_host()
    result = load_and_call(SCRIPT, host, object_name=obj.name, component="vertex", limit=2)

    assert result["success"] is True
    context = result["context"]
    assert context["component"] == "vertex"
    assert context["coordinate_space"] == "local"
    assert context["mesh_source"] == "original"
    assert [record["index"] for record in context["records"]] == [0, 1]
    assert context["records"][0]["position"] == [0.0, 0.0, 0.0]
    assert context["records"][0]["normal"] == [0.0, 0.0, 1.0]
    assert context["next_offset"] == 2
    assert context["revision"].startswith("mesh-query-v1:")
    assert obj.mode == "OBJECT"
    assert len(obj.data.vertices) == 3


@pytest.mark.parametrize(
    ("component", "expected"),
    [
        ("vertex", {"position": [0.0, 0.0, 0.0], "edge_indices": [0, 2], "face_indices": [0]}),
        ("edge", {"position": [0.5, 0.0, 0.0], "vertex_indices": [0, 1], "face_indices": [0]}),
        ("face", {"position": [1 / 3, 1 / 3, 0.0], "vertex_indices": [0, 1, 2], "edge_indices": [0, 1, 2]}),
    ],
)
def test_query_returns_deterministic_component_geometry_and_connectivity(component, expected):
    host, obj = mesh_host()
    result = load_and_call(SCRIPT, host, object_name=obj.name, component=component, limit=1)

    assert result["success"] is True
    record = result["context"]["records"][0]
    for key, value in expected.items():
        assert record[key] == value
    assert record["connectivity_complete"] is True


def test_revision_pins_pages_and_rejects_even_small_coordinate_changes():
    host, obj = mesh_host()
    first = load_and_call(SCRIPT, host, object_name=obj.name, limit=1)["context"]
    second = load_and_call(
        SCRIPT, host, object_name=obj.name, offset=first["next_offset"], limit=1, expected_revision=first["revision"]
    )
    assert second["success"] is True
    assert second["context"]["revision"] == first["revision"]
    assert second["context"]["records"][0]["index"] == 1

    obj.data.vertices[0].co = (1e-12, 0.0, 0.0)
    stale = load_and_call(SCRIPT, host, object_name=obj.name, expected_revision=first["revision"])
    assert stale["success"] is False
    assert stale["context"]["error_code"] == "stale_mesh_revision"
    assert "records" not in stale["context"]
    assert stale["context"]["current_revision"] != first["revision"]


def test_geometric_filters_scan_component_indices_in_order_and_pin_followup_pages():
    host, obj = mesh_host()
    arguments = dict(
        object_name=obj.name,
        bounds_min=[-0.1, -0.1, -0.1],
        bounds_max=[0.1, 1.1, 0.1],
        normal_direction=[0.0, 0.0, 2.0],
        normal_min_dot=0.99,
        limit=1,
    )
    first = load_and_call(SCRIPT, host, **arguments)
    assert first["success"] is True
    context = first["context"]
    assert [item["index"] for item in context["records"]] == [0]
    followup = load_and_call(
        SCRIPT, host, **arguments, offset=context["next_offset"], expected_revision=context["revision"]
    )
    assert followup["success"] is True
    assert [item["index"] for item in followup["context"]["records"]] == [2]
    assert followup["context"]["next_offset"] is None

    obj.data.vertices[0].normal = (0.0, 0.0, -1.0)
    filtered = load_and_call(SCRIPT, host, **arguments)
    assert [item["index"] for item in filtered["context"]["records"]] == [2]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"limit": 257},
        {"limit": True},
        {"offset": -1},
        {"offset": 1.5},
        {"expected_revision": "wrong"},
        {"bounds_min": [0, 0, 0]},
        {"normal_direction": [0, 0, 0]},
        {"normal_min_dot": float("nan")},
        {"component": "edge", "normal_direction": [0, 0, 1]},
    ],
)
def test_invalid_queries_fail_without_component_records(kwargs):
    host, obj = mesh_host()
    result = load_and_call(SCRIPT, host, object_name=obj.name, **kwargs)
    assert result["success"] is False
    assert "records" not in result["context"]


def test_edit_mode_and_oversized_mesh_fail_without_partial_revision():
    host, obj = mesh_host()
    obj.mode = "EDIT"
    assert not load_and_call(SCRIPT, host, object_name=obj.name)["success"]
    obj.mode = "OBJECT"
    obj.data.loops = range(100_001)
    result = load_and_call(SCRIPT, host, object_name=obj.name)
    assert not result["success"]
    assert "revision" not in result["context"]
