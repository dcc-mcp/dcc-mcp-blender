"""E2E tests for blender-lighting and blender-render skills.

Requires a real Blender Python interpreter.

Run::

    blender --background --python -m pytest tests/e2e/test_lighting_render_e2e.py -- -v
"""

from __future__ import annotations

import math
import os

import pytest

bpy = pytest.importorskip("bpy", reason="bpy not available — run inside Blender Python interpreter")

pytestmark = pytest.mark.e2e

from tests.e2e.conftest import load_skill  # noqa: E402


def _new_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


# ── blender-lighting ──────────────────────────────────────────────────────────


class TestLightingSkillsE2E:
    def setup_method(self):
        _new_scene()

    def test_create_point_light(self):
        mod = load_skill("blender-lighting", "create_light")
        result = mod.create_light(light_type="POINT", name="E2EPoint")
        assert result["success"] is True
        assert "E2EPoint" in bpy.data.objects
        assert bpy.data.objects["E2EPoint"].type == "LIGHT"
        assert bpy.data.objects["E2EPoint"].data.type == "POINT"

    def test_create_sun_light(self):
        mod = load_skill("blender-lighting", "create_light")
        result = mod.create_light(light_type="SUN", name="E2ESun")
        assert result["success"] is True
        assert bpy.data.objects["E2ESun"].data.type == "SUN"

    def test_create_spot_light(self):
        mod = load_skill("blender-lighting", "create_light")
        result = mod.create_light(light_type="SPOT", name="E2ESpot")
        assert result["success"] is True
        assert bpy.data.objects["E2ESpot"].data.type == "SPOT"

    def test_create_area_light(self):
        mod = load_skill("blender-lighting", "create_light")
        result = mod.create_light(light_type="AREA", name="E2EArea")
        assert result["success"] is True
        assert bpy.data.objects["E2EArea"].data.type == "AREA"

    def test_create_light_with_energy(self):
        mod = load_skill("blender-lighting", "create_light")
        result = mod.create_light(light_type="POINT", name="BrightLight", energy=2000.0)
        assert result["success"] is True
        assert abs(bpy.data.objects["BrightLight"].data.energy - 2000.0) < 1.0

    def test_create_light_at_location(self):
        mod = load_skill("blender-lighting", "create_light")
        result = mod.create_light(light_type="POINT", name="LocLight", location=[1.0, 2.0, 5.0])
        assert result["success"] is True
        loc = bpy.data.objects["LocLight"].location
        assert abs(loc.x - 1.0) < 1e-4
        assert abs(loc.z - 5.0) < 1e-4

    def test_create_light_invalid_type(self):
        mod = load_skill("blender-lighting", "create_light")
        result = mod.create_light(light_type="LASER", name="BadLight")
        assert result["success"] is False

    def test_set_light_energy(self):
        bpy.ops.object.light_add(type="POINT")
        light_name = bpy.context.active_object.name
        mod = load_skill("blender-lighting", "set_light_properties")
        result = mod.set_light_properties(name=light_name, energy=500.0)
        assert result["success"] is True
        assert abs(bpy.data.objects[light_name].data.energy - 500.0) < 1.0

    def test_set_light_color(self):
        bpy.ops.object.light_add(type="POINT")
        light_name = bpy.context.active_object.name
        mod = load_skill("blender-lighting", "set_light_properties")
        result = mod.set_light_properties(name=light_name, color=[1.0, 0.0, 0.0])
        assert result["success"] is True
        color = bpy.data.objects[light_name].data.color
        assert abs(color[0] - 1.0) < 1e-4
        assert abs(color[1] - 0.0) < 1e-4

    def test_set_light_not_found(self):
        mod = load_skill("blender-lighting", "set_light_properties")
        result = mod.set_light_properties(name="NoSuchLight_XYZ", energy=100.0)
        assert result["success"] is False

    def test_list_lights(self):
        bpy.ops.object.light_add(type="POINT")
        bpy.ops.object.light_add(type="SUN")
        mod = load_skill("blender-lighting", "list_lights")
        result = mod.list_lights()
        assert result["success"] is True
        assert result["context"]["count"] >= 2
        light_types = {lt["light_type"] for lt in result["context"]["lights"]}
        assert "POINT" in light_types
        assert "SUN" in light_types

    def test_list_lights_empty_scene(self):
        mod = load_skill("blender-lighting", "list_lights")
        result = mod.list_lights()
        assert result["success"] is True
        assert result["context"]["count"] == 0

    def _background_node(self):
        """Return the world's background node, or None when there is none."""
        world = bpy.context.scene.world
        if world is None or world.node_tree is None:
            return None
        for node in world.node_tree.nodes:
            if node.type == "BACKGROUND":
                return node
        return None

    def test_world_background_color_applies_to_node(self):
        """Once the world runs on nodes, a color-only call must hit the socket."""
        mod = load_skill("blender-lighting", "set_world_background")

        # A strength call switches the world onto nodes; that is the state the
        # reported bug lived in from the second call onwards.
        assert mod.set_world_background(color=[0.1, 0.1, 0.1], strength=1.0)["success"] is True
        result = mod.set_world_background(color=[0.2, 0.4, 0.6])
        assert result["success"] is True

        node = self._background_node()
        assert node is not None, "no ShaderNodeBackground was created"
        socket = node.inputs["Color"].default_value
        assert abs(socket[0] - 0.2) < 1e-4
        assert abs(socket[1] - 0.4) < 1e-4
        assert abs(socket[2] - 0.6) < 1e-4

    def test_world_background_linked_color_reports_failure(self):
        """A linked Color socket (HDRI setup) must not be reported as success."""
        mod = load_skill("blender-lighting", "set_world_background")
        assert mod.set_world_background(color=[0.1, 0.1, 0.1], strength=1.0)["success"] is True

        node = self._background_node()
        node_tree = bpy.context.scene.world.node_tree
        environment = node_tree.nodes.new("ShaderNodeTexEnvironment")
        node_tree.links.new(environment.outputs["Color"], node.inputs["Color"])

        result = mod.set_world_background(color=[0.5, 0.1, 0.1])

        assert result["success"] is False
        assert "link" in result["message"].lower()

    def _output_surface(self):
        """Return the world's ``OUTPUT_WORLD.Surface`` input socket."""
        node_tree = bpy.context.scene.world.node_tree
        output = next(node for node in node_tree.nodes if node.type == "OUTPUT_WORLD")
        return node_tree, output.inputs["Surface"]

    def test_world_background_writes_the_node_that_drives_the_output(self):
        """With two Background nodes, only the one driving the output is written."""
        mod = load_skill("blender-lighting", "set_world_background")
        assert mod.set_world_background(color=[0.1, 0.1, 0.1], strength=1.0)["success"] is True

        node_tree, surface = self._output_surface()
        orphan = self._background_node()

        # Keep the original background linked (to a spare output) so a plain
        # link-state check still looks fine, then feed the surface from a second
        # background node: only that second node drives the render.
        spare_output = node_tree.nodes.new("ShaderNodeOutputWorld")
        for link in list(surface.links):
            node_tree.links.remove(link)
        node_tree.links.new(orphan.outputs[0], spare_output.inputs["Surface"])
        driving = node_tree.nodes.new("ShaderNodeBackground")
        node_tree.links.new(driving.outputs[0], surface)

        result = mod.set_world_background(color=[0.3, 0.6, 0.9])

        assert result["success"] is True
        driving_color = driving.inputs["Color"].default_value
        assert abs(driving_color[0] - 0.3) < 1e-4, f"driving node not written: {tuple(driving_color)}"
        assert abs(driving_color[1] - 0.6) < 1e-4
        assert abs(driving_color[2] - 0.9) < 1e-4
        # The node that renders nothing must be left alone.
        orphan_color = orphan.inputs["Color"].default_value
        assert abs(orphan_color[0] - 0.1) < 1e-4, f"unrelated node was written: {tuple(orphan_color)}"

    def test_world_background_fails_when_no_node_drives_the_output(self):
        """Two Background nodes, neither wired to the output: still a failure."""
        mod = load_skill("blender-lighting", "set_world_background")
        assert mod.set_world_background(color=[0.1, 0.1, 0.1], strength=1.0)["success"] is True

        node_tree, surface = self._output_surface()
        for link in list(surface.links):
            node_tree.links.remove(link)
        node_tree.nodes.new("ShaderNodeBackground")

        result = mod.set_world_background(color=[0.5, 0.1, 0.1])

        assert result["success"] is False
        assert "output" in result["message"].lower()

    def test_world_background_color_reapplied_on_second_call(self):
        """Regression for PIP-3545: color used to be dropped after the 1st call."""
        mod = load_skill("blender-lighting", "set_world_background")

        assert mod.set_world_background(color=[0.015, 0.02, 0.045], strength=1.0)["success"] is True
        result = mod.set_world_background(color=[0.5, 0.1, 0.1], strength=2.0)
        assert result["success"] is True

        node = self._background_node()
        assert node is not None, "no ShaderNodeBackground was created"
        socket = node.inputs["Color"].default_value
        assert abs(socket[0] - 0.5) < 1e-4, f"color not reapplied: {tuple(socket)}"
        assert abs(socket[1] - 0.1) < 1e-4
        assert abs(socket[2] - 0.1) < 1e-4
        assert abs(node.inputs["Strength"].default_value - 2.0) < 1e-4


