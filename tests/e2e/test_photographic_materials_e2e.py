"""Exercise photographic toy-material setup in native Blender."""

from __future__ import annotations

import struct
import zlib

import pytest

bpy = pytest.importorskip("bpy", reason="requires a real Blender interpreter")

from tests.e2e.conftest import load_skill  # noqa: E402

pytestmark = pytest.mark.e2e


def _write_generated_png(path):
    image = bpy.data.images.new("E2E Scan", width=1, height=1, alpha=True)
    image.pixels = [1.0, 1.0, 1.0, 0.5]
    image.filepath_raw = str(path)
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)


def _write_generated_rgb_png(path):
    def chunk(kind, payload):
        checksum = zlib.crc32(kind + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff"))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)


@pytest.fixture
def material_scene():
    if tuple(bpy.app.version) < (5, 0, 0):
        pytest.skip("the photographic material contract targets Blender 5")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_cube_add(size=0.067)
    toy = bpy.context.object
    toy.name = "E2E Photographic Toy"
    return toy


def test_photographic_materials_and_bevel_round_trip(material_scene, tmp_path):
    toy = material_scene
    configure = load_skill("blender-photographic-materials", "configure_photographic_material")
    bevel = load_skill("blender-photographic-materials", "configure_toy_bevel")
    validate = load_skill("blender-photographic-materials", "validate_photographic_material")

    diffuse = tmp_path / "diffuse.png"
    roughness = tmp_path / "roughness.png"
    normal = tmp_path / "normal.png"
    for path in (diffuse, roughness, normal):
        _write_generated_png(path)

    configured = configure.main(
        material_name="E2E Painted Toy",
        material_kind="PAINTED_TOY",
        target_object=toy.name,
        texture_paths={"diffuse": str(diffuse), "roughness": str(roughness), "normal": str(normal)},
        texture_source="Poly Haven",
    )
    assert configured["success"] is True, configured

    bevel_result = bevel.main(object_name=toy.name, width_mm=0.5, segments=3)
    assert bevel_result["success"] is True, bevel_result

    report = validate.main(
        material_name="E2E Painted Toy",
        material_kind="PAINTED_TOY",
        object_name=toy.name,
        require_pbr_textures=True,
    )
    assert report["success"] is True, report
    assert report["context"]["valid"] is True, report
    assert report["context"]["texture_map_count"] == 3
    assert report["context"]["bevel"]["width_mm"] == pytest.approx(0.5)


def test_gloss_eye_and_leaf_contracts(material_scene, tmp_path):
    configure = load_skill("blender-photographic-materials", "configure_photographic_material")
    validate = load_skill("blender-photographic-materials", "validate_photographic_material")

    eye = configure.main(material_name="E2E Gloss Eye", material_kind="GLOSS_BLACK_EYE")
    assert eye["success"] is True, eye
    eye_report = validate.main(
        material_name="E2E Gloss Eye",
        material_kind="GLOSS_BLACK_EYE",
        require_pbr_textures=False,
    )
    assert eye_report["context"]["valid"] is True, eye_report

    leaf_path = tmp_path / "leaf.png"
    _write_generated_png(leaf_path)
    leaf = configure.main(
        material_name="E2E Plant Leaf",
        material_kind="PLANT_LEAF",
        texture_paths={"diffuse": str(leaf_path)},
    )
    assert leaf["success"] is True, leaf
    leaf_report = validate.main(
        material_name="E2E Plant Leaf",
        material_kind="PLANT_LEAF",
        require_pbr_textures=False,
    )
    assert leaf_report["context"]["valid"] is True, leaf_report

    rgb_leaf_path = tmp_path / "leaf-rgb.png"
    _write_generated_rgb_png(rgb_leaf_path)
    leaf_material = bpy.data.materials["E2E Plant Leaf"]
    node_names_before_rejection = [node.name for node in leaf_material.node_tree.nodes]
    rejected = configure.main(
        material_name="E2E Plant Leaf",
        material_kind="PLANT_LEAF",
        texture_paths={"diffuse": str(rgb_leaf_path)},
    )
    assert rejected["success"] is False, rejected
    assert [node.name for node in leaf_material.node_tree.nodes] == node_names_before_rejection
    leaf_after_rejection = validate.main(
        material_name="E2E Plant Leaf",
        material_kind="PLANT_LEAF",
        require_pbr_textures=False,
    )
    assert leaf_after_rejection["context"]["valid"] is True, leaf_after_rejection
