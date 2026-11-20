"""Tests for the asset build contract and deterministic scene snapshots."""

from __future__ import annotations

import json
from types import SimpleNamespace

from tests.conftest import load_and_call, make_mock_bpy


class _Collection(list):
    def get(self, name):
        for item in self:
            if getattr(item, "name", None) == name:
                return item
        return None


class _Scene(dict):
    def __init__(self):
        super().__init__()
        self.name = "Scene"
        self.frame_start = 1
        self.frame_end = 24
        self.frame_current = 1
        self.render = SimpleNamespace(fps=24, engine="BLENDER_EEVEE_NEXT")
        self.unit_settings = SimpleNamespace(scale_length=1.0)

    def get(self, key, default=None):
        return dict.get(self, key, default)


class _Object(dict):
    def __init__(self, name="Cube", object_type="MESH"):
        super().__init__()
        self.name = name
        self.type = object_type
        self.parent = None
        self.bound_box = []
        self.modifiers = []
        if object_type == "MESH":
            self.data = SimpleNamespace(
                vertices=[object()] * 8,
                edges=[],
                polygons=[object()] * 6,
                materials=[SimpleNamespace(name="Mat")],
                uv_layers=[object()],
            )
        else:
            self.data = SimpleNamespace(
                bones=[SimpleNamespace(name="root", parent=None)],
                materials=[],
            )

    def get(self, key, default=None):
        return dict.get(self, key, default)


def _make_bpy(*objects):
    bpy = make_mock_bpy()
    bpy.context.scene = _Scene()
    bpy.data.objects = _Collection(objects)
    bpy.data.actions = _Collection([SimpleNamespace(name="Walk", frame_range=(1.0, 24.0), fcurves=[])])
    return bpy


def test_capture_snapshot_is_deterministic_and_writes_json(tmp_path):
    bpy = _make_bpy(_Object())
    output_path = tmp_path / "baseline.json"

    result = load_and_call(
        "blender-pipeline/scripts/capture_asset_snapshot.py",
        bpy,
        output_path=str(output_path),
    )

    assert result["success"] is True
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema"] == "dcc-mcp-blender.asset-snapshot.v1"
    assert payload["snapshot_hash"] == result["context"]["snapshot_hash"]
    assert payload["objects"][0]["name"] == "Cube"


def test_create_and_validate_build_manifest_checks_control_and_action(tmp_path):
    mesh = _Object()
    rig = _Object("Rig", "ARMATURE")
    rig["walk"] = 0.5
    bpy = _make_bpy(mesh, rig)
    manifest_path = tmp_path / "build.json"

    created = load_and_call(
        "blender-pipeline/scripts/create_asset_build_manifest.py",
        bpy,
        asset_name="Walker",
        object_names=["Cube", "Rig"],
        output_path=str(manifest_path),
        armature_name="Rig",
        controls=[{"name": "walk", "min": 0, "max": 1}],
        action_names=["Walk"],
        references=[{"path": str(tmp_path / "missing-reference.png")}],
    )
    validated = load_and_call(
        "blender-validation/scripts/validate_asset_build_manifest.py",
        bpy,
        manifest_path=str(manifest_path),
    )

    assert created["success"] is True
    assert validated["success"] is True
    assert validated["context"]["report"]["passed"] is True
    assert validated["context"]["manifest"]["asset_name"] == "Walker"


def test_validate_build_manifest_reports_control_drift():
    mesh = _Object()
    rig = _Object("Rig", "ARMATURE")
    rig["walk"] = 2.0
    bpy = _make_bpy(mesh, rig)
    manifest = {
        "schema": "dcc-mcp-blender.asset-build-manifest.v1",
        "manifest_id": "test-manifest",
        "asset_name": "Walker",
        "object_names": ["Cube", "Rig"],
        "armature_name": "Rig",
        "controls": [{"name": "walk", "property": "walk", "target_object": "Rig", "min": 0, "max": 1}],
        "action_names": ["Walk"],
    }

    result = load_and_call(
        "blender-validation/scripts/validate_asset_build_manifest.py",
        bpy,
        manifest=manifest,
    )

    codes = {issue["code"] for issue in result["context"]["report"]["issues"]}
    assert result["success"] is True
    assert result["context"]["report"]["passed"] is False
    assert "BUILD_CONTROL_OUT_OF_RANGE" in codes


def test_compare_snapshot_reports_strict_scene_changes(tmp_path):
    baseline_bpy = _make_bpy(_Object())
    baseline_path = tmp_path / "baseline.json"
    load_and_call(
        "blender-pipeline/scripts/capture_asset_snapshot.py",
        baseline_bpy,
        output_path=str(baseline_path),
    )

    changed_bpy = _make_bpy(_Object(), _Object("Added"))
    result = load_and_call(
        "blender-validation/scripts/compare_asset_snapshot.py",
        changed_bpy,
        baseline_path=str(baseline_path),
        strict=True,
    )

    assert result["success"] is True
    assert result["context"]["passed"] is False
    assert result["context"]["changes"]["objects_added"] == ["Added"]
