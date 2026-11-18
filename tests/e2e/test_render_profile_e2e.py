"""Exercise the photographic render-profile skill in real Blender."""

from __future__ import annotations

import pytest

bpy = pytest.importorskip("bpy", reason="requires a real Blender interpreter")

from tests.e2e.conftest import load_skill  # noqa: E402

pytestmark = pytest.mark.e2e


@pytest.fixture
def scene():
    if tuple(bpy.app.version) < (5, 0, 0):
        pytest.skip("the photographic profile targets Blender 5")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    return bpy.context.scene


def test_preview_profile_round_trips_through_native_blender(scene):
    capabilities = load_skill("blender-render-profile", "get_render_capabilities").main()
    assert capabilities["success"] is True, capabilities
    assert capabilities["context"]["blender_version"][0] >= 5

    applied = load_skill("blender-render-profile", "apply_render_profile").main(
        profile_name="PREVIEW",
        device_backend="CPU",
    )
    assert applied["success"] is True, applied
    assert scene.render.engine == "CYCLES"
    assert scene.render.resolution_percentage == 25
    assert scene.cycles.samples == 32
    assert scene.render.image_settings.file_format == "JPEG"

    read = load_skill("blender-render-profile", "get_render_profile").main()
    assert read["success"] is True, read
    assert read["context"]["current"]["scene_device"] == "CPU"

    validation = load_skill("blender-render-profile", "validate_render_profile").main(
        profile_name="PREVIEW",
        device_backend="CPU",
    )
    assert validation["success"] is True, validation
    assert validation["context"]["valid"] is True, validation
