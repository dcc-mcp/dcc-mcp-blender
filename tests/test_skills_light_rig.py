"""Unit tests for blender-light-rig skill scripts."""

from __future__ import annotations

from types import SimpleNamespace

from tests.conftest import load_and_call, make_mock_bpy


class _Collection(list):
    def get(self, name):
        for item in self:
            if getattr(item, "name", None) == name:
                return item
        return None


class _LinkList(list):
    def link(self, item):
        if item not in self:
            self.append(item)


class _FakeCollection(dict):
    def __init__(self, name):
        super().__init__()
        self.name = name
        self.objects = _LinkList()
        self.children = _LinkList()

    def get(self, key, default=None):
        return dict.get(self, key, default)


class _CollectionCollection(_Collection):
    def new(self, name):
        collection = _FakeCollection(name)
        self.append(collection)
        return collection


class _FakeLightData:
    def __init__(self, name, light_type):
        self.name = name
        self.type = light_type
        self.energy = 0.0
        self.color = [1.0, 1.0, 1.0]
        self.size = 1.0
        self.shadow_soft_size = 1.0


class _LightCollection(_Collection):
    def new(self, name, type):  # noqa: A002
        light = _FakeLightData(name, type)
        self.append(light)
        return light


class _FakeObject(dict):
    def __init__(self, name, obj_type="MESH", data=None, location=None):
        super().__init__()
        self.name = name
        self.type = obj_type
        self.data = data
        self.location = location or [0.0, 0.0, 0.0]
        self.rotation_euler = [0.0, 0.0, 0.0]

    def get(self, key, default=None):
        return dict.get(self, key, default)


class _ObjectCollection(_Collection):
    def new(self, name, object_data=None):
        obj_type = "LIGHT" if object_data is not None else "EMPTY"
        obj = _FakeObject(name, obj_type, object_data)
        self.append(obj)
        return obj


class _FakeScene:
    def __init__(self):
        self.collection = _FakeCollection("Scene Collection")
        self.world = None
        self.view_settings = SimpleNamespace(view_transform="AgX", look="None", exposure=0.0, gamma=1.0)


def _make_bpy(*objects):
    bpy = make_mock_bpy()
    bpy.context.scene = _FakeScene()
    bpy.data.objects = _ObjectCollection(objects)
    bpy.data.lights = _LightCollection()
    bpy.data.collections = _CollectionCollection()
    return bpy


def _make_light(name="Light", energy=100.0):
    data = _FakeLightData(name, "POINT")
    data.energy = energy
    return _FakeObject(name, "LIGHT", data, [0.0, 0.0, 3.0])


class TestLightRig:
    def test_create_three_point_rig_and_scale_intensity(self):
        target = _FakeObject("Cube")
        bpy = _make_bpy(target)

        created = load_and_call(
            "blender-light-rig/scripts/create_three_point_light_rig.py",
            bpy,
            name="HeroRig",
            target_object="Cube",
        )
        listed = load_and_call("blender-light-rig/scripts/list_light_rigs.py", bpy)
        scaled = load_and_call(
            "blender-light-rig/scripts/set_light_rig_intensity.py",
            bpy,
            rig_name="HeroRig",
            multiplier=0.5,
        )

        assert created["success"] is True
        assert len(created["context"]["lights"]) == 3
        assert listed["context"]["count"] == 1
        assert scaled["success"] is True
        assert scaled["context"]["lights"][0]["energy"] == 400.0

    def test_create_three_point_rig_missing_target(self):
        bpy = _make_bpy()

        result = load_and_call(
            "blender-light-rig/scripts/create_three_point_light_rig.py",
            bpy,
            name="MissingTargetRig",
            target_object="Ghost",
        )

        assert result["success"] is False

    def test_create_area_softbox(self):
        bpy = _make_bpy()

        result = load_and_call(
            "blender-light-rig/scripts/create_area_softbox.py",
            bpy,
            name="Softbox",
            size=6.0,
            energy=750.0,
        )

        assert result["success"] is True
        assert result["context"]["light"]["light_type"] == "AREA"
        assert result["context"]["light"]["energy"] == 750.0

    def test_create_area_softbox_invalid_vector(self):
        bpy = _make_bpy()

        result = load_and_call(
            "blender-light-rig/scripts/create_area_softbox.py",
            bpy,
            name="BadSoftbox",
            location=[1.0, 2.0],
        )

        assert result["success"] is False

    def test_set_light_rig_intensity_missing_rig(self):
        bpy = _make_bpy()

        result = load_and_call(
            "blender-light-rig/scripts/set_light_rig_intensity.py",
            bpy,
            rig_name="GhostRig",
            multiplier=1.0,
        )

        assert result["success"] is False

    def test_group_lights_and_summary(self):
        key = _make_light("Key", 100.0)
        fill = _make_light("Fill", 50.0)
        bpy = _make_bpy(key, fill)

        grouped = load_and_call(
            "blender-light-rig/scripts/group_lights.py",
            bpy,
            light_names=["Key", "Fill"],
            collection_name="GroupedRig",
        )
        summary = load_and_call("blender-light-rig/scripts/get_lighting_summary.py", bpy)

        assert grouped["success"] is True
        assert len(grouped["context"]["lights"]) == 2
        assert summary["context"]["light_count"] == 2
        assert summary["context"]["rigs"][0]["rig_name"] == "GroupedRig"

    def test_group_lights_rejects_non_light(self):
        mesh = _FakeObject("Cube")
        bpy = _make_bpy(mesh)

        result = load_and_call(
            "blender-light-rig/scripts/group_lights.py",
            bpy,
            light_names=["Cube"],
            collection_name="BadRig",
        )

        assert result["success"] is False

    def test_aim_light_at_missing_target(self):
        light = _make_light("Key")
        bpy = _make_bpy(light)

        result = load_and_call(
            "blender-light-rig/scripts/aim_light_at_object.py",
            bpy,
            light_name="Key",
            target_object="Missing",
        )

        assert result["success"] is False

    def test_hdri_world_rejects_invalid_path(self):
        bpy = _make_bpy()

        result = load_and_call(
            "blender-light-rig/scripts/create_hdri_world.py",
            bpy,
            image_path="https://example.com/studio.exr",
        )

        assert result["success"] is False

    def test_set_render_view_transform(self):
        bpy = _make_bpy()

        result = load_and_call(
            "blender-light-rig/scripts/set_render_view_transform.py",
            bpy,
            view_transform="Standard",
            exposure=0.25,
        )

        assert result["success"] is True
        assert result["context"]["current"]["view_transform"] == "Standard"
        assert result["context"]["current"]["exposure"] == 0.25
