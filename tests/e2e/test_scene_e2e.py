"""E2E tests for blender-scene and blender-objects skills.

Requires a real Blender Python interpreter.  Skipped automatically when bpy
is not importable so the file is safe to collect in normal test runs.

Run::

    blender --background --python -m pytest tests/e2e/test_scene_e2e.py -- -v

Or inside blender's bundled Python::

    /path/to/blender/python/bin/python -m pytest tests/e2e/test_scene_e2e.py -v
"""

from __future__ import annotations

import pytest

bpy = pytest.importorskip("bpy", reason="bpy not available — run inside Blender Python interpreter")

pytestmark = pytest.mark.e2e

from tests.e2e.conftest import load_skill  # noqa: E402


def _new_scene():
    """Reset to an empty scene before each test."""
    bpy.ops.wm.read_factory_settings(use_empty=True)


# ── blender-scene ─────────────────────────────────────────────────────────────


class TestSceneSkillsE2E:
    def setup_method(self):
        _new_scene()

    def test_get_session_info(self):
        mod = load_skill("blender-scene", "get_session_info")
        result = mod.get_session_info()
        assert result["success"] is True
        ctx = result["context"]
        assert "blender_version" in ctx
        assert len(ctx["blender_version"].split(".")) >= 2

    def test_list_objects_empty_scene(self):
        mod = load_skill("blender-scene", "list_objects")
        result = mod.list_objects()
        assert result["success"] is True
        assert result["context"]["count"] == 0

    def test_list_objects_after_add(self):
        bpy.ops.mesh.primitive_cube_add()
        mod = load_skill("blender-scene", "list_objects")
        result = mod.list_objects()
        assert result["success"] is True
        assert result["context"]["count"] >= 1

    def test_list_objects_type_filter(self):
        bpy.ops.mesh.primitive_cube_add()
        bpy.ops.object.light_add(type="POINT")
        mod = load_skill("blender-scene", "list_objects")
        result = mod.list_objects(object_type="LIGHT")
        assert result["success"] is True
        for obj in result["context"]["objects"]:
            assert obj["type"] == "LIGHT"

    def test_new_scene_clears_objects(self):
        # Add something first
        bpy.ops.mesh.primitive_cube_add()
        # Create new scene
        mod = load_skill("blender-scene", "new_scene")
        result = mod.new_scene()
        assert result["success"] is True
        # Scene should be empty
        assert len(bpy.data.objects) == 0

    def test_new_scene_preserves_dispatcher(self):
        """Regression: new_scene must not wipe the MCP main-thread dispatcher.

        After ``read_factory_settings(use_empty=True)`` the dispatcher timer
        is re-registered so subsequent main-thread tool calls succeed without
        restarting Blender.  Failure mode: second call hangs or times out.
        """
        # Prime: create an object so we have something to query.
        bpy.ops.mesh.primitive_cube_add()

        # Step 1 — new_scene (this internally calls read_factory_settings +
        # the dispatcher preservation logic).
        mod_scene = load_skill("blender-scene", "new_scene")
        result = mod_scene.new_scene()
        assert result["success"] is True

        # Step 2 — immediate main-thread tool call (must NOT hang).
        mod_list = load_skill("blender-scene", "list_objects")
        result2 = mod_list.list_objects()
        assert result2["success"] is True
        # Factory-reset scene has zero objects.
        assert result2["context"]["count"] == 0

        # Step 3 — verify the dispatcher timer is actually installed.
        try:
            from dcc_mcp_blender.server import get_server

            server = get_server()
            if server is not None:
                dispatcher = getattr(server, "_blender_dispatcher", None)
                if dispatcher is not None:
                    pump = getattr(dispatcher, "pump", None)
                    if pump is not None and hasattr(pump, "verify_installed"):
                        assert pump.verify_installed(), (
                            "Dispatcher timer is not registered with bpy.app.timers after new_scene"
                        )
        except ImportError:
            pass  # server module not importable in --background without addon

    def test_get_scene_info_structure(self):
        bpy.ops.mesh.primitive_cube_add()
        mod = load_skill("blender-scene", "get_scene_info")
        result = mod.get_scene_info()
        assert result["success"] is True
        ctx = result["context"]
        assert "scene_name" in ctx
        assert "total_objects" in ctx
        assert "objects_by_type" in ctx
        assert "collections" in ctx

    def test_save_scene_to_temp(self, tmp_path):
        bpy.ops.mesh.primitive_cube_add()
        blend_path = str(tmp_path / "e2e_test.blend")
        mod = load_skill("blender-scene", "save_scene")
        result = mod.save_scene(filepath=blend_path)
        assert result["success"] is True
        assert (tmp_path / "e2e_test.blend").exists()


