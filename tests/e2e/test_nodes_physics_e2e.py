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
