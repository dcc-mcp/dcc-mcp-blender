"""Unit tests for blender-physics skill scripts (bpy mocked)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from tests.conftest import load_and_call, make_mock_bpy


def _make_obj(name="Cube"):
    obj = MagicMock()
    obj.name = name
    obj.type = "MESH"
    obj.rigid_body = None
    obj.modifiers = _ModifierCollection()
    return obj


class _ObjectCollection(list):
    def get(self, name):
        for obj in self:
            if getattr(obj, "name", None) == name:
                return obj
        return None


class _ModifierCollection(list):
    def get(self, name):
        for modifier in self:
            if modifier.name == name:
                return modifier
        return None

    def new(self, name, type):
        cache = SimpleNamespace(frame_start=1, frame_end=250, is_baked=False, use_disk_cache=False)
        if type == "CLOTH":
            settings = SimpleNamespace(
                quality=5,
                mass=0.3,
                tension_stiffness=5.0,
                use_pressure=False,
                point_cache=cache,
            )
        elif type == "COLLISION":
            settings = SimpleNamespace(
                thickness_outer=0.02,
                friction=5.0,
                use_culling=False,
            )
        else:
            settings = SimpleNamespace(point_cache=cache)
        modifier = SimpleNamespace(
            name=name, type=type, settings=settings, point_cache=getattr(settings, "point_cache", None)
        )
        self.append(modifier)
        return modifier


def _bpy_with_objects(*objects):
    bpy = make_mock_bpy()
    bpy.data.objects = _ObjectCollection(objects)
    return bpy


class TestAddRigidBody:
    def test_adds_rigid_body_and_applies_properties(self):
        bpy = make_mock_bpy()
        obj = _make_obj()
        rigid_body = MagicMock()
        rigid_body.type = "ACTIVE"
        rigid_body.mass = 1.0
        rigid_body.collision_shape = "CONVEX_HULL"
        bpy.data.objects.get.return_value = obj

        def _add_body(type="ACTIVE"):
            obj.rigid_body = rigid_body
            rigid_body.type = type

        bpy.ops.rigidbody.object_add.side_effect = _add_body

        result = load_and_call(
            "blender-physics/scripts/add_rigid_body.py",
            bpy,
            object_name="Cube",
            body_type="PASSIVE",
            mass="2.5",
            collision_shape="BOX",
        )

        assert result["success"] is True
        bpy.ops.rigidbody.object_add.assert_called_once_with(type="PASSIVE")
        assert rigid_body.mass == 2.5
        assert rigid_body.collision_shape == "BOX"

    def test_invalid_body_type_returns_error(self):
        bpy = make_mock_bpy()
        bpy.data.objects.get.return_value = _make_obj()

        result = load_and_call(
            "blender-physics/scripts/add_rigid_body.py",
            bpy,
            object_name="Cube",
            body_type="FLYING",
        )

        assert result["success"] is False


class TestSetRigidBodyProperties:
    def test_updates_existing_rigid_body(self):
        bpy = make_mock_bpy()
        obj = _make_obj()
        obj.rigid_body = MagicMock()
        obj.rigid_body.mass = 1.0
        obj.rigid_body.friction = 0.5
        bpy.data.objects.get.return_value = obj

        result = load_and_call(
            "blender-physics/scripts/set_rigid_body_properties.py",
            bpy,
            object_name="Cube",
            mass="3.0",
            friction="0.2",
        )

        assert result["success"] is True
        assert obj.rigid_body.mass == 3.0
        assert obj.rigid_body.friction == 0.2
        assert result["context"]["applied"]["mass"] == 3.0

    def test_missing_rigid_body_returns_error(self):
        bpy = make_mock_bpy()
        bpy.data.objects.get.return_value = _make_obj()

        result = load_and_call(
            "blender-physics/scripts/set_rigid_body_properties.py",
            bpy,
            object_name="Cube",
            mass=3.0,
        )

        assert result["success"] is False


class TestRemoveRigidBody:
    def test_removes_existing_rigid_body(self):
        bpy = make_mock_bpy()
        obj = _make_obj()
        obj.rigid_body = MagicMock()
        bpy.data.objects.get.return_value = obj

        result = load_and_call(
            "blender-physics/scripts/remove_rigid_body.py",
            bpy,
            object_name="Cube",
        )

        assert result["success"] is True
        bpy.ops.rigidbody.object_remove.assert_called_once_with()

    def test_missing_rigid_body_returns_error(self):
        bpy = make_mock_bpy()
        bpy.data.objects.get.return_value = _make_obj()

        result = load_and_call(
            "blender-physics/scripts/remove_rigid_body.py",
            bpy,
            object_name="Cube",
        )

        assert result["success"] is False


class TestRigidBodyWorldAndListing:
    def test_lists_rigid_bodies(self):
        cube = _make_obj()
        cube.rigid_body = SimpleNamespace(
            type="ACTIVE",
            mass=2.0,
            collision_shape="BOX",
            friction=0.4,
            restitution=0.1,
        )
        bpy = _bpy_with_objects(cube)

        result = load_and_call("blender-physics/scripts/list_rigid_bodies.py", bpy)

        assert result["success"] is True
        assert result["context"]["count"] == 1
        assert result["context"]["rigid_bodies"][0]["object_name"] == "Cube"

    def test_sets_rigid_body_world_settings_and_cache_frames(self):
        bpy = make_mock_bpy()
        cache = SimpleNamespace(frame_start=1, frame_end=250, is_baked=False, use_disk_cache=False)
        world = SimpleNamespace(time_scale=1.0, substeps_per_frame=10, solver_iterations=10, point_cache=cache)
        bpy.context.scene.rigidbody_world = world

        result = load_and_call(
            "blender-physics/scripts/set_rigid_body_world_settings.py",
            bpy,
            frame_start="3",
            frame_end="24",
            time_scale="0.5",
            substeps_per_frame="6",
            settings={"solver_iterations": "14", "unknown": "skip"},
        )

        assert result["success"] is True
        assert world.time_scale == 0.5
        assert world.substeps_per_frame == 6
        assert world.solver_iterations == 14
        assert cache.frame_start == 3
        assert cache.frame_end == 24
        assert result["context"]["skipped"] == ["unknown"]

    def test_bake_rigid_body_simulation_supports_dry_run(self):
        bpy = make_mock_bpy()
        cache = SimpleNamespace(frame_start=1, frame_end=250, is_baked=False, use_disk_cache=False)
        bpy.context.scene.rigidbody_world = SimpleNamespace(point_cache=cache)

        result = load_and_call(
            "blender-physics/scripts/bake_rigid_body_simulation.py",
            bpy,
            frame_start=1,
            frame_end=12,
            dry_run=True,
        )

        assert result["success"] is True
        assert result["context"]["dry_run"] is True
        bpy.ops.ptcache.bake_all.assert_not_called()

    def test_clear_rigid_body_bake_calls_point_cache_free(self):
        bpy = make_mock_bpy()
        bpy.ops.ptcache = MagicMock()
        bpy.context.scene.rigidbody_world = SimpleNamespace(
            point_cache=SimpleNamespace(frame_start=1, frame_end=250, is_baked=True, use_disk_cache=False)
        )

        result = load_and_call("blender-physics/scripts/clear_rigid_body_bake.py", bpy)

        assert result["success"] is True
        bpy.ops.ptcache.free_bake_all.assert_called_once_with()


class TestSimulationModifiers:
    def test_adds_cloth_modifier_and_coerces_settings(self):
        cube = _make_obj()
        bpy = _bpy_with_objects(cube)

        result = load_and_call(
            "blender-physics/scripts/add_cloth_modifier.py",
            bpy,
            object_name="Cube",
            name="Hero Cloth",
            settings={"quality": "3", "mass": "0.25", "use_pressure": "true"},
        )

        assert result["success"] is True
        modifier = cube.modifiers.get("Hero Cloth")
        assert modifier is not None
        assert modifier.settings.quality == 3
        assert modifier.settings.mass == 0.25
        assert modifier.settings.use_pressure is True

    def test_set_cloth_settings_requires_matching_modifier(self):
        cube = _make_obj()
        bpy = _bpy_with_objects(cube)

        result = load_and_call(
            "blender-physics/scripts/set_cloth_settings.py",
            bpy,
            object_name="Cube",
            modifier_name="Missing Cloth",
            settings={"mass": 0.5},
        )

        assert result["success"] is False
        assert "not found" in result["message"].lower()

    def test_adds_and_updates_collision_modifier_settings(self):
        cube = _make_obj()
        bpy = _bpy_with_objects(cube)

        add_result = load_and_call(
            "blender-physics/scripts/add_collision_modifier.py",
            bpy,
            object_name="Cube",
            settings={"thickness_outer": "0.08"},
        )
        update_result = load_and_call(
            "blender-physics/scripts/set_collision_settings.py",
            bpy,
            object_name="Cube",
            settings={"friction": "2.5", "use_culling": "true"},
        )

        modifier = cube.modifiers.get("Collision")
        assert add_result["success"] is True
        assert update_result["success"] is True
        assert modifier.settings.thickness_outer == 0.08
        assert modifier.settings.friction == 2.5
        assert modifier.settings.use_culling is True

    def test_lists_simulation_modifiers(self):
        cube = _make_obj()
        cube.modifiers.new("Hero Cloth", "CLOTH")
        cube.modifiers.new("Hero Collision", "COLLISION")
        bpy = _bpy_with_objects(cube)

        result = load_and_call("blender-physics/scripts/list_simulation_modifiers.py", bpy, object_name="Cube")

        assert result["success"] is True
        assert result["context"]["count"] == 2
        assert {item["type"] for item in result["context"]["modifiers"]} == {"CLOTH", "COLLISION"}

    def test_bake_simulation_dry_run_reports_targets_without_baking(self):
        cube = _make_obj()
        cube.modifiers.new("Hero Cloth", "CLOTH")
        bpy = _bpy_with_objects(cube)
        bpy.ops.ptcache = MagicMock()

        result = load_and_call(
            "blender-physics/scripts/bake_simulation.py",
            bpy,
            object_name="Cube",
            modifier_name="Hero Cloth",
            frame_start=5,
            frame_end=10,
            dry_run=True,
        )

        assert result["success"] is True
        assert result["context"]["dry_run"] is True
        assert result["context"]["count"] == 1
        bpy.ops.ptcache.bake_all.assert_not_called()

    def test_clear_simulation_cache_dry_run_reports_targets_without_clearing(self):
        cube = _make_obj()
        cube.modifiers.new("Hero Cloth", "CLOTH")
        bpy = _bpy_with_objects(cube)
        bpy.ops.ptcache = MagicMock()

        result = load_and_call(
            "blender-physics/scripts/clear_simulation_cache.py",
            bpy,
            object_name="Cube",
            modifier_name="Hero Cloth",
            dry_run=True,
        )

        assert result["success"] is True
        assert result["context"]["dry_run"] is True
        bpy.ops.ptcache.free_bake_all.assert_not_called()

    def test_get_simulation_status_reports_world_and_modifiers(self):
        cube = _make_obj()
        cube.modifiers.new("Hero Cloth", "CLOTH")
        bpy = _bpy_with_objects(cube)
        bpy.context.scene.rigidbody_world = SimpleNamespace(
            point_cache=SimpleNamespace(frame_start=1, frame_end=24, is_baked=False, use_disk_cache=False)
        )

        result = load_and_call("blender-physics/scripts/get_simulation_status.py", bpy)

        assert result["success"] is True
        assert result["context"]["rigid_body_world"]["exists"] is True
        assert result["context"]["modifier_count"] == 1

    def test_add_simulation_modifier_requires_mesh_object(self):
        lamp = _make_obj("Lamp")
        lamp.type = "LIGHT"
        bpy = _bpy_with_objects(lamp)

        result = load_and_call("blender-physics/scripts/add_cloth_modifier.py", bpy, object_name="Lamp")

        assert result["success"] is False
        assert "not a mesh" in result["message"].lower()


class TestSoftBody:
    def test_adds_soft_body_modifier(self):
        cube = _make_obj()
        bpy = _bpy_with_objects(cube)

        result = load_and_call(
            "blender-physics/scripts/add_soft_body_modifier.py",
            bpy,
            object_name="Cube",
            name="MySoftBody",
        )

        assert result["success"] is True
        modifier = cube.modifiers.get("MySoftBody")
        assert modifier is not None
        assert modifier.type == "SOFT_BODY"

    def test_set_soft_body_settings_returns_error_when_no_modifier(self):
        cube = _make_obj()
        bpy = _bpy_with_objects(cube)

        result = load_and_call(
            "blender-physics/scripts/set_soft_body_settings.py",
            bpy,
            object_name="Cube",
            modifier_name="Missing",
            settings={"mass": 1.5},
        )

        assert result["success"] is False
        assert "not found" in result["message"].lower()


class TestRigidBodyConstraints:
    def test_adds_rigid_body_constraint(self):
        bpy = make_mock_bpy()
        obj = _make_obj()
        obj.rigid_body_constraint = None
        bpy.data.objects.get.return_value = obj

        rbc = SimpleNamespace(type="FIXED", enabled=True, disable_collisions=False, object1=None, object2=None)

        def _add_constraint(type="FIXED"):
            obj.rigid_body_constraint = rbc
            rbc.type = type

        bpy.ops.rigidbody.constraint_add.side_effect = _add_constraint

        result = load_and_call(
            "blender-physics/scripts/add_rigid_body_constraint.py",
            bpy,
            object_name="Cube",
            constraint_type="HINGE",
        )

        assert result["success"] is True
        bpy.ops.rigidbody.constraint_add.assert_called_once_with(type="HINGE")

    def test_invalid_constraint_type_returns_error(self):
        bpy = make_mock_bpy()
        obj = _make_obj()
        obj.rigid_body_constraint = None
        bpy.data.objects.get.return_value = obj

        result = load_and_call(
            "blender-physics/scripts/add_rigid_body_constraint.py",
            bpy,
            object_name="Cube",
            constraint_type="INVALID_TYPE",
        )

        assert result["success"] is False

    def test_lists_rigid_body_constraints(self):
        cube = _make_obj()
        cube.rigid_body_constraint = SimpleNamespace(
            type="FIXED", enabled=True, disable_collisions=False, object1=None, object2=None
        )
        bpy = _bpy_with_objects(cube)

        result = load_and_call("blender-physics/scripts/list_rigid_body_constraints.py", bpy)

        assert result["success"] is True
        assert result["context"]["count"] == 1
        assert result["context"]["constraints"][0]["constraint_type"] == "FIXED"

    def test_remove_rigid_body_constraint_when_none_returns_error(self):
        cube = _make_obj()
        cube.rigid_body_constraint = None
        bpy = _bpy_with_objects(cube)

        result = load_and_call(
            "blender-physics/scripts/remove_rigid_body_constraint.py",
            bpy,
            object_name="Cube",
        )

        assert result["success"] is False


class TestForceFields:
    def test_adds_force_field(self):
        bpy = make_mock_bpy()
        obj = _make_obj()
        field = SimpleNamespace(type="FORCE", strength=1.0, falloff_power=2.0)
        obj.field = field
        bpy.data.objects.get.return_value = obj

        result = load_and_call(
            "blender-physics/scripts/add_force_field.py",
            bpy,
            object_name="Cube",
            field_type="WIND",
            strength=5.0,
        )

        assert result["success"] is True
        assert field.type == "WIND"
        assert field.strength == 5.0

    def test_invalid_field_type_returns_error(self):
        bpy = make_mock_bpy()
        bpy.data.objects.get.return_value = _make_obj()

        result = load_and_call(
            "blender-physics/scripts/add_force_field.py",
            bpy,
            object_name="Cube",
            field_type="INVALID_FIELD",
        )

        assert result["success"] is False

    def test_lists_force_fields(self):
        cube = _make_obj()
        cube.field = SimpleNamespace(type="VORTEX", strength=2.0, falloff_power=1.0)
        bpy = _bpy_with_objects(cube)

        result = load_and_call("blender-physics/scripts/list_force_fields.py", bpy)

        assert result["success"] is True
        assert result["context"]["count"] == 1
        assert result["context"]["force_fields"][0]["field_type"] == "VORTEX"

    def test_remove_force_field_when_none_returns_error(self):
        bpy = make_mock_bpy()
        obj = _make_obj()
        obj.field = SimpleNamespace(type="NONE", strength=0.0, falloff_power=2.0)
        bpy.data.objects.get.return_value = obj

        result = load_and_call(
            "blender-physics/scripts/remove_force_field.py",
            bpy,
            object_name="Cube",
        )

        assert result["success"] is False


class TestParticleSystems:
    def test_adds_particle_system(self):
        cube = _make_obj()
        bpy = _bpy_with_objects(cube)

        result = load_and_call(
            "blender-physics/scripts/add_particle_system.py",
            bpy,
            object_name="Cube",
            name="Sparks",
            count=500,
            frame_start=1,
            frame_end=120,
            lifetime=50,
        )

        assert result["success"] is True
        modifier = cube.modifiers.get("Sparks")
        assert modifier is not None
        assert modifier.type == "PARTICLE_SYSTEM"

    def test_add_particle_system_requires_mesh(self):
        lamp = _make_obj("Lamp")
        lamp.type = "LIGHT"
        bpy = _bpy_with_objects(lamp)

        result = load_and_call(
            "blender-physics/scripts/add_particle_system.py",
            bpy,
            object_name="Lamp",
        )

        assert result["success"] is False
        assert "not a mesh" in result["message"].lower()

    def test_set_particle_system_settings_no_modifier_returns_error(self):
        cube = _make_obj()
        bpy = _bpy_with_objects(cube)

        result = load_and_call(
            "blender-physics/scripts/set_particle_system_settings.py",
            bpy,
            object_name="Cube",
            modifier_name="NoParticle",
            settings={"count": 100},
        )

        assert result["success"] is False

    def test_lists_particle_systems(self):
        cube = _make_obj()
        # Manually add a PARTICLE_SYSTEM modifier to the collection
        cache = SimpleNamespace(frame_start=1, frame_end=250, is_baked=False, use_disk_cache=False)
        ps_settings = SimpleNamespace(
            count=1000,
            frame_start=1.0,
            frame_end=50.0,
            lifetime=30.0,
            physics_type="NEWTON",
        )
        ps = SimpleNamespace(name="Sparks", settings=ps_settings)
        modifier = SimpleNamespace(
            name="Sparks",
            type="PARTICLE_SYSTEM",
            particle_system=ps,
            settings=SimpleNamespace(point_cache=cache),
            point_cache=cache,
        )
        cube.modifiers.append(modifier)
        bpy = _bpy_with_objects(cube)

        result = load_and_call(
            "blender-physics/scripts/list_particle_systems.py",
            bpy,
            object_name="Cube",
        )

        assert result["success"] is True
        assert result["context"]["count"] == 1
        assert result["context"]["particle_systems"][0]["modifier_name"] == "Sparks"
