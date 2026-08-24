"""E2E tests for expanded Blender scene/object and mesh operation skills.

Requires a real Blender Python interpreter.
"""

from __future__ import annotations

import pytest

bpy = pytest.importorskip("bpy", reason="bpy not available - run inside Blender Python interpreter")

pytestmark = pytest.mark.e2e

from tests.e2e.conftest import load_skill  # noqa: E402


def _new_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


class TestMeshSceneOpsE2E:
    def setup_method(self):
        _new_scene()

    def test_scene_selection_visibility_bounds_and_mesh_mutation(self):
        bpy.ops.mesh.primitive_cube_add()
        cube_name = bpy.context.active_object.name

        rename_mod = load_skill("blender-objects", "rename_object")
        renamed = rename_mod.rename_object(object_name=cube_name, new_name="AgentCube")
        assert renamed["success"] is True

        selection_mod = load_skill("blender-objects", "set_selection")
        selection = selection_mod.set_selection(object_names=["AgentCube"])
        assert selection["success"] is True
        assert selection["context"]["selected"] == ["AgentCube"]

        bounds_mod = load_skill("blender-objects", "get_bounding_box")
        bounds = bounds_mod.get_bounding_box(object_name="AgentCube", world_space=True)
        assert bounds["success"] is True
        assert bounds["context"]["size"] == [2.0, 2.0, 2.0]

        visibility_mod = load_skill("blender-objects", "set_visibility")
        visibility = visibility_mod.set_visibility(object_name="AgentCube", visible=False, viewport=False, render=True)
        assert visibility["success"] is True
        assert bpy.data.objects["AgentCube"].hide_render is True

        count_mod = load_skill("blender-mesh-ops", "get_poly_count")
        before = count_mod.get_poly_count(object_name="AgentCube")
        assert before["success"] is True
        assert before["context"]["face_count"] == 6

        triangulate_mod = load_skill("blender-mesh-ops", "triangulate_mesh")
        triangulated = triangulate_mod.triangulate_mesh(object_name="AgentCube")
        assert triangulated["success"] is True

        after = count_mod.get_poly_count(object_name="AgentCube")
        assert after["success"] is True
        assert after["context"]["face_count"] == 12
        assert after["context"]["triangle_count"] == 12

    def test_shared_modeling_verbs_mutate_and_read_back_real_blender_state(self):
        create_mod = load_skill("blender-mesh-ops", "create_primitive")
        created = create_mod.create_primitive(
            primitive_type="cube",
            name="TypedBody",
            location=[0.0, 0.0, 0.0],
            rotation=[0.0, 0.0, 0.0],
            scale=[1.0, 1.0, 1.0],
            size=2.0,
        )
        assert created["success"] is True, created
        assert created["context"]["readback"]["verified"] is True

        extrude_mod = load_skill("blender-mesh-ops", "extrude_faces")
        extruded = extrude_mod.extrude_faces(
            object_name="TypedBody",
            face_indices=[0],
            distance=0.25,
            direction=[0.0, 0.0, 1.0],
        )
        assert extruded["success"] is True, extruded
        assert extruded["context"]["readback"]["verified"] is True

        bevel_mod = load_skill("blender-mesh-ops", "bevel_edges")
        beveled = bevel_mod.bevel_edges(
            object_name="TypedBody",
            edge_indices=[0],
            width=0.02,
            segments=2,
        )
        assert beveled["success"] is True, beveled

        array_mod = load_skill("blender-mesh-ops", "array_instances")
        arrayed = array_mod.array_instances(
            object_name="TypedBody",
            count=4,
            offset=[2.5, 0.0, 0.0],
            modifier_name="TypedArray",
        )
        assert arrayed["success"] is True, arrayed
        assert arrayed["context"]["readback"]["count"] == 4

        mirror_mod = load_skill("blender-mesh-ops", "mirror")
        mirrored = mirror_mod.mirror(
            object_name="TypedBody",
            axis="y",
            modifier_name="TypedMirror",
        )
        assert mirrored["success"] is True, mirrored
        assert mirrored["context"]["readback"]["use_axis"] == [False, True, False]

        material = bpy.data.materials.new("TypedPaint")
        assign_mod = load_skill("blender-mesh-ops", "modeling_assign_material")
        assigned = assign_mod.assign_material(
            object_name="TypedBody",
            material_name=material.name,
            slot_index=0,
        )
        assert assigned["success"] is True, assigned
        assert assigned["context"]["readback"]["verified"] is True

        uv_mod = load_skill("blender-mesh-ops", "auto_uv")
        unwrapped = uv_mod.auto_uv(object_name="TypedBody", margin=0.01)
        assert unwrapped["success"] is True, unwrapped
        assert unwrapped["context"]["readback"]["uv_map_count"] >= 1

        history_mod = load_skill("blender-mesh-ops", "delete_history")
        cleaned = history_mod.delete_history(object_name="TypedBody")
        assert cleaned["success"] is True, cleaned
        assert cleaned["context"]["readback"]["remaining_modifiers"] == []

    def test_applied_modifiers_boolean_and_uvs_prove_real_mesh_digest_changes(self):
        from dcc_mcp_blender._modeling_common import uv_state

        create_mod = load_skill("blender-mesh-ops", "create_primitive")
        body = create_mod.create_primitive(primitive_type="cube", name="DigestBody", size=2.0)
        cutter = create_mod.create_primitive(
            primitive_type="cube",
            name="DigestCutter",
            location=[0.75, 0.0, 0.0],
            scale=[0.5, 0.5, 0.5],
            size=2.0,
        )
        assert body["success"] is True, body
        assert cutter["success"] is True, cutter

        array_mod = load_skill("blender-mesh-ops", "array_instances")
        arrayed = array_mod.array_instances(
            object_name="DigestBody",
            count=3,
            offset=[3.0, 0.0, 0.0],
            modifier_name="AppliedArray",
            apply=True,
        )
        assert arrayed["success"] is True, arrayed
        assert arrayed["context"]["readback"]["applied"] is True
        assert (
            arrayed["context"]["readback"]["mesh_before"]["mesh_digest"]
            != arrayed["context"]["readback"]["mesh_after"]["mesh_digest"]
        )

        mirror_mod = load_skill("blender-mesh-ops", "mirror")
        mirrored = mirror_mod.mirror(
            object_name="DigestBody",
            axis="y",
            modifier_name="AppliedMirror",
            apply=True,
        )
        assert mirrored["success"] is True, mirrored
        assert mirrored["context"]["readback"]["applied"] is True
        assert (
            mirrored["context"]["readback"]["mesh_before"]["mesh_digest"]
            != mirrored["context"]["readback"]["mesh_after"]["mesh_digest"]
        )

        boolean_mod = load_skill("blender-mesh-ops", "boolean_op")
        booleaned = boolean_mod.boolean_op(
            input_a="DigestBody",
            input_b="DigestCutter",
            operation="subtract",
            apply=True,
        )
        assert booleaned["success"] is True, booleaned
        assert booleaned["context"]["readback"]["applied"] is True
        assert (
            booleaned["context"]["readback"]["mesh_before"]["mesh_digest"]
            != booleaned["context"]["readback"]["mesh_after"]["mesh_digest"]
        )

        object_state = bpy.data.objects["DigestBody"]
        uv_before = uv_state(object_state)
        uv_mod = load_skill("blender-mesh-ops", "auto_uv")
        unwrapped = uv_mod.auto_uv(object_name="DigestBody", margin=0.01)
        assert unwrapped["success"] is True, unwrapped
        uv_after = uv_state(object_state)
        assert uv_after["uv_coordinate_count"] > 0
        assert uv_after["uv_digest"] != uv_before["uv_digest"]
        assert uv_after["uv_digest"] == unwrapped["context"]["readback"]["uv_digest"]

    def test_loft_and_lathe_generate_real_mesh_topology_without_consuming_sources(self):
        bpy.ops.mesh.primitive_circle_add(vertices=8, radius=1.0, fill_type="NOTHING", location=(0.0, 0.0, 0.0))
        bpy.context.active_object.name = "SectionA"
        bpy.ops.mesh.primitive_circle_add(vertices=8, radius=0.5, fill_type="NOTHING", location=(0.0, 0.0, 2.0))
        bpy.context.active_object.name = "SectionB"

        loft_mod = load_skill("blender-mesh-ops", "loft_sections")
        lofted = loft_mod.loft_sections(
            sections=["SectionA", "SectionB"],
            output_name="TypedLoft",
        )
        assert lofted["success"] is True, lofted
        assert lofted["context"]["readback"]["face_count"] > 0
        assert bpy.data.objects.get("SectionA") is not None
        assert bpy.data.objects.get("SectionB") is not None

        profile_mesh = bpy.data.meshes.new("LatheProfileMesh")
        profile_mesh.from_pydata(
            [(0.5, 0.0, -1.0), (1.0, 0.0, 0.0), (0.5, 0.0, 1.0)],
            [(0, 1), (1, 2)],
            [],
        )
        profile = bpy.data.objects.new("LatheProfile", profile_mesh)
        bpy.context.collection.objects.link(profile)

        lathe_mod = load_skill("blender-mesh-ops", "lathe_profile")
        lathed = lathe_mod.lathe_profile(
            profile="LatheProfile",
            axis="z",
            origin=[0.0, 0.0, 0.0],
            segments=32,
            output_name="TypedLathe",
        )
        assert lathed["success"] is True, lathed
        assert lathed["context"]["readback"]["face_count"] > 0
        assert bpy.data.objects.get("LatheProfile") is profile
