"""UV audit geometry and non-mutating delivery contracts."""

from __future__ import annotations

import sys
from types import SimpleNamespace as NS
from xml.etree import ElementTree

import pytest

from dcc_mcp_blender._uv_quality import _intersection_area, audit_uv_layout, export_uv_layout

TRI = ((0.0, 0.0), (1.0, 0.0), (0.0, 1.0))


def mesh(name="Mesh", triangles=(TRI,), with_uv=True):
    coords = [p for tri in triangles for p in tri]
    layer = NS(name="UVMap", data=[NS(uv=p) for p in coords])
    uv_layers = NS(active=layer if with_uv else None, get=lambda name: layer if name == "UVMap" and with_uv else None)
    polygons = [NS(index=i, loop_indices=tuple(range(3 * i, 3 * i + 3))) for i in range(len(triangles))]
    data = NS(
        uv_layers=uv_layers,
        loops=list(range(len(coords))),
        polygons=polygons,
        loop_triangles=[NS(loops=p.loop_indices, polygon_index=p.index) for p in polygons],
        calc_loop_triangles=lambda: None,
    )
    return NS(name=name, type="MESH", mode="OBJECT", data=data)


@pytest.fixture
def install(monkeypatch):
    def apply(*objects):
        monkeypatch.setitem(sys.modules, "bpy", NS(data=NS(objects={o.name: o for o in objects})))

    return apply


def context(result):
    assert result["success"], result
    return result["context"]


def test_overlap_is_area_not_bbox_or_edge_contact():
    assert _intersection_area(TRI, tuple(reversed(TRI))) == pytest.approx(0.5)
    touching = ((1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
    assert _intersection_area(TRI, touching) == 0
    contained = ((0.1, 0.1), (0.2, 0.1), (0.1, 0.2))
    assert _intersection_area(TRI, contained) == pytest.approx(0.005)
    disjoint_bbox = ((0.8, 0.8), (1.0, 0.8), (0.8, 1.0))
    assert _intersection_area(TRI, disjoint_bbox) == 0


def test_audit_nonmutating_named_map_and_missing_map(install):
    obj = mesh()
    obj.data.uv_layers.active = None
    install(obj)
    assert context(audit_uv_layout([obj.name], uv_map="UVMap"))["passed"]
    assert obj.data.uv_layers.active is None
    missing = context(audit_uv_layout([obj.name]))
    assert missing["complete"] and not missing["passed"]
    assert missing["issue_counts"] == {"missing_uv_map": 1}


def test_stacks_and_scope_are_explicit(install):
    install(mesh("A"), mesh("B", (tuple(reversed(TRI)),)))
    assert context(audit_uv_layout(["A", "B"]))["passed"]
    assert context(audit_uv_layout(["A", "B"], overlap_scope="selection"))["issue_counts"] == {"overlap_pairs": 1}
    allowed = context(audit_uv_layout(["A", "B"], overlap_scope="selection", allow_stacked=True))
    assert allowed["passed"] and allowed["allowed_stacked_pairs"] == 1


def test_partial_overlap_still_fails_when_stacks_allowed(install):
    shifted = tuple((x + 0.1, y) for x, y in TRI)
    install(mesh(triangles=(TRI, shifted)))
    report = context(audit_uv_layout(["Mesh"], allow_stacked=True, tile_policy="unrestricted"))
    assert report["issue_counts"] == {"overlap_pairs": 1}


def test_invalid_degenerate_and_tile_policies(install):
    invalid = ((float("nan"), 0), (1, 0), (0, 1))
    flat = ((0, 0), (0.5, 0), (1, 0))
    udim = tuple((x + 2, y + 3) for x, y in TRI)
    install(mesh(triangles=(invalid, flat, udim)))
    report = context(audit_uv_layout(["Mesh"]))
    assert report["issue_counts"] == {"invalid_coordinates": 1, "degenerate_triangles": 1, "out_of_tile_triangles": 1}
    report = context(audit_uv_layout(["Mesh"], tile_policy="udim"))
    assert "out_of_tile_triangles" not in report["issue_counts"]


def test_no_false_pass_when_budget_exhausted(install):
    install(mesh(triangles=(TRI,) * 5))
    report = context(audit_uv_layout(["Mesh"], max_triangles=1))
    assert not report["complete"] and not report["passed"]
    assert report["objects"][0]["incomplete_reason"] == "triangle_budget"
    report = context(audit_uv_layout(["Mesh"], allow_stacked=True, max_pair_tests=1))
    assert not report["complete"] and not report["passed"]
    assert report["pair_tests"] == 1 and not report["overlap_complete"]
    assert not report["objects"][0]["complete"]


def test_triangle_budget_shared_between_objects_and_details_bounded(install):
    install(mesh("A"), mesh("B"))
    report = context(audit_uv_layout(["A", "B"], max_triangles=1))
    assert report["triangles_checked"] == 1 and not report["complete"]
    install(mesh(triangles=(TRI,) * 5))
    report = context(audit_uv_layout(["Mesh"], max_report_items=1))
    assert len(report["details"]) == 1 and report["details_truncated"]
    assert report["issue_counts"]["overlap_pairs"] == 10


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_triangles": True},
        {"max_pair_tests": 0},
        {"area_epsilon": float("inf")},
        {"area_epsilon": 0},
        {"area_epsilon": True},
        {"check_overlap": 1},
        {"tile_policy": "wrong"},
        {"overlap_scope": "wrong"},
        {"max_report_items": -1},
        {"uv_map": ""},
    ],
)
def test_invalid_arguments_rejected(install, kwargs):
    install(mesh())
    assert not audit_uv_layout(["Mesh"], **kwargs)["success"]


