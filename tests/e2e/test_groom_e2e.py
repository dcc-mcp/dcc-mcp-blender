"""Real-Blender acceptance tests for the guide-curve groom skill."""

from __future__ import annotations

import pytest

bpy = pytest.importorskip("bpy", reason="bpy not available - run inside Blender Python interpreter")

pytestmark = pytest.mark.e2e

from tests.e2e.conftest import load_skill  # noqa: E402


def _new_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


class TestGroomE2E:
    def setup_method(self):
        _new_scene()

    def test_create_inspect_and_style_guides(self):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8)
        scalp = bpy.context.active_object
        scalp.name = "Scalp"

        create_mod = load_skill("blender-groom", "create_groom_guides")
        created = create_mod.create_groom_guides(
            scalp_object_name="Scalp",
            groom_name="Hair Groom",
            guide_count=32,
            segments=4,
            length=0.2,
            width=0.002,
            seed=23,
        )
        assert created["success"] is True
        assert created["context"]["guide_count"] == 32
        assert created["context"]["point_count"] == 128

        inspect_mod = load_skill("blender-groom", "inspect_grooms")
        inspected = inspect_mod.inspect_grooms(object_name="Hair Groom")
        assert inspected["success"] is True
        assert inspected["context"]["groom"]["guide_count"] == 32

        style_mod = load_skill("blender-groom", "set_groom_style")
        styled = style_mod.set_groom_style(object_name="Hair Groom", length_scale=0.5, width=0.004)
        assert styled["success"] is True
        assert styled["context"]["style"]["length_scale"] == 0.5
        assert bpy.data.objects["Hair Groom"].data.bevel_depth == pytest.approx(0.004)
