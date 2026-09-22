"""E2E tests for shader nodes, geometry nodes, and physics skills."""

from __future__ import annotations

import pytest

bpy = pytest.importorskip("bpy", reason="bpy not available - run inside Blender Python interpreter")

pytestmark = pytest.mark.e2e

from tests.e2e.conftest import load_skill  # noqa: E402


def _new_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


class TestShaderNodesE2E:
    def setup_method(self):
        _new_scene()

    def test_list_and_update_principled_inputs(self):
        mat = bpy.data.materials.new("E2EShader")
        mat.use_nodes = True

        list_mod = load_skill("blender-shader-nodes", "list_material_nodes")
        list_result = list_mod.list_material_nodes(material_name="E2EShader")
        assert list_result["success"] is True
        assert list_result["context"]["count"] >= 1

        set_mod = load_skill("blender-shader-nodes", "set_principled_input")
        result = set_mod.set_principled_input(
            material_name="E2EShader",
            input_name="Metallic",
            value=0.75,
        )
        assert result["success"] is True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        assert bsdf.inputs["Metallic"].default_value == pytest.approx(0.75)


class TestGeometryNodesE2E:
    def setup_method(self):
        _new_scene()

    def test_add_and_list_geometry_nodes_modifier(self):
        bpy.ops.mesh.primitive_cube_add()
        cube_name = bpy.context.active_object.name

        add_mod = load_skill("blender-geometry-nodes", "add_geometry_nodes_modifier")
        result = add_mod.add_geometry_nodes_modifier(
            object_name=cube_name,
            name="E2E Geometry Nodes",
            group_name="E2E Geometry Group",
        )
        assert result["success"] is True

        list_mod = load_skill("blender-geometry-nodes", "list_geometry_nodes_modifiers")
        list_result = list_mod.list_geometry_nodes_modifiers(object_name=cube_name)
        assert list_result["success"] is True
        assert list_result["context"]["count"] == 1


class TestPhysicsE2E:
    def setup_method(self):
        _new_scene()

    def test_add_update_and_remove_rigid_body(self):
        bpy.ops.mesh.primitive_cube_add()
        cube_name = bpy.context.active_object.name
        cube = bpy.data.objects[cube_name]

        add_mod = load_skill("blender-physics", "add_rigid_body")
        add_result = add_mod.add_rigid_body(object_name=cube_name, mass=2.0, collision_shape="BOX")
        assert add_result["success"] is True
        assert cube.rigid_body is not None

        set_mod = load_skill("blender-physics", "set_rigid_body_properties")
        set_result = set_mod.set_rigid_body_properties(object_name=cube_name, mass=3.0, friction=0.1)
        assert set_result["success"] is True
        assert cube.rigid_body.mass == pytest.approx(3.0)

        remove_mod = load_skill("blender-physics", "remove_rigid_body")
        remove_result = remove_mod.remove_rigid_body(object_name=cube_name)
        assert remove_result["success"] is True

    def test_cloth_collision_status_and_dry_run_cache(self):
        bpy.ops.mesh.primitive_plane_add(size=2.0)
        cloth_name = bpy.context.active_object.name
        cloth_obj = bpy.data.objects[cloth_name]

        add_cloth_mod = load_skill("blender-physics", "add_cloth_modifier")
        cloth_result = add_cloth_mod.add_cloth_modifier(
            object_name=cloth_name,
            name="E2E Cloth",
            settings={"quality": 3, "mass": 0.25},
        )
        assert cloth_result["success"] is True
        assert cloth_obj.modifiers["E2E Cloth"].type == "CLOTH"

        bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0, 0, -1.0))
        collision_name = bpy.context.active_object.name
        collision_obj = bpy.data.objects[collision_name]

        add_collision_mod = load_skill("blender-physics", "add_collision_modifier")
        collision_result = add_collision_mod.add_collision_modifier(
            object_name=collision_name,
            settings={"thickness_outer": 0.08},
        )
        assert collision_result["success"] is True
        assert collision_obj.modifiers["Collision"].type == "COLLISION"

        list_mod = load_skill("blender-physics", "list_simulation_modifiers")
        list_result = list_mod.list_simulation_modifiers()
        assert list_result["success"] is True
        assert list_result["context"]["count"] >= 2

        status_mod = load_skill("blender-physics", "get_simulation_status")
        status_result = status_mod.get_simulation_status(object_name=cloth_name)
        assert status_result["success"] is True
        assert status_result["context"]["modifier_count"] == 1

        bake_mod = load_skill("blender-physics", "bake_simulation")
        bake_result = bake_mod.bake_simulation(
            object_name=cloth_name,
            modifier_name="E2E Cloth",
            frame_start=1,
            frame_end=2,
            dry_run=True,
        )
        assert bake_result["success"] is True
        assert bake_result["context"]["dry_run"] is True

        clear_mod = load_skill("blender-physics", "clear_simulation_cache")
        clear_result = clear_mod.clear_simulation_cache(
            object_name=cloth_name,
            modifier_name="E2E Cloth",
            dry_run=True,
        )
        assert clear_result["success"] is True
        assert clear_result["context"]["dry_run"] is True