# ── blender-objects ───────────────────────────────────────────────────────────


class TestObjectSkillsE2E:
    def setup_method(self):
        _new_scene()

    def test_create_cube(self):
        mod = load_skill("blender-objects", "create_object")
        result = mod.create_object(object_type="cube", name="E2ECube")
        assert result["success"] is True
        assert "E2ECube" in bpy.data.objects

    def test_create_sphere(self):
        mod = load_skill("blender-objects", "create_object")
        result = mod.create_object(object_type="sphere", name="E2ESphere")
        assert result["success"] is True
        assert "E2ESphere" in bpy.data.objects

    def test_create_cylinder(self):
        mod = load_skill("blender-objects", "create_object")
        result = mod.create_object(object_type="cylinder", name="E2ECylinder")
        assert result["success"] is True
        assert "E2ECylinder" in bpy.data.objects

    def test_create_plane(self):
        mod = load_skill("blender-objects", "create_object")
        result = mod.create_object(object_type="plane", name="E2EPlane")
        assert result["success"] is True
        assert "E2EPlane" in bpy.data.objects

    def test_delete_object(self):
        bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))
        cube_name = bpy.context.active_object.name
        mod = load_skill("blender-objects", "delete_object")
        result = mod.delete_object(name=cube_name)
        assert result["success"] is True
        assert cube_name not in bpy.data.objects

    def test_move_object(self):
        bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))
        cube_name = bpy.context.active_object.name
        mod = load_skill("blender-objects", "move_object")
        result = mod.move_object(name=cube_name, location=[3.0, 4.0, 5.0])
        assert result["success"] is True
        loc = bpy.data.objects[cube_name].location
        assert abs(loc.x - 3.0) < 1e-4
        assert abs(loc.y - 4.0) < 1e-4
        assert abs(loc.z - 5.0) < 1e-4

    def test_rotate_object(self):
        import math

        bpy.ops.mesh.primitive_cube_add()
        cube_name = bpy.context.active_object.name
        mod = load_skill("blender-objects", "rotate_object")
        result = mod.rotate_object(name=cube_name, rotation=[90.0, 0.0, 0.0])
        assert result["success"] is True
        rot = bpy.data.objects[cube_name].rotation_euler
        assert abs(rot.x - math.radians(90)) < 1e-4

    def test_scale_object_uniform(self):
        bpy.ops.mesh.primitive_cube_add()
        cube_name = bpy.context.active_object.name
        mod = load_skill("blender-objects", "scale_object")
        result = mod.scale_object(name=cube_name, scale=2.0)
        assert result["success"] is True
        scale = bpy.data.objects[cube_name].scale
        assert abs(scale.x - 2.0) < 1e-4
        assert abs(scale.y - 2.0) < 1e-4

    def test_duplicate_object(self):
        bpy.ops.mesh.primitive_cube_add()
        cube_name = bpy.context.active_object.name
        mod = load_skill("blender-objects", "duplicate_object")
        result = mod.duplicate_object(name=cube_name, new_name="DuplicateCube")
        assert result["success"] is True
        assert "DuplicateCube" in bpy.data.objects

    def test_get_object_info(self):
        bpy.ops.mesh.primitive_cube_add()
        cube_name = bpy.context.active_object.name
        mod = load_skill("blender-objects", "get_object_info")
        result = mod.get_object_info(name=cube_name)
        assert result["success"] is True
        ctx = result["context"]
        assert ctx["type"] == "MESH"
        assert ctx["vertex_count"] == 8  # default cube