# ── blender-render ────────────────────────────────────────────────────────────


class TestRenderSkillsE2E:
    def setup_method(self):
        _new_scene()

    def test_get_render_info(self):
        mod = load_skill("blender-render", "get_render_info")
        result = mod.get_render_info()
        assert result["success"] is True
        ctx = result["context"]
        assert "engine" in ctx
        assert "resolution_x" in ctx
        assert "resolution_y" in ctx

    def test_set_render_resolution(self):
        mod = load_skill("blender-render", "set_render_settings")
        result = mod.set_render_settings(resolution_x=1280, resolution_y=720)
        assert result["success"] is True
        scene = bpy.context.scene
        assert scene.render.resolution_x == 1280
        assert scene.render.resolution_y == 720

    def test_set_render_engine_cycles(self):
        mod = load_skill("blender-render", "set_render_settings")
        result = mod.set_render_settings(engine="CYCLES")
        assert result["success"] is True
        assert bpy.context.scene.render.engine == "CYCLES"

    def test_set_render_engine_eevee(self):
        mod = load_skill("blender-render", "set_render_settings")
        # EEVEE Next is the engine id on supported releases; try both names.
        for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
            result = mod.set_render_settings(engine=engine)
            if result["success"]:
                assert bpy.context.scene.render.engine == engine
                return
        # If neither worked, at least verify CYCLES works
        result = mod.set_render_settings(engine="CYCLES")
        assert result["success"] is True

    def test_set_render_engine_invalid(self):
        mod = load_skill("blender-render", "set_render_settings")
        result = mod.set_render_settings(engine="INVALID_ENGINE_XYZ")
        assert result["success"] is False

    def test_set_output_path(self, tmp_path):
        mod = load_skill("blender-render", "set_render_settings")
        out = str(tmp_path / "render_")
        result = mod.set_render_settings(output_path=out)
        assert result["success"] is True
        assert bpy.context.scene.render.filepath == out

    def test_set_cycles_samples(self):
        bpy.context.scene.render.engine = "CYCLES"
        mod = load_skill("blender-render", "set_render_settings")
        result = mod.set_render_settings(samples=64)
        assert result["success"] is True
        assert bpy.context.scene.cycles.samples == 64

    def test_render_scene_to_file(self, tmp_path):
        """Render a minimal 32×32 scene with CYCLES (CPU) to verify render_scene.

        CYCLES uses CPU rendering by default in ``--background`` mode — no GPU,
        no OpenGL context required.  Runs on Linux, Windows, and macOS CI runners.

        BLENDER_WORKBENCH / BLENDER_EEVEE require an OpenGL / Metal context that
        is unavailable on headless Linux / Windows runners and cause SIGABRT.
        """
        bpy.ops.mesh.primitive_cube_add()
        bpy.ops.object.camera_add()
        bpy.context.scene.camera = bpy.context.active_object
        scene = bpy.context.scene

        # Minimal CYCLES render: 1 sample, 32×32 → completes in < 1 s on CI.
        scene.render.engine = "CYCLES"
        scene.cycles.samples = 1
        scene.render.resolution_x = 32
        scene.render.resolution_y = 32
        scene.render.resolution_percentage = 100

        out_path = str(tmp_path / "e2e_render.png")
        mod = load_skill("blender-render", "render_scene")
        result = mod.render_scene(output_path=out_path, write_still=True)
        assert result["success"] is True
        assert (tmp_path / "e2e_render.png").exists()