class TestFluidE2E:
    """Real-Blender assertions for the Mantaflow fluid paths.

    The unit suite can only mock these, so the property names that
    set_fluid_settings and the fluid_type aliases advertise are pinned here
    against Blender's own RNA. If a name ever moves, this fails on every
    supported Blender version in CI rather than in production.
    """

    def setup_method(self):
        _new_scene()

    def _cube(self, name="E2E Fluid Cube"):
        bpy.ops.mesh.primitive_cube_add()
        obj = bpy.context.active_object
        obj.name = name
        return obj

    def test_add_domain_and_set_domain_settings(self):
        obj = self._cube()

        add_mod = load_skill("blender-physics", "add_fluid_modifier")
        add_result = add_mod.add_fluid_modifier(object_name=obj.name, fluid_type="DOMAIN", name="E2E Domain")
        assert add_result["success"] is True, add_result.get("error")

        modifier = obj.modifiers["E2E Domain"]
        assert modifier.type == "FLUID"
        assert modifier.fluid_type == "DOMAIN"
        # Domain options live on a nested block, not on the modifier itself.
        assert modifier.domain_settings is not None

        set_mod = load_skill("blender-physics", "set_fluid_settings")
        result = set_mod.set_fluid_settings(
            object_name=obj.name,
            modifier_name="E2E Domain",
            domain_settings={"resolution_divisions": 48},
        )
        assert result["success"] is True, result.get("error")
        assert result["context"]["domain_applied"]["resolution_divisions"] == 48
        assert modifier.domain_settings.resolution_divisions == 48

    def test_fluid_type_enum_matches_the_documented_values(self):
        """Every value the tool offers must be assignable to fluid_type."""
        obj = self._cube()
        add_mod = load_skill("blender-physics", "add_fluid_modifier")

        for fluid_type in ("DOMAIN", "FLOW", "EFFECTOR"):
            name = f"E2E {fluid_type}"
            result = add_mod.add_fluid_modifier(object_name=obj.name, fluid_type=fluid_type, name=name)
            assert result["success"] is True, f"{fluid_type}: {result.get('error')}"
            assert obj.modifiers[name].fluid_type == fluid_type

    def test_legacy_fluid_types_are_rejected_without_orphans(self):
        obj = self._cube()
        add_mod = load_skill("blender-physics", "add_fluid_modifier")

        for legacy, needle in (
            ("OBSTACLE", "modifier.effector_settings.effector_type = 'COLLISION'"),
            ("INFLOW", "modifier.flow_settings.flow_behavior = 'INFLOW'"),
            ("OUTFLOW", "modifier.flow_settings.flow_behavior = 'OUTFLOW'"),
        ):
            result = add_mod.add_fluid_modifier(object_name=obj.name, fluid_type=legacy, name=f"E2E {legacy}")
            assert result["success"] is False, legacy
            assert needle in result["error"], result["error"]

        assert len(obj.modifiers) == 0, "a rejected fluid type must not create a modifier"

    def test_flow_settings_properties_advertised_by_the_error_exist(self):
        """Pin the property paths the alias errors tell callers to set."""
        obj = self._cube()
        add_mod = load_skill("blender-physics", "add_fluid_modifier")

        flow = add_mod.add_fluid_modifier(object_name=obj.name, fluid_type="FLOW", name="E2E Flow")
        assert flow["success"] is True, flow.get("error")
        flow_settings = obj.modifiers["E2E Flow"].flow_settings
        assert flow_settings is not None
        # Advertised as modifier.flow_settings.flow_behavior / .flow_type.
        assert hasattr(flow_settings, "flow_behavior")
        assert hasattr(flow_settings, "flow_type")

        effector = add_mod.add_fluid_modifier(object_name=obj.name, fluid_type="EFFECTOR", name="E2E Effector")
        assert effector["success"] is True, effector.get("error")
        effector_settings = obj.modifiers["E2E Effector"].effector_settings
        assert effector_settings is not None
        # Advertised as modifier.effector_settings.effector_type.
        assert hasattr(effector_settings, "effector_type")

    def test_dynamic_paint_canvas_and_surface(self):
        obj = self._cube("E2E Paint Canvas")

        add_mod = load_skill("blender-physics", "add_dynamic_paint_modifier")
        result = add_mod.add_dynamic_paint_modifier(object_name=obj.name, paint_type="CANVAS", name="E2E Canvas")
        assert result["success"] is True, result.get("error")

        modifier = obj.modifiers["E2E Canvas"]
        assert modifier.type == "DYNAMIC_PAINT"
        assert modifier.ui_type == "CANVAS"

        surface_mod = load_skill("blender-physics", "add_dynamic_paint_surface")
        surface_result = surface_mod.add_dynamic_paint_surface(
            object_name=obj.name,
            modifier_name="E2E Canvas",
            surface_type="PAINT",
            name="E2E Surface",
        )
        if not surface_result["success"]:
            # canvas_surfaces.new() is not exposed by every build; the tool has
            # to say so explicitly rather than failing with a traceback.
            assert "canvas_surfaces.new()" in surface_result["error"]
            assert "surface_slot_add" in surface_result["error"]
            return

        assert surface_result["context"]["surface"]["surface_type"] == "PAINT"

        list_mod = load_skill("blender-physics", "list_dynamic_paint_surfaces")
        list_result = list_mod.list_dynamic_paint_surfaces(object_name=obj.name)
        assert list_result["success"] is True
        assert list_result["context"]["count"] >= 1


