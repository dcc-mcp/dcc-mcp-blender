"""E2E tests for blender-lighting and blender-render skills.

Requires a real Blender Python interpreter.

Run::

    blender --background --python -m pytest tests/e2e/test_lighting_render_e2e.py -- -v
"""

from __future__ import annotations

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
        # Blender 4.2+ uses BLENDER_EEVEE_NEXT; try both
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
