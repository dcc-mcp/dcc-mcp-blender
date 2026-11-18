"""Exercise motivated photographic lighting in native Blender."""

from __future__ import annotations

import pytest

bpy = pytest.importorskip("bpy", reason="requires a real Blender interpreter")

from tests.e2e.conftest import load_skill  # noqa: E402

pytestmark = pytest.mark.e2e


@pytest.fixture
def lighting_scene():
    if tuple(bpy.app.version) < (5, 0, 0):
        pytest.skip("the photographic lighting contract targets Blender 5")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_cube_add(size=0.067, location=(0.0, 0.0, 0.035))
    hero = bpy.context.object
    hero.name = "E2E Light Hero"
    bpy.ops.mesh.primitive_cube_add(size=0.2, location=(0.0, 0.3, 0.1))
    background = bpy.context.object
    background.name = "E2E Light Background"
    return hero, background


def test_motivated_lamp_round_trip(lighting_scene):
    hero, background = lighting_scene
    configure = load_skill("blender-photographic-lighting", "configure_motivated_lighting")
    validate = load_skill("blender-photographic-lighting", "validate_motivated_lighting")

    result = configure.main(
        source_name="E2E Lamp Key",
        source_type="LAMP",
        energy=120.0,
        hero_object=hero.name,
        background_object=background.name,
    )
    assert result["success"] is True, result

    report = validate.main(
        source_name="E2E Lamp Key",
        source_type="LAMP",
        hero_object=hero.name,
        background_object=background.name,
    )
    assert report["success"] is True, report
    assert report["context"]["valid"] is True, report
    assert report["context"]["color_safety"]["exposure"] == pytest.approx(0.0)


def test_outdoor_hdri_uses_a_tight_sun(tmp_path):
    image = bpy.data.images.new("E2E HDRI", width=1, height=1, alpha=False)
    image.pixels = [0.5, 0.5, 0.5, 1.0]
    hdri_path = tmp_path / "sky.hdr"
    image.filepath_raw = str(hdri_path)
    image.file_format = "HDR"
    image.save()
    bpy.data.images.remove(image)
    configure = load_skill("blender-photographic-lighting", "configure_motivated_lighting")
    validate = load_skill("blender-photographic-lighting", "validate_motivated_lighting")

    result = configure.main(
        source_name="E2E Outdoor Sun",
        source_type="OUTDOOR_HDRI",
        energy=2.0,
        hdri_path=str(hdri_path),
        hdri_strength=0.35,
    )
    assert result["success"] is True, result
    report = validate.main(source_name="E2E Outdoor Sun", source_type="OUTDOOR_HDRI")
    assert report["success"] is True, report
    assert report["context"]["source"]["angle_degrees"] == pytest.approx(1.2)
