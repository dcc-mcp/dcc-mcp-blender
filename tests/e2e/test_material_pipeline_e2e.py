"""E2E tests for material library and texture bake skills."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

bpy = pytest.importorskip("bpy", reason="bpy not available - run inside Blender Python interpreter")

pytestmark = pytest.mark.e2e

from tests.e2e.conftest import load_skill  # noqa: E402


def _new_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


class TestMaterialPipelineE2E:
    def setup_method(self):
        _new_scene()

    def test_material_preset_texture_assignment_and_bake_dry_run(self):
        bpy.ops.mesh.primitive_cube_add()
        cube_name = bpy.context.active_object.name
        material = bpy.data.materials.new("E2ELookdev")
        material.use_nodes = True
        bpy.context.active_object.data.materials.append(material)

        set_attr = load_skill("blender-material-library", "set_material_attribute")
        attr_result = set_attr.set_material_attribute(
            material_name="E2ELookdev",
            attribute="roughness",
            value=0.25,
        )
        assert attr_result["success"] is True

        with tempfile.TemporaryDirectory() as tmp:
            texture_path = Path(tmp) / "tiny.png"
            image = bpy.data.images.new("TinyTexture", width=2, height=2, alpha=True)
            image.filepath_raw = str(texture_path)
            image.file_format = "PNG"
            image.save()

            assign_texture = load_skill("blender-material-library", "assign_texture")
            texture_result = assign_texture.assign_texture(
                material_name="E2ELookdev",
                image_path=str(texture_path),
            )
            assert texture_result["success"] is True

            save_preset = load_skill("blender-material-library", "save_material_preset")
            save_result = save_preset.save_material_preset(
                material_name="E2ELookdev",
                preset_name="e2e-look",
            )
            assert save_result["success"] is True

            list_presets = load_skill("blender-material-library", "list_material_presets")
            presets_result = list_presets.list_material_presets()
            assert presets_result["context"]["count"] == 1

            bake = load_skill("blender-texture-bake", "bake_textures")
            bake_result = bake.bake_textures(
                object_name=cube_name,
                maps=["diffuse"],
                output_dir=tmp,
                resolution=16,
                dry_run=True,
            )
            assert bake_result["success"] is True
            assert bake_result["context"]["written_files"] == []
            assert bake_result["context"]["planned_files"][0].endswith("_diffuse.png")
