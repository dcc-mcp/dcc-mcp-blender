"""E2E tests for light rig and environment skills."""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import pytest

bpy = pytest.importorskip("bpy", reason="bpy not available - run inside Blender Python interpreter")

pytestmark = pytest.mark.e2e

from tests.e2e.conftest import load_skill  # noqa: E402


def _new_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


class TestLightRigE2E:
    def setup_method(self):
        _new_scene()

    def test_create_light_rig_hdri_world_and_summary(self):
        bpy.ops.mesh.primitive_cube_add()
        cube_name = bpy.context.object.name

        rig_mod = load_skill("blender-light-rig", "create_three_point_light_rig")
        rig = rig_mod.create_three_point_light_rig(name="E2ERig", target_object=cube_name)
        assert rig["success"] is True
        assert len(rig["context"]["lights"]) == 3
        for light in rig["context"]["lights"]:
            assert light["name"] in bpy.data.objects

        intensity_mod = load_skill("blender-light-rig", "set_light_rig_intensity")
        intensity = intensity_mod.set_light_rig_intensity(rig_name="E2ERig", multiplier=0.25)
        assert intensity["success"] is True
        assert intensity["context"]["lights"][0]["energy"] > 0

        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "studio.png"
            image = bpy.data.images.new("E2EHDRI", width=2, height=2, alpha=True)
            image.filepath_raw = str(image_path)
            image.file_format = "PNG"
            image.save()

            hdri_mod = load_skill("blender-light-rig", "create_hdri_world")
            hdri = hdri_mod.create_hdri_world(image_path=str(image_path), strength=0.5, rotation=15.0)
            assert hdri["success"] is True
            assert bpy.context.scene.world.use_nodes is True
            mapping = bpy.context.scene.world.node_tree.nodes.get("DCC MCP Mapping")
            assert mapping is not None
            assert round(mapping.inputs["Rotation"].default_value[2], 3) == round(math.radians(15.0), 3)

        view_mod = load_skill("blender-light-rig", "set_render_view_transform")
        view = view_mod.set_render_view_transform(view_transform="Standard", exposure=0.1)
        assert view["success"] is True
        assert bpy.context.scene.view_settings.view_transform == "Standard"

        summary_mod = load_skill("blender-light-rig", "get_lighting_summary")
        summary = summary_mod.get_lighting_summary()
        assert summary["success"] is True
        assert summary["context"]["light_count"] >= 3
        assert summary["context"]["rigs"][0]["rig_name"] == "E2ERig"