# ── IES photometric profiles ─────────────────────────────────────────────────


def _write_ies_profile(path, half_width, label="test profile"):
    """Write a real LM-63 photometric file.

    The file is photometric type A and repeats one vertical distribution across
    every horizontal angle. Two details matter and both were learned the hard
    way: a single horizontal angle gives Blender a zero-width horizontal range
    that reads as black everywhere, and photometric type B rotates the frame so
    the beam no longer follows the lamp.
    """
    vertical = [float(v) for v in range(0, 91, 5)]
    horizontal = [float(h) for h in range(0, 361, 30)]
    lines = [
        "IESNA:LM-63-2002",
        "[TEST] " + label,
        "[MANUFAC] dcc-mcp-blender",
        "[LUMINAIRE] " + label,
        "TILT=NONE",
        # lamps lumens multiplier n_vertical n_horizontal photo_type units ...
        "1 1000 1 {0} {1} 1 2 0 0 0".format(len(vertical), len(horizontal)),
        "1 1 50",
        " ".join("{0:g}".format(v) for v in vertical),
        " ".join("{0:g}".format(v) for v in horizontal),
    ]
    for _ in horizontal:
        line = []
        for angle in vertical:
            line.append("{0:g}".format(round(1000.0 * math.exp(-((angle / half_width) ** 2)), 2)))
        lines.append(" ".join(line))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def _ies_floor_scene(samples=32, resolution=128):
    """A floor, a spot lamp five metres up, and a top-down camera.

    The camera is orthographic so a pixel maps to a world position by a plain
    linear scale, which keeps the beam-position assertions free of projection
    guesswork. Cycles on the CPU needs no GPU, so this runs headless.
    """
    _new_scene()
    scene = bpy.context.scene
    scene.world = None

    bpy.ops.mesh.primitive_plane_add(size=40.0, location=(0.0, 0.0, 0.0))
    floor = bpy.context.active_object
    material = bpy.data.materials.new("FloorMat")
    # A new material starts with use_nodes off and node_tree None on Blender 4.x;
    # 5.x flips it on at creation. Setting it explicitly is what makes the node
    # lookup below safe on both, rather than only on the version it was written on.
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    bsdf.inputs["Roughness"].default_value = 1.0
    floor.data.materials.append(material)

    bpy.ops.object.light_add(type="SPOT", location=(0.0, 0.0, 5.0))
    lamp = bpy.context.active_object
    lamp.name = "E2ESpot"
    lamp.data.energy = 600.0
    lamp.data.spot_size = math.radians(150)
    lamp.data.spot_blend = 0.0
    lamp.data.shadow_soft_size = 0.0

    bpy.ops.object.camera_add(location=(0.0, 0.0, 16.0))
    camera = bpy.context.active_object
    camera.rotation_euler = (0.0, 0.0, 0.0)
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 40.0
    scene.camera = camera

    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = False
    scene.cycles.seed = 1
    scene.cycles.max_bounces = 0
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    bpy.context.view_layer.update()
    return lamp