def test_object_validation_and_edit_mode_fail_closed(install):
    obj = mesh()
    install(obj)
    for names in ([], ["Mesh", "Mesh"], ["Missing"], "Mesh", [True]):
        assert not audit_uv_layout(names)["success"]
    obj.mode = "EDIT"
    assert not audit_uv_layout(["Mesh"])["success"]
    assert obj.mode == "EDIT"


def test_export_true_edges_xml_escaping_and_no_overwrite(install, tmp_path):
    obj = mesh('A<&"')
    install(obj)
    path = tmp_path / "layout.svg"
    result = context(export_uv_layout([obj.name], str(path)))
    assert result["edge_count"] == 3 and not result["mutation_applied"]
    root = ElementTree.parse(path).getroot()
    assert root.attrib["width"] == "2048"
    text = root.find("{http://www.w3.org/2000/svg}text")
    assert text.text == obj.name + " | UVMap"
    original = path.read_bytes()
    assert not export_uv_layout([obj.name], str(path))["success"]
    assert path.read_bytes() == original


def test_export_does_not_create_partial_file_on_preflight_failure(install, tmp_path):
    install(mesh("A"), mesh("B", with_uv=False))
    path = tmp_path / "layout.svg"
    assert not export_uv_layout(["A", "B"], str(path))["success"]
    assert not path.exists()
    install(mesh(triangles=(TRI, TRI)))
    assert not export_uv_layout(["Mesh"], str(path), max_triangles=1)["success"]
    assert not path.exists()
    assert not export_uv_layout(["Mesh"], "relative.svg")["success"]


def test_missing_loop_coordinates_and_empty_mesh(install):
    obj = mesh()
    obj.data.uv_layers.active.data.pop()
    install(obj)
    assert context(audit_uv_layout(["Mesh"]))["issue_counts"] == {"uncovered_faces": 1}
    install(mesh(triangles=()))
    assert context(audit_uv_layout(["Mesh"]))["issue_counts"] == {"empty_mesh": 1}


def test_invalid_xml_name_never_creates_broken_artifact(install, tmp_path):
    obj = mesh("invalid\x01name")
    install(obj)
    path = tmp_path / "layout.svg"
    assert not export_uv_layout([obj.name], str(path))["success"]
    assert not path.exists()
