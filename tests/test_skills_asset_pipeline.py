"""Unit tests for validation and pipeline skill scripts."""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from unittest.mock import patch

from tests.conftest import load_and_call, make_mock_bpy


class _ObjectCollection(list):
    def get(self, name):
        for obj in self:
            if getattr(obj, "name", None) == name:
                return obj
        return None


class _FakeScene(dict):
    def __init__(self):
        super().__init__()
        self.frame_start = 1
        self.frame_end = 24
        self.render = SimpleNamespace(fps=24)
        self.unit_settings = SimpleNamespace(scale_length=1.0)

    def get(self, key, default=None):
        return dict.get(self, key, default)


class _FakeObject(dict):
    def __init__(
        self,
        name="Cube",
        type="MESH",
        vertices=8,
        polygons=6,
        materials=None,
        uv_layers=1,
    ):
        super().__init__()
        self.name = name
        self.type = type
        self.hide_viewport = False
        self.hide_render = False
        self.animation_data = None
        self.data = SimpleNamespace(
            vertices=[object()] * vertices,
            edges=[],
            polygons=[object()] * polygons,
            materials=materials if materials is not None else [],
            uv_layers=[object()] * uv_layers,
        )
        self.material_slots = [SimpleNamespace(material=material) for material in self.data.materials]

    def get(self, key, default=None):
        return dict.get(self, key, default)

    def hide_get(self):
        return self.hide_viewport


def _make_bpy(*objects):
    bpy = make_mock_bpy()
    bpy.data.objects = _ObjectCollection(objects)
    bpy.context.scene = _FakeScene()
    return bpy


def _codes(result):
    return {issue["code"] for issue in result["context"]["report"]["issues"]}


class TestValidationSkills:
    def test_validate_mesh_passes_with_info_report(self):
        cube = _FakeObject()
        bpy = _make_bpy(cube)

        result = load_and_call("blender-validation/scripts/validate_mesh.py", bpy, object_name="Cube")

        assert result["success"] is True
        report = result["context"]["report"]
        assert report["passed"] is True
        assert report["counts"]["info"] == 1
        assert "MESH_VALID" in _codes(result)

    def test_validate_mesh_reports_empty_mesh_error(self):
        cube = _FakeObject(vertices=0, polygons=0)
        bpy = _make_bpy(cube)

        result = load_and_call("blender-validation/scripts/validate_mesh.py", bpy, object_name="Cube")

        assert result["success"] is True
        assert result["context"]["report"]["passed"] is False
        assert "MESH_NO_VERTICES" in _codes(result)

    def test_validate_materials_reports_missing_object_and_materials(self):
        cube = _FakeObject()
        bpy = _make_bpy(cube)

        result = load_and_call(
            "blender-validation/scripts/validate_materials.py",
            bpy,
            object_names=["Cube", "Missing"],
        )

        assert result["success"] is True
        assert {"OBJECT_MISSING", "MATERIALS_MISSING"}.issubset(_codes(result))

    def test_validate_export_readiness_reports_unsupported_format(self):
        cube = _FakeObject()
        bpy = _make_bpy(cube)

        result = load_and_call(
            "blender-validation/scripts/validate_export_readiness.py",
            bpy,
            object_names=["Cube"],
            target_format="unknown",
        )

        assert result["success"] is True
        assert "EXPORT_FORMAT_UNSUPPORTED" in _codes(result)

    def test_validate_animation_reports_invalid_frame_range(self):
        cube = _FakeObject()
        bpy = _make_bpy(cube)

        result = load_and_call(
            "blender-validation/scripts/validate_animation.py",
            bpy,
            object_names=["Cube"],
            frame_range=[20, 1],
        )

        assert result["success"] is True
        assert result["context"]["report"]["passed"] is False
        assert "ANIMATION_FRAME_RANGE_INVALID" in _codes(result)

    def test_get_validation_report_returns_latest_report(self):
        from dcc_mcp_blender import _asset_pipeline_ops as ops

        cube = _FakeObject()
        bpy = _make_bpy(cube)
        ops._REPORTS.clear()
        ops._LATEST_REPORT_ID = None

        with patch.dict(sys.modules, {"bpy": bpy}):
            validate = ops.validate_mesh("Cube")
            result = ops.get_validation_report()

        assert result["success"] is True
        assert result["context"]["report"]["report_id"] == validate["context"]["report"]["report_id"]


class TestPipelineMetadata:
    def test_asset_metadata_round_trip_and_clear_keys(self):
        cube = _FakeObject()
        bpy = _make_bpy(cube)

        tag = load_and_call(
            "blender-pipeline/scripts/tag_asset_metadata.py",
            bpy,
            object_name="Cube",
            metadata={"asset_type": "prop", "variant": "hero"},
        )
        get = load_and_call("blender-pipeline/scripts/get_asset_metadata.py", bpy, object_name="Cube")
        clear = load_and_call(
            "blender-pipeline/scripts/clear_asset_metadata.py",
            bpy,
            object_name="Cube",
            keys=["variant"],
        )

        assert tag["success"] is True
        assert get["context"]["assets"][0]["metadata"]["asset_type"] == "prop"
        assert clear["context"]["metadata"] == {"asset_type": "prop"}

    def test_missing_object_returns_error_for_metadata(self):
        bpy = _make_bpy()

        result = load_and_call(
            "blender-pipeline/scripts/tag_asset_metadata.py",
            bpy,
            object_name="Missing",
            metadata={"asset_type": "prop"},
        )

        assert result["success"] is False

    def test_set_project_context_updates_scene_settings(self):
        bpy = _make_bpy()

        result = load_and_call(
            "blender-pipeline/scripts/set_project_context.py",
            bpy,
            name="Demo",
            root="assets/demo",
            unit_scale=0.01,
            frame_rate=30,
            metadata={"show": "test"},
        )

        assert result["success"] is True
        assert bpy.context.scene.unit_settings.scale_length == 0.01
        assert bpy.context.scene.render.fps == 30
        assert result["context"]["project_context"]["name"] == "Demo"


class TestPublishOutputs:
    def test_create_publish_manifest_writes_local_json(self, tmp_path):
        cube = _FakeObject()
        bpy = _make_bpy(cube)
        output_path = tmp_path / "manifest.json"

        result = load_and_call(
            "blender-pipeline/scripts/create_publish_manifest.py",
            bpy,
            object_names=["Cube"],
            output_path=str(output_path),
            metadata={"task": "export"},
        )

        assert result["success"] is True
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        assert payload["schema"] == "dcc-mcp-blender.publish-manifest.v1"
        assert payload["assets"][0]["name"] == "Cube"

    def test_create_publish_manifest_rejects_url_path(self):
        cube = _FakeObject()
        bpy = _make_bpy(cube)

        result = load_and_call(
            "blender-pipeline/scripts/create_publish_manifest.py",
            bpy,
            object_names=["Cube"],
            output_path="https://example.com/manifest.json",
        )

        assert result["success"] is False
        assert "unsafe" in result["message"].lower()

    def test_prepare_publish_package_writes_manifest_and_readme(self, tmp_path):
        cube = _FakeObject()
        bpy = _make_bpy(cube)
        output_dir = tmp_path / "package"

        result = load_and_call(
            "blender-pipeline/scripts/prepare_publish_package.py",
            bpy,
            object_names=["Cube"],
            output_dir=str(output_dir),
            preset_name="game",
        )

        assert result["success"] is True
        assert (output_dir / "publish_manifest.json").exists()
        assert (output_dir / "README.txt").exists()