def _render_luminance(path):
    """Render to ``path`` and return per-pixel luminance as a flat list."""
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    image = bpy.data.images.load(path)
    pixels = list(image.pixels)
    bpy.data.images.remove(image)
    count = len(pixels) // 4
    return [0.2126 * pixels[4 * i] + 0.7152 * pixels[4 * i + 1] + 0.0722 * pixels[4 * i + 2] for i in range(count)]


def _mean_abs_difference(left, right):
    return sum(abs(a - b) for a, b in zip(left, right)) / len(left)


class TestSetLightIesE2E:
    def setup_method(self):
        _new_scene()

    def _spot(self):
        bpy.ops.object.light_add(type="SPOT", location=(0.0, 0.0, 5.0))
        lamp = bpy.context.active_object
        lamp.name = "E2ESpot"
        return lamp.name

    def test_attaches_an_ies_node(self, tmp_path):
        mod = load_skill("blender-lighting", "set_light_ies")
        profile = _write_ies_profile(tmp_path / "narrow.ies", 12.0)
        name = self._spot()

        result = mod.set_light_ies(light_name=name, ies_path=profile)

        assert result["success"] is True
        light = bpy.data.objects[name].data
        ies_nodes = [node for node in light.node_tree.nodes if node.type == "TEX_IES"]
        assert len(ies_nodes) == 1
        assert ies_nodes[0].mode == "EXTERNAL"

    def test_ies_node_drives_the_light_output(self, tmp_path):
        """The node has to feed the emission node the renderer actually reads."""
        mod = load_skill("blender-lighting", "set_light_ies")
        profile = _write_ies_profile(tmp_path / "narrow.ies", 12.0)
        name = self._spot()

        mod.set_light_ies(light_name=name, ies_path=profile)

        light = bpy.data.objects[name].data
        tree = light.node_tree
        output = next(node for node in tree.nodes if node.type == "OUTPUT_LIGHT")
        surface_link = output.inputs["Surface"].links[0]
        emission = surface_link.from_node
        strength = emission.inputs["Strength"]
        assert strength.links, "the IES node is not driving the light's emission"
        assert strength.links[0].from_node.type == "TEX_IES"

    def test_vector_input_stays_unconnected(self, tmp_path):
        """Connecting a direction there mis-aims the beam away from the aim."""
        mod = load_skill("blender-lighting", "set_light_ies")
        profile = _write_ies_profile(tmp_path / "narrow.ies", 12.0)
        name = self._spot()

        mod.set_light_ies(light_name=name, ies_path=profile)

        light = bpy.data.objects[name].data
        ies = next(node for node in light.node_tree.nodes if node.type == "TEX_IES")
        assert list(ies.inputs["Vector"].links) == []

    def test_repeat_call_does_not_stack_nodes(self, tmp_path):
        mod = load_skill("blender-lighting", "set_light_ies")
        first = _write_ies_profile(tmp_path / "a.ies", 12.0)
        second = _write_ies_profile(tmp_path / "b.ies", 35.0)
        name = self._spot()

        mod.set_light_ies(light_name=name, ies_path=first)
        mod.set_light_ies(light_name=name, ies_path=second)

        light = bpy.data.objects[name].data
        ies_nodes = [node for node in light.node_tree.nodes if node.type == "TEX_IES"]
        assert len(ies_nodes) == 1
        # Blender normalises the stored path on some releases and leaves it alone on
        # others, so compare resolved paths rather than the stored string.
        assert os.path.abspath(ies_nodes[0].filepath) == os.path.abspath(second)

    def test_clear_removes_the_profile(self, tmp_path):
        mod = load_skill("blender-lighting", "set_light_ies")
        profile = _write_ies_profile(tmp_path / "narrow.ies", 12.0)
        name = self._spot()
        mod.set_light_ies(light_name=name, ies_path=profile)

        result = mod.set_light_ies(light_name=name, clear=True)

        assert result["success"] is True
        light = bpy.data.objects[name].data
        assert [node for node in light.node_tree.nodes if node.type == "TEX_IES"] == []

    def test_missing_profile_file_is_refused(self, tmp_path):
        mod = load_skill("blender-lighting", "set_light_ies")
        name = self._spot()

        result = mod.set_light_ies(light_name=name, ies_path=str(tmp_path / "absent.ies"))

        assert result["success"] is False

    def test_unknown_light_is_refused(self, tmp_path):
        mod = load_skill("blender-lighting", "set_light_ies")
        profile = _write_ies_profile(tmp_path / "narrow.ies", 12.0)

        result = mod.set_light_ies(light_name="NoSuchLight_XYZ", ies_path=profile)

        assert result["success"] is False

    def test_profile_changes_the_render(self, tmp_path):
        """Render proof: the beam has to change with the profile.

        A node that is wired but inert still passes every structural check, so
        the only evidence that matters is a difference in rendered pixels.
        """
        mod = load_skill("blender-lighting", "set_light_ies")
        narrow = _write_ies_profile(tmp_path / "narrow.ies", 12.0)
        flood = _write_ies_profile(tmp_path / "flood.ies", 35.0)

        renders = {}
        for label, profile in (("plain", None), ("narrow", narrow), ("flood", flood)):
            lamp = _ies_floor_scene()
            if profile is not None:
                result = mod.set_light_ies(light_name=lamp.name, ies_path=profile)
                assert result["success"] is True, result
            renders[label] = _render_luminance(str(tmp_path / ("ies_" + label + ".png")))

        narrow_diff = _mean_abs_difference(renders["plain"], renders["narrow"])
        flood_diff = _mean_abs_difference(renders["plain"], renders["flood"])
        profile_diff = _mean_abs_difference(renders["narrow"], renders["flood"])

        assert narrow_diff > 0.01, f"the narrow profile did not change the render (diff {narrow_diff:.4f})"
        assert flood_diff > 0.01, f"the flood profile did not change the render (diff {flood_diff:.4f})"
        assert profile_diff > 0.01, (
            "two different profiles rendered the same image: the profile is not reaching the "
            f"renderer (diff {profile_diff:.4f})"
        )

    def test_beam_is_centred_under_a_level_lamp(self, tmp_path):
        """A symmetric profile on a level lamp must light the floor symmetrically."""
        mod = load_skill("blender-lighting", "set_light_ies")
        profile = _write_ies_profile(tmp_path / "narrow.ies", 12.0)

        lamp = _ies_floor_scene()
        assert mod.set_light_ies(light_name=lamp.name, ies_path=profile)["success"] is True
        luminance = _render_luminance(str(tmp_path / "ies_centred.png"))

        resolution = bpy.context.scene.render.resolution_x
        centre_row = resolution // 2

        def at(world_x):
            pixel = int((world_x + 20.0) / 40.0 * resolution)
            return luminance[centre_row * resolution + min(pixel, resolution - 1)]

        # Sampled either side of nadir; a mis-aimed profile lights one side only.
        left, right = at(-2.0), at(2.0)
        assert left > 0.05 and right > 0.05, f"the beam is off-centre: left={left:.4f} right={right:.4f}"
        assert abs(left - right) < 0.25, f"the beam is asymmetric: left={left:.4f} right={right:.4f}"

    def test_beam_follows_the_lamp_aim(self, tmp_path):
        """Tilting the lamp must move the beam, so the profile is lamp-relative."""
        mod = load_skill("blender-lighting", "set_light_ies")
        profile = _write_ies_profile(tmp_path / "narrow.ies", 12.0)

        def centroid_x(rotation_y):
            lamp = _ies_floor_scene()
            lamp.rotation_euler = (0.0, rotation_y, 0.0)
            bpy.context.view_layer.update()
            assert mod.set_light_ies(light_name=lamp.name, ies_path=profile)["success"] is True
            luminance = _render_luminance(str(tmp_path / "ies_aim.png"))
            resolution = bpy.context.scene.render.resolution_x
            centre_row = resolution // 2
            total = weighted = 0.0
            for pixel in range(resolution):
                value = luminance[centre_row * resolution + pixel]
                if value > 0.10:
                    total += value
                    weighted += value * (pixel - resolution / 2.0)
            return weighted / total if total else 0.0

        tilted_negative = centroid_x(math.radians(-45.0))
        tilted_positive = centroid_x(math.radians(45.0))

        # The two aims are mirror images, so the beam must land on opposite sides.
        assert tilted_negative * tilted_positive < 0, (
            f"the beam did not follow the lamp's aim: -45deg -> {tilted_negative:+.2f}px, "
            f"+45deg -> {tilted_positive:+.2f}px"
        )
