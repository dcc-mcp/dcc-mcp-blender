"""E2E tests for Blender validation and local pipeline skills."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

bpy = pytest.importorskip("bpy", reason="bpy not available - run inside Blender Python interpreter")

pytestmark = pytest.mark.e2e

from tests.e2e.conftest import load_skill  # noqa: E402


def _new_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


class TestAssetPipelineE2E:
    def setup_method(self):
        _new_scene()

    def test_validate_scene_and_create_publish_manifest(self):
        bpy.ops.mesh.primitive_cube_add()
        cube_name = bpy.context.active_object.name

        tag_mod = load_skill("blender-pipeline", "tag_asset_metadata")
        tag_result = tag_mod.tag_asset_metadata(cube_name, {"asset_type": "prop", "department": "layout"})
        assert tag_result["success"] is True

        validate_mod = load_skill("blender-validation", "validate_mesh")
        validate_result = validate_mod.validate_mesh(cube_name, rules={"require_uvs": False})
        assert validate_result["success"] is True
        assert validate_result["context"]["report"]["passed"] is True

        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "publish_manifest.json"
            manifest_mod = load_skill("blender-pipeline", "create_publish_manifest")
            manifest_result = manifest_mod.create_publish_manifest(
                object_names=[cube_name],
                output_path=str(manifest_path),
                metadata={"target": "smoke"},
            )
            assert manifest_result["success"] is True
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            assert payload["assets"][0]["metadata"]["asset_type"] == "prop"


class TestMaterialValidationE2E:
    def setup_method(self):
        _new_scene()
        bpy.ops.mesh.primitive_cube_add()
        self.obj = bpy.context.active_object
        self.material = bpy.data.materials.new("ValidationFixture")
        self.material.use_nodes = True
        self.obj.data.materials.append(self.material)
        self.validate = load_skill("blender-validation", "validate_materials").validate_materials

    def _report(self):
        result = self.validate(object_names=[self.obj.name], rules={"require_nodes": True})
        assert result["success"] is True
        return result["context"]["report"]

    def _texture(self, image, linked=True):
        texture = self.material.node_tree.nodes.new("ShaderNodeTexImage")
        texture.image = image
        if linked:
            shader = self.material.node_tree.nodes.get("Principled BSDF")
            self.material.node_tree.links.new(texture.outputs["Color"], shader.inputs["Base Color"])
        return texture

    def test_empty_imported_material_node_tree_fails(self):
        self.material.node_tree.nodes.clear()

        report = self._report()

        assert report["passed"] is False
        assert "MATERIAL_NODE_TREE_EMPTY" in {issue["code"] for issue in report["issues"]}

    def test_effective_object_material_override_is_validated(self):
        unused = bpy.data.materials.new("UnusedMeshMaterial")
        unused.use_nodes = True
        unused.node_tree.nodes.clear()
        self.obj.data.materials[0] = unused
        self.obj.material_slots[0].link = "OBJECT"
        self.obj.material_slots[0].material = self.material

        assert self._report()["passed"] is True

    def test_missing_connected_image_fails_without_loading_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = bpy.data.images.new("MissingFixture", width=1, height=1)
            image.source = "FILE"
            image.filepath = str(Path(tmp) / "missing.png")
            self._texture(image)
            before = (image.filepath, image.has_data, image.is_dirty)

            report = self._report()

            assert report["passed"] is False
            assert "MATERIAL_IMAGE_MISSING" in {issue["code"] for issue in report["issues"]}
            assert (image.filepath, image.has_data, image.is_dirty) == before

    @pytest.mark.parametrize("packed", [False, True])
    def test_generated_and_packed_images_need_no_external_file(self, packed):
        image = bpy.data.images.new("InternalFixture", width=1, height=1)
        if packed:
            image.pixels[:] = [1.0, 0.0, 0.0, 1.0]
            image.pack()
            assert image.packed_file is not None
        self._texture(image)

        report = self._report()

        assert report["passed"] is True
        assert report["context"]["resource_checks_complete"] is True

    def test_unconnected_missing_image_does_not_fail_material(self):
        image = bpy.data.images.new("UnusedFixture", width=1, height=1)
        image.source = "FILE"
        image.filepath = "//unused-missing.png"
        self._texture(image, linked=False)

        assert self._report()["passed"] is True

    def test_sequence_is_explicitly_unverified_not_missing(self):
        image = bpy.data.images.new("SequenceFixture", width=1, height=1)
        image.source = "SEQUENCE"
        image.filepath = "//frames/frame0001.png"
        self._texture(image)

        report = self._report()

        assert report["counts"]["error"] == 0
        assert report["context"]["resource_checks_complete"] is False
        assert "MATERIAL_IMAGE_UNVERIFIED" in {issue["code"] for issue in report["issues"]}

    def test_udim_checks_only_declared_tiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Existence validation must not decode/reload these artist resources.
            (Path(tmp) / "leaf.1001.png").write_bytes(b"exists")
            image = bpy.data.images.new("TilesFixture", width=1, height=1, tiled=True)
            image.filepath = str(Path(tmp) / "leaf.<UDIM>.png")
            image.tiles.new(1002)
            assert [tile.number for tile in image.tiles] == [1001, 1002]
            self._texture(image)

            report = self._report()

            missing = [issue for issue in report["issues"] if issue["code"] == "MATERIAL_IMAGE_MISSING"]
            assert report["passed"] is False, report
            assert [issue["details"]["tile"] for issue in missing] == [1002]

    def test_nested_node_group_image_is_inspected(self):
        with tempfile.TemporaryDirectory() as tmp:
            group_tree = bpy.data.node_groups.new("ValidationGroup", "ShaderNodeTree")
            if hasattr(group_tree, "interface"):
                group_tree.interface.new_socket(name="Color", in_out="OUTPUT", socket_type="NodeSocketColor")
            else:
                group_tree.outputs.new("NodeSocketColor", "Color")
            group_output = group_tree.nodes.new("NodeGroupOutput")
            texture = group_tree.nodes.new("ShaderNodeTexImage")
            image = bpy.data.images.new("NestedMissing", width=1, height=1)
            image.source = "FILE"
            image.filepath = str(Path(tmp) / "missing.png")
            texture.image = image
            group_tree.links.new(texture.outputs["Color"], group_output.inputs["Color"])
            group = self.material.node_tree.nodes.new("ShaderNodeGroup")
            group.node_tree = group_tree
            shader = self.material.node_tree.nodes.get("Principled BSDF")
            self.material.node_tree.links.new(group.outputs["Color"], shader.inputs["Base Color"])

            report = self._report()

            assert report["passed"] is False
            assert "MATERIAL_IMAGE_MISSING" in {issue["code"] for issue in report["issues"]}
