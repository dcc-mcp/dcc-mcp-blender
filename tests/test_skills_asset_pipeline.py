"""Unit tests for validation and pipeline skill scripts."""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

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


def _bpy_with_image(image, connected=True):
    texture = SimpleNamespace(
        name="Texture", type="TEX_IMAGE", image=image, outputs=[SimpleNamespace(is_linked=connected)]
    )
    material = SimpleNamespace(name="Leaves", use_nodes=True, node_tree=SimpleNamespace(nodes=[texture]))
    bpy = _make_bpy(_FakeObject(materials=[material]))
    bpy.path.abspath.side_effect = lambda path, **kwargs: path
    return bpy


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

    def test_validate_materials_rejects_empty_enabled_node_tree(self):
        material = SimpleNamespace(name="ImportedPlaceholder", use_nodes=True, node_tree=SimpleNamespace(nodes=[]))
        bpy = _make_bpy(_FakeObject(materials=[material]))

        result = load_and_call(
            "blender-validation/scripts/validate_materials.py",
            bpy,
            object_names=["Cube"],
            rules={"require_nodes": True},
        )

        assert result["success"] is True
        assert result["context"]["report"]["passed"] is False
        assert "MATERIAL_NODE_TREE_EMPTY" in _codes(result)

    def test_validate_materials_reports_missing_connected_image(self, tmp_path):
        image = SimpleNamespace(
            name="Normal", source="FILE", filepath=str(tmp_path / "missing.png"), packed_file=None, packed_files=[]
        )
        texture = SimpleNamespace(
            name="Texture", type="TEX_IMAGE", image=image, outputs=[SimpleNamespace(is_linked=True)]
        )
        material = SimpleNamespace(name="Leaves", use_nodes=True, node_tree=SimpleNamespace(nodes=[texture]))
        bpy = _make_bpy(_FakeObject(materials=[material]))
        bpy.path.abspath.side_effect = lambda path, **kwargs: path

        result = load_and_call(
            "blender-validation/scripts/validate_materials.py",
            bpy,
            object_names=["Cube"],
            rules={"require_nodes": True},
        )

        assert result["success"] is True
        assert result["context"]["report"]["passed"] is False
        assert "MATERIAL_IMAGE_MISSING" in _codes(result)

    @pytest.mark.parametrize("missing_datablock", [True, False])
    def test_validate_materials_reports_missing_environment_image(self, tmp_path, missing_datablock):
        image = (
            None
            if missing_datablock
            else SimpleNamespace(
                name="Environment", source="FILE", filepath=str(tmp_path / "missing.exr"), packed_file=None
            )
        )
        bpy = _bpy_with_image(image)
        bpy.data.objects[0].material_slots[0].material.node_tree.nodes[0].type = "TEX_ENVIRONMENT"

        result = load_and_call(
            "blender-validation/scripts/validate_materials.py",
            bpy,
            object_names=["Cube"],
            rules={"require_nodes": True},
        )

        assert result["success"] is True
        assert result["context"]["report"]["passed"] is False
        assert "MATERIAL_IMAGE_MISSING" in _codes(result)

    @pytest.mark.parametrize("require_nodes", [False, True])
    def test_validate_materials_does_not_inspect_disabled_node_tree(self, require_nodes):
        bpy = _bpy_with_image(None)
        material = bpy.data.objects[0].material_slots[0].material
        material.use_nodes = False

        result = load_and_call(
            "blender-validation/scripts/validate_materials.py",
            bpy,
            object_names=["Cube"],
            rules={"require_nodes": require_nodes},
        )

        assert result["success"] is True
        assert result["context"]["report"]["passed"] is (not require_nodes)
        assert _codes(result) == ({"MATERIAL_NODES_DISABLED"} if require_nodes else {"MATERIALS_VALID"})
        assert material.use_nodes is False
        assert material.node_tree.nodes[0].image is None

    @pytest.mark.parametrize("missing_image", [False, True])
    def test_validate_materials_inspects_nodes_when_legacy_toggle_is_absent(self, missing_image):
        image = None if missing_image else SimpleNamespace(name="Internal", source="GENERATED")
        bpy = _bpy_with_image(image)
        del bpy.data.objects[0].material_slots[0].material.use_nodes

        result = load_and_call(
            "blender-validation/scripts/validate_materials.py",
            bpy,
            object_names=["Cube"],
            rules={"require_nodes": True},
        )

        assert result["success"] is True
        assert result["context"]["report"]["passed"] is (not missing_image)
        assert _codes(result) == ({"MATERIAL_IMAGE_MISSING"} if missing_image else {"MATERIALS_VALID"})

    @pytest.mark.parametrize("source,packed", [("GENERATED", False), ("VIEWER", False), ("FILE", True)])
    def test_validate_materials_does_not_require_external_files_for_internal_images(self, source, packed):
        image = SimpleNamespace(
            name="Internal", source=source, filepath="", packed_file=object() if packed else None, packed_files=[]
        )
        texture = SimpleNamespace(
            name="Texture", type="TEX_IMAGE", image=image, outputs=[SimpleNamespace(is_linked=True)]
        )
        material = SimpleNamespace(name="Internal", use_nodes=True, node_tree=SimpleNamespace(nodes=[texture]))
        bpy = _make_bpy(_FakeObject(materials=[material]))
        bpy.path.abspath.side_effect = lambda path, **kwargs: path

        result = load_and_call("blender-validation/scripts/validate_materials.py", bpy, object_names=["Cube"])

        assert result["context"]["report"]["passed"] is True
        assert "MATERIAL_IMAGE_MISSING" not in _codes(result)
        bpy.path.abspath.assert_not_called()

    @pytest.mark.parametrize("missing_tile", [False, True])
    def test_validate_materials_checks_declared_udim_tiles_not_literal_template(self, tmp_path, missing_tile):
        (tmp_path / "leaf.1001.png").write_bytes(b"fixture")
        if not missing_tile:
            (tmp_path / "leaf.1002.png").write_bytes(b"fixture")
        image = SimpleNamespace(
            name="Tiles",
            source="TILED",
            filepath=str(tmp_path / "leaf.<UDIM>.png"),
            packed_file=None,
            packed_files=[],
            tiles=[SimpleNamespace(number=1001), SimpleNamespace(number=1002)],
        )
        bpy = _bpy_with_image(image)

        result = load_and_call("blender-validation/scripts/validate_materials.py", bpy, object_names=["Cube"])

        assert result["context"]["report"]["passed"] is (not missing_tile)
        if missing_tile:
            findings = result["context"]["report"]["issues"]
            assert any(
                item["code"] == "MATERIAL_IMAGE_MISSING" and item["details"]["tile"] == 1002 for item in findings
            )

    @pytest.mark.parametrize(
        "source,template,tiles",
        [
            ("SEQUENCE", "frame0001.png", []),
            ("MOVIE", "clip.mov", []),
            ("TILED", "leaf.png", [1001]),
            ("TILED", "leaf.<UDIM>.png", []),
            ("UNKNOWN", "image.png", []),
        ],
    )
    def test_validate_materials_reports_unverified_sources_without_false_missing(self, source, template, tiles):
        image = SimpleNamespace(
            name="Special",
            source=source,
            filepath=template,
            packed_file=None,
            packed_files=[],
            tiles=[SimpleNamespace(number=number) for number in tiles],
        )
        bpy = _bpy_with_image(image)

        result = load_and_call("blender-validation/scripts/validate_materials.py", bpy, object_names=["Cube"])

        report = result["context"]["report"]
        assert report["counts"]["error"] == 0
        assert "MATERIAL_IMAGE_UNVERIFIED" in _codes(result)
        assert "MATERIALS_VALID" not in _codes(result)
        assert report["context"]["resource_checks_complete"] is False

    def test_validate_materials_checks_connected_nested_node_groups(self, tmp_path):
        image = SimpleNamespace(name="Nested", source="FILE", filepath=str(tmp_path / "missing.png"), packed_file=None)
        bpy = _bpy_with_image(image)
        material = bpy.data.objects[0].data.materials[0]
        nested_tree = material.node_tree
        group = SimpleNamespace(
            name="Group", type="GROUP", node_tree=nested_tree, outputs=[SimpleNamespace(is_linked=True)]
        )
        material.node_tree = SimpleNamespace(nodes=[group])

        result = load_and_call("blender-validation/scripts/validate_materials.py", bpy, object_names=["Cube"])

        assert result["context"]["report"]["passed"] is False
        assert "MATERIAL_IMAGE_MISSING" in _codes(result)

    def test_validate_materials_bounds_udim_file_checks(self):
        image = SimpleNamespace(
            name="ManyTiles",
            source="TILED",
            filepath="many.<UDIM>.png",
            packed_file=None,
            tiles=[SimpleNamespace(number=number) for number in range(1001, 2026)],
        )
        bpy = _bpy_with_image(image)

        result = load_and_call("blender-validation/scripts/validate_materials.py", bpy, object_names=["Cube"])

        assert "MATERIAL_IMAGE_UNVERIFIED" in _codes(result)
        assert result["context"]["report"]["context"]["resource_checks_complete"] is False
        assert result["context"]["report"]["counts"]["error"] == 0

    def test_validate_materials_does_not_assume_partial_packed_udim_is_complete(self):
        image = SimpleNamespace(
            name="PartialPacked",
            source="TILED",
            filepath="leaf.<UDIM>.png",
            packed_file=object(),
            packed_files=[object()],
            tiles=[SimpleNamespace(number=1001), SimpleNamespace(number=1002)],
        )
        bpy = _bpy_with_image(image)

        result = load_and_call("blender-validation/scripts/validate_materials.py", bpy, object_names=["Cube"])

        assert "MATERIAL_IMAGE_UNVERIFIED" in _codes(result)
        assert result["context"]["report"]["context"]["resource_checks_complete"] is False
        assert result["context"]["report"]["counts"]["error"] == 0
        bpy.path.abspath.assert_not_called()

    @pytest.mark.parametrize("case", ["depth", "nodes", "unavailable_group"])
    def test_validate_materials_marks_bounded_or_unavailable_groups_incomplete(self, case):
        bpy = _bpy_with_image(None)
        material = bpy.data.objects[0].data.materials[0]
        if case == "nodes":
            material.node_tree.nodes = [SimpleNamespace(outputs=[], mute=False)] * 4097
        else:
            tree = None if case == "unavailable_group" else material.node_tree
            for _ in range(1 if case == "unavailable_group" else 18):
                tree = SimpleNamespace(
                    nodes=[
                        SimpleNamespace(
                            name="Group", type="GROUP", node_tree=tree, outputs=[SimpleNamespace(is_linked=True)]
                        )
                    ]
                )
            material.node_tree = tree

        result = load_and_call("blender-validation/scripts/validate_materials.py", bpy, object_names=["Cube"])

        assert "MATERIAL_GRAPH_UNVERIFIED" in _codes(result)
        assert result["context"]["report"]["context"]["resource_checks_complete"] is False

    @pytest.mark.parametrize("muted,linked", [(True, True), (False, False)])
    def test_validate_materials_does_not_check_inactive_images(self, muted, linked):
        bpy = _bpy_with_image(None, connected=linked)
        bpy.data.objects[0].data.materials[0].node_tree.nodes[0].mute = muted

        result = load_and_call("blender-validation/scripts/validate_materials.py", bpy, object_names=["Cube"])

        assert result["context"]["report"]["passed"] is True
        bpy.path.abspath.assert_not_called()

    def test_validate_materials_fails_closed_on_unreadable_image_metadata(self):
        image = SimpleNamespace(name="Unreadable", source="FILE", filepath="//locked.png", packed_file=None)
        bpy = _bpy_with_image(image)
        bpy.path.abspath.side_effect = OSError("Image library cannot be resolved")

        result = load_and_call("blender-validation/scripts/validate_materials.py", bpy, object_names=["Cube"])

        assert result["success"] is False

    def test_validate_materials_uses_effective_object_material_override(self):
        unused = SimpleNamespace(name="UnusedMeshMaterial", use_nodes=True, node_tree=SimpleNamespace(nodes=[]))
        image = SimpleNamespace(name="Generated", source="GENERATED", filepath="")
        bpy = _bpy_with_image(image)
        bpy.data.objects[0].data.materials = [unused]

        result = load_and_call(
            "blender-validation/scripts/validate_materials.py",
            bpy,
            object_names=["Cube"],
            rules={"require_nodes": True},
        )

        assert result["context"]["report"]["passed"] is True

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
