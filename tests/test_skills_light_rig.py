"""Unit tests for blender-light-rig skill scripts."""

from __future__ import annotations

import math
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
        self.frame_current = 1
        self.view_settings = SimpleNamespace(view_transform="AgX", look="None", exposure=0.0, gamma=1.0)
        self.display_settings = SimpleNamespace(display_device="sRGB")

    def frame_set(self, frame):
        self.frame_current = frame


class _FakeSocket:
    def __init__(self, node, name, default_value=None):
        self.node = node
        self.name = name
        self.default_value = default_value
        self.keyframes = []

    def keyframe_insert(self, data_path, index, frame):
        self.keyframes.append(
            {
                "data_path": data_path,
                "index": index,
                "frame": frame,
                "value": self.default_value[index],
            }
        )
        return True


class _FakeNode:
    def __init__(self, node_type):
        self.type = node_type
        self.name = node_type
        self.inputs = _Collection()
        self.outputs = _Collection()
        if node_type == "ShaderNodeBackground":
            self.inputs.extend(
                [
                    _FakeSocket(self, "Color", [0.0, 0.0, 0.0, 1.0]),
                    _FakeSocket(self, "Strength", 1.0),
                ]
            )
        elif node_type == "ShaderNodeTexEnvironment":
            self.inputs.append(_FakeSocket(self, "Vector", [0.0, 0.0, 0.0]))
            self.outputs.append(_FakeSocket(self, "Color", [0.0, 0.0, 0.0, 1.0]))
            self.image = None
        elif node_type == "ShaderNodeTexCoord":
            self.outputs.extend(
                [
                    _FakeSocket(self, "Generated", [0.0, 0.0, 0.0]),
                    _FakeSocket(self, "Normal", [0.0, 0.0, 1.0]),
                ]
            )
        elif node_type == "ShaderNodeMapping":
            self.inputs.extend(
                [
                    _FakeSocket(self, "Vector", [0.0, 0.0, 0.0]),
                    _FakeSocket(self, "Rotation", [0.0, 0.0, 0.0]),
                ]
            )
            self.outputs.append(_FakeSocket(self, "Vector", [0.0, 0.0, 0.0]))


class _FakeNodes(_Collection):
    def new(self, type):  # noqa: A002
        node = _FakeNode(type)
        self.append(node)
        return node


class _FakeLinks(list):
    def new(self, from_socket, to_socket):
        self.append(
            SimpleNamespace(
                from_node=from_socket.node,
                from_socket=from_socket,
                to_node=to_socket.node,
                to_socket=to_socket,
            )
        )


class _FakeWorld(dict):
    def __init__(self, name):
        super().__init__()
        self.name = name
        self.color = [0.0, 0.0, 0.0]
        self.use_nodes = False
        self.node_tree = SimpleNamespace(nodes=_FakeNodes(), links=_FakeLinks())

    def get(self, key, default=None):
        return dict.get(self, key, default)


class _WorldCollection(_Collection):
    def new(self, name):
        world = _FakeWorld(name)
        world.node_tree.nodes.append(_FakeNode("ShaderNodeBackground"))
        world.node_tree.nodes[-1].name = "Background"
        self.append(world)
        return world


class _ImageCollection:
    def load(self, path, check_existing=True):
        return SimpleNamespace(filepath=path)


def _make_bpy(*objects):
    bpy = make_mock_bpy()
    bpy.context.scene = _FakeScene()
    bpy.data.objects = _ObjectCollection(objects)
    bpy.data.lights = _LightCollection()
    bpy.data.collections = _CollectionCollection()
    bpy.data.worlds = _WorldCollection()
    bpy.data.images = _ImageCollection()
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

    def test_hdri_world_uses_world_normal_coordinates(self, tmp_path):
        image_path = tmp_path / "studio.hdr"
        image_path.write_bytes(b"test")
        bpy = _make_bpy()

        result = load_and_call(
            "blender-light-rig/scripts/create_hdri_world.py",
            bpy,
            image_path=str(image_path),
        )

        assert result["success"] is True
        world = bpy.context.scene.world
        mapping = world.node_tree.nodes.get("DCC MCP Mapping")
        coordinate_link = next(link for link in world.node_tree.links if link.to_node is mapping)
        assert coordinate_link.from_socket.name == "Normal"

    def test_animate_hdri_rotation_creates_lookdev_keyframes(self, tmp_path):
        image_path = tmp_path / "studio.hdr"
        image_path.write_bytes(b"test")
        bpy = _make_bpy()
        created = load_and_call(
            "blender-light-rig/scripts/create_hdri_world.py",
            bpy,
            image_path=str(image_path),
        )

        animated = load_and_call(
            "blender-light-rig/scripts/animate_hdri_rotation.py",
            bpy,
            frame_start=1,
            frame_end=61,
            start_rotation=0.0,
            end_rotation=360.0,
            interpolation="LINEAR",
        )

        assert created["success"] is True
        assert animated["success"] is True
        assert animated["context"]["keyframes"] == [
            {"frame": 1, "rotation": 0.0},
            {"frame": 61, "rotation": 360.0},
        ]
        assert animated["context"]["replace_existing"] is True
        mapping = bpy.context.scene.world.node_tree.nodes.get("DCC MCP Mapping")
        rotation_socket = mapping.inputs.get("Rotation")
        assert [keyframe["frame"] for keyframe in rotation_socket.keyframes] == [1, 61]
        assert [round(keyframe["value"], 6) for keyframe in rotation_socket.keyframes] == [
            0.0,
            round(math.tau, 6),
        ]

    def test_lighting_summary_reports_hdri_mapping_and_animation(self, tmp_path):
        image_path = tmp_path / "studio.hdr"
        image_path.write_bytes(b"test")
        bpy = _make_bpy()
        load_and_call(
            "blender-light-rig/scripts/create_hdri_world.py",
            bpy,
            image_path=str(image_path),
            strength=0.75,
            rotation=15.0,
        )
        load_and_call(
            "blender-light-rig/scripts/animate_hdri_rotation.py",
            bpy,
            frame_start=1,
            frame_end=61,
        )

        summary = load_and_call("blender-light-rig/scripts/get_lighting_summary.py", bpy)

        hdri = summary["context"]["world"]["hdri"]
        assert hdri["coordinate_output"] == "Normal"
        assert hdri["strength"] == 0.75
        assert hdri["rotation"] == 15.0
        assert hdri["animation"] == {
            "frame_start": 1,
            "frame_end": 61,
            "start_rotation": 0.0,
            "end_rotation": 360.0,
            "interpolation": "LINEAR",
        }

    def test_set_render_view_transform(self):
        bpy = _make_bpy()

        result = load_and_call(
            "blender-light-rig/scripts/set_render_view_transform.py",
            bpy,
            display_device="Rec.1886 Rec.709 - Display",
            view_transform="Standard",
            exposure=0.25,
        )

        assert result["success"] is True
        assert result["context"]["current"]["display_device"] == "Rec.1886 Rec.709 - Display"
        assert result["context"]["current"]["view_transform"] == "Standard"
        assert result["context"]["current"]["exposure"] == 0.25
