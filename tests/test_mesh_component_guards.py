"""Revision-pinned modeling must reject outdated component indices before edits."""

import pytest
import yaml

from tests.conftest import SKILLS_ROOT, load_and_call
from tests.test_mesh_component_query import SCRIPT, mesh_host

EDITS = [
    ("extrude_faces", {"face_indices": [0], "distance": 0.25}),
    ("bevel_edges", {"edge_indices": [0], "width": 0.1}),
    ("inset", {"face_indices": [0], "thickness": 0.1}),
    ("add_edge_loop", {"edge_indices": [0], "cuts": 1}),
]


@pytest.mark.parametrize(("tool", "arguments"), EDITS)
def test_edit_rejects_stale_query_revision_without_changing_the_mesh(tool, arguments):
    host, obj = mesh_host()
    revision = load_and_call(SCRIPT, host, object_name=obj.name)["context"]["revision"]
    obj.data.vertices[0].co = (0.125, 0.0, 0.0)

    result = load_and_call(
        f"blender-mesh-ops/scripts/{tool}.py",
        host,
        object_name=obj.name,
        expected_revision=revision,
        **arguments,
    )

    assert not result["success"]
    assert result["context"]["error_code"] == "stale_mesh_revision"
    assert result["context"]["mutation_applied"] is False
    assert obj.mode == "OBJECT"
    assert len(obj.data.polygons) == 1
    assert obj.data.vertices[0].co == (0.125, 0.0, 0.0)


@pytest.mark.parametrize(("tool", "arguments"), EDITS)
@pytest.mark.parametrize(
    ("condition", "error_code"),
    [
        ("malformed", "invalid_mesh_revision"),
        ("edit_mode", "mesh_revision_mode_required"),
        ("oversize", "mesh_revision_scan_limit"),
        ("unreadable", "mesh_revision_unavailable"),
        ("nonfinite", "mesh_revision_unavailable"),
        ("replaced_mesh", "stale_mesh_revision"),
    ],
)
def test_unverifiable_revision_rejects_edit_without_operator_or_mode_changes(tool, arguments, condition, error_code):
    host, obj = mesh_host()
    revision = load_and_call(SCRIPT, host, object_name=obj.name)["context"]["revision"]
    if condition == "malformed":
        revision = "not-a-revision"
    elif condition == "edit_mode":
        obj.mode = "EDIT"
    elif condition == "oversize":
        obj.data.loops = range(100_001)
    elif condition == "unreadable":
        del obj.data.vertices[0].normal
    elif condition == "nonfinite":
        obj.data.vertices[0].co = (float("nan"), 0, 0)
    elif condition == "replaced_mesh":
        # Identical geometry under a replacement data block is not the queried mesh.
        _, other = mesh_host()
        obj.data = other.data
    mode_before = obj.mode
    result = load_and_call(
        f"blender-mesh-ops/scripts/{tool}.py", host, object_name=obj.name, expected_revision=revision, **arguments
    )
    assert not result["success"]
    assert result["context"]["error_code"] == error_code
    assert result["context"]["mutation_applied"] is False
    assert obj.mode == mode_before
    assert len(obj.data.polygons) == 1


@pytest.mark.parametrize(("tool", "arguments"), EDITS)
def test_guarded_edit_discovery_declares_revision_and_query_recovery(tool, arguments):
    tools = yaml.safe_load((SKILLS_ROOT / "blender-mesh-ops/tools.yaml").read_text(encoding="utf-8"))["tools"]
    contract = next(item for item in tools if item["name"] == tool)
    schema = contract["input_schema"]
    revision = schema["properties"]["expected_revision"]
    assert revision["type"] == "string"
    assert revision["pattern"] == "^mesh-query-v1:[0-9a-f]{64}$"
    assert "expected_revision" not in schema["required"]
    assert contract["affinity"] == "main"
    assert contract["enforce_thread_affinity"] is True
    assert "inspect_mesh_components" in str(contract["next-tools"])
