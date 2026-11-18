"""Exercise photographic camera setup in a native Blender process."""

from __future__ import annotations

import pytest

bpy = pytest.importorskip("bpy", reason="requires a real Blender interpreter")

from tests.e2e.conftest import load_skill  # noqa: E402

pytestmark = pytest.mark.e2e


@pytest.fixture
def camera_scene():
    if tuple(bpy.app.version) < (5, 0, 0):
        pytest.skip("the photographic camera contract targets Blender 5")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    camera_data = bpy.data.cameras.new("E2E Photo Camera")
    camera = bpy.data.objects.new("E2E Photo Camera", camera_data)
    bpy.context.scene.collection.objects.link(camera)
    eyes = bpy.data.objects.new("E2E Toy Eyes", None)
    bpy.context.scene.collection.objects.link(eyes)
    return camera, eyes


def test_photographic_camera_round_trip(camera_scene):
    camera, eyes = camera_scene
    configure = load_skill("blender-photographic-camera", "configure_photographic_camera")
    animate = load_skill("blender-photographic-camera", "animate_photographic_camera")
    validate = load_skill("blender-photographic-camera", "validate_photographic_camera")

    configured = configure.main(
        camera_name=camera.name,
        shot_type="CHARACTER",
        lens=50,
        aperture_fstop=4.0,
        focus_object=eyes.name,
        camera_height_cm=4.0,
    )
    assert configured["success"] is True, configured

    animated = animate.main(
        camera_name=camera.name,
        frame_start=1,
        frame_end=24,
        start_location=[0.0, -0.4, 0.04],
        end_location=[0.02, -0.35, 0.04],
        start_rotation_degrees=[70.0, 0.0, 0.0],
        end_rotation_degrees=[72.0, 0.0, 2.0],
    )
    assert animated["success"] is True, animated

    report = validate.main(
        camera_name=camera.name,
        shot_type="CHARACTER",
        frame_start=1,
        frame_end=24,
    )
    assert report["success"] is True, report
    assert report["context"]["valid"] is True, report
    assert report["context"]["camera"]["sensor_width"] == pytest.approx(36.0)
    assert report["context"]["animation"]["keyframe_count"] >= 8
