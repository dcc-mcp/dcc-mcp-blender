"""E2E tests for light rig and environment skills."""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import pytest

bpy = pytest.importorskip("bpy", reason="bpy not available - run inside Blender Python interpreter")

pytestmark = pytest.mark.e2e

from mathutils import Vector  # noqa: E402

from tests.e2e.conftest import load_skill  # noqa: E402


def _new_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def _write_white_hdri(image_path: Path):
    image = bpy.data.images.new("E2EHDRI", width=4, height=2, alpha=False, float_buffer=True)
    image.pixels = [1.0, 1.0, 1.0, 1.0] * 8
    image.filepath_raw = str(image_path)
    image.file_format = "HDR"
    image.save()


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
            image_path = Path(tmp) / "studio.hdr"
            _write_white_hdri(image_path)

            hdri_mod = load_skill("blender-light-rig", "create_hdri_world")
            hdri = hdri_mod.create_hdri_world(image_path=str(image_path), strength=0.5, rotation=15.0)
            assert hdri["success"] is True
            assert hdri["context"]["coordinate_output"] == "Normal"
            assert bpy.context.scene.world.use_nodes is True
            world = bpy.context.scene.world
            mapping = bpy.context.scene.world.node_tree.nodes.get("DCC MCP Mapping")
            assert mapping is not None
            assert round(mapping.inputs["Rotation"].default_value[2], 3) == round(math.radians(15.0), 3)
            coordinate_link = next(
                link
                for link in world.node_tree.links
                if link.to_node.name == mapping.name and link.to_socket.name == "Vector"
            )
            assert coordinate_link.from_socket.name == "Normal"

            animate_mod = load_skill("blender-light-rig", "animate_hdri_rotation")
            animated = animate_mod.animate_hdri_rotation(
                frame_start=1,
                frame_end=61,
                start_rotation=0.0,
                end_rotation=360.0,
                interpolation="LINEAR",
            )
            assert animated["success"] is True
            bpy.context.scene.frame_set(31)
            assert round(mapping.inputs["Rotation"].default_value[2], 3) == round(math.pi, 3)

        view_mod = load_skill("blender-light-rig", "set_render_view_transform")
        view = view_mod.set_render_view_transform(view_transform="Standard", exposure=0.1)
        assert view["success"] is True
        assert bpy.context.scene.view_settings.view_transform == "Standard"

        summary_mod = load_skill("blender-light-rig", "get_lighting_summary")
        summary = summary_mod.get_lighting_summary()
        assert summary["success"] is True
        assert summary["context"]["light_count"] >= 3
        assert summary["context"]["rigs"][0]["rig_name"] == "E2ERig"
        assert summary["context"]["world"]["hdri"]["coordinate_output"] == "Normal"
        assert summary["context"]["world"]["hdri"]["animation"]["frame_end"] == 61

    def test_hdri_world_lights_diffuse_subject(self):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=1.0)
        sphere = bpy.context.object
        material = bpy.data.materials.new("E2EMatte")
        material.use_nodes = True
        principled = material.node_tree.nodes.get("Principled BSDF")
        principled.inputs["Base Color"].default_value = (0.8, 0.8, 0.8, 1.0)
        principled.inputs["Roughness"].default_value = 1.0
        sphere.data.materials.append(material)

        camera_data = bpy.data.cameras.new("E2ECamera")
        camera = bpy.data.objects.new("E2ECamera", camera_data)
        bpy.context.scene.collection.objects.link(camera)
        camera.location = (0.0, -4.0, 0.0)
        camera.rotation_euler = (Vector((0.0, 0.0, 0.0)) - camera.location).to_track_quat("-Z", "Y").to_euler()
        bpy.context.scene.camera = camera

        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "white_studio.hdr"
            render_path = Path(tmp) / "hdri_lighting_probe.png"
            _write_white_hdri(image_path)
            hdri_mod = load_skill("blender-light-rig", "create_hdri_world")
            hdri = hdri_mod.create_hdri_world(image_path=str(image_path), strength=1.0)
            assert hdri["success"] is True

            scene = bpy.context.scene
            scene.render.engine = "CYCLES"
            scene.cycles.samples = 4
            scene.cycles.use_denoising = False
            scene.cycles.max_bounces = 2
            scene.cycles.diffuse_bounces = 1
            scene.cycles.glossy_bounces = 1
            scene.render.resolution_x = 32
            scene.render.resolution_y = 32
            scene.render.resolution_percentage = 100
            scene.render.film_transparent = True
            scene.render.image_settings.file_format = "PNG"
            scene.render.filepath = str(render_path)
            scene.view_settings.view_transform = "Standard"
            scene.view_settings.look = "None"
            bpy.ops.render.render(write_still=True)

            rendered = bpy.data.images.load(str(render_path), check_existing=False)
            width, height = rendered.size
            center = ((height // 2) * width + width // 2) * 4
            center_rgb = list(rendered.pixels[center : center + 3])
            assert sum(center_rgb) / 3.0 > 0.05
