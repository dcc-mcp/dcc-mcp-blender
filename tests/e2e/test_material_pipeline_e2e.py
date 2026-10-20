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


def test_transfer_projection_real_bake_and_settings_restoration(tmp_path, monkeypatch):
    """Controlled geometry/color-space comparison, not a general flat-map validator."""
    import math

    from dcc_mcp_blender import _material_pipeline_ops as ops

    _new_scene()
    bpy.ops.mesh.primitive_plane_add(size=0.2)
    low = bpy.context.object
    low.name = "ProjectionLow"
    mesh = bpy.data.meshes.new("ProjectionHighMesh")
    n = 20
    vertices = [
        (-0.1 + 0.2 * x / n, -0.1 + 0.2 * y / n, 0.006 + 0.003 * math.sin(x * 0.7))
        for y in range(n + 1)
        for x in range(n + 1)
    ]
    faces = []
    for y in range(n):
        for x in range(n):
            a = y * (n + 1) + x
            faces.append((a, a + 1, a + n + 2, a + n + 1))
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    high = bpy.data.objects.new("ProjectionHigh", mesh)
    bpy.context.collection.objects.link(high)
    scene = bpy.context.scene
    original_engine = scene.render.engine
    assert original_engine != "CYCLES"
    scene.cycles.samples = 1
    bake = scene.render.bake
    fields = ("cage_extrusion", "max_ray_distance", "use_cage", "normal_space", "use_selected_to_active", "margin")
    before = {name: getattr(bake, name) for name in fields}

    # Keep this test's color interpretation constant in both real bakes. Production
    # image creation is intentionally unchanged by the projection-controls feature.
    create_image = ops._create_bake_image

    def non_color_image(*args, **kwargs):
        image = create_image(*args, **kwargs)
        image.colorspace_settings.name = "Non-Color"
        return image

    monkeypatch.setattr(ops, "_create_bake_image", non_color_image)

    colors = []
    transfer = load_skill("blender-texture-bake", "transfer_maps")
    for label, projection in (
        ("zero", dict(use_cage=False, cage_extrusion=0.0, max_ray_distance=0.0)),
        ("extruded", dict(use_cage=True, cage_extrusion=0.02, max_ray_distance=0.05)),
    ):
        result = transfer.main(
            source_object=high.name,
            target_object=low.name,
            output_dir=str(tmp_path / label),
            resolution=256,
            margin=0,
            normal_space="TANGENT",
            **projection,
        )
        assert result["success"] is True, result
        output = Path(result["context"]["written_files"][0])
        assert output.is_file() and output.stat().st_size > 0
        image = low.active_material.node_tree.nodes.active.image
        pixels = list(image.pixels)
        rgb = {tuple(round(pixels[i + c] * 255) for c in range(3)) for i in range(0, len(pixels), 4)}
        colors.append(len(rgb))
        assert scene.render.engine == original_engine
        assert {name: getattr(bake, name) for name in fields} == before
    assert colors[0] == 1, colors  # This particular geometry is above zero-distance ray origins.
    assert colors[1] > 10, colors
    print("PROJECTION_REAL_BAKE", {"version": bpy.app.version_string, "unique_rgb": colors, "settings_restored": True})

    def fail_save(*args):
        raise RuntimeError("injected save failure after real bake")

    monkeypatch.setattr(ops, "_save_bake_image", fail_save)
    failed = transfer.main(
        source_object=high.name,
        target_object=low.name,
        output_dir=str(tmp_path / "failed"),
        resolution=8,
        cage_extrusion=0.02,
        max_ray_distance=0.05,
        use_cage=True,
    )
    assert failed["success"] is False
    assert scene.render.engine == original_engine
    assert {name: getattr(bake, name) for name in fields} == before