class TestParticleAuthoringE2E:
    def setup_method(self):
        _new_scene()

    def _cube_with_particles(self, name="E2E Particles"):
        bpy.ops.mesh.primitive_cube_add()
        obj = bpy.context.active_object
        obj.name = name
        add_mod = load_skill("blender-physics", "add_particle_system")
        result = add_mod.add_particle_system(object_name=name, name="E2E System")
        assert result["success"] is True, result.get("error")
        return obj

    def test_hair_mode_children_and_instance(self):
        obj = self._cube_with_particles()
        psettings = obj.modifiers["E2E System"].particle_system.settings

        hair_mod = load_skill("blender-physics", "set_particle_hair")
        hair_result = hair_mod.set_particle_hair(
            object_name=obj.name,
            system_name="E2E System",
            enabled=True,
            settings={"hair_length": 2.5},
        )
        assert hair_result["success"] is True, hair_result.get("error")
        assert psettings.type == "HAIR"
        assert psettings.hair_length == pytest.approx(2.5)
        assert hair_result["context"]["skipped"] == []

        children_mod = load_skill("blender-physics", "set_particle_children")
        children_result = children_mod.set_particle_children(
            object_name=obj.name,
            system_name="E2E System",
            child_type="INTERPOLATED",
            child_nbr=12,
        )
        assert children_result["success"] is True, children_result.get("error")
        assert psettings.child_type == "INTERPOLATED"
        assert psettings.child_nbr == 12
        assert children_result["context"]["skipped"] == []

        bpy.ops.mesh.primitive_plane_add(size=0.2)
        instance = bpy.context.active_object
        instance.name = "E2E Instance"

        instance_mod = load_skill("blender-physics", "set_particle_instance")
        instance_result = instance_mod.set_particle_instance(
            object_name=obj.name,
            system_name="E2E System",
            instance_object_name="E2E Instance",
            show_emitter=False,
        )
        assert instance_result["success"] is True, instance_result.get("error")
        assert psettings.instance_object is instance
        assert instance_result["context"]["skipped"] == []

    def test_emitter_mode_round_trip(self):
        obj = self._cube_with_particles()
        psettings = obj.modifiers["E2E System"].particle_system.settings

        hair_mod = load_skill("blender-physics", "set_particle_hair")
        first = hair_mod.set_particle_hair(object_name=obj.name, system_name="E2E System", enabled=True)
        assert first["success"] is True, first.get("error")
        assert psettings.type == "HAIR"

        result = hair_mod.set_particle_hair(object_name=obj.name, system_name="E2E System", enabled=False)
        assert result["success"] is True
        assert psettings.type == "EMITTER"

    def test_bake_particle_system_with_a_short_range(self):
        obj = self._cube_with_particles()

        bake_mod = load_skill("blender-physics", "bake_particle_system")
        result = bake_mod.bake_particle_system(
            object_name=obj.name,
            system_name="E2E System",
            frame_start=1,
            frame_end=2,
        )
        assert result["success"] is True, result.get("error")
        assert result["context"]["operator_result"] == ["FINISHED"]
        assert result["context"]["cache"]["frame_end"] == 2
