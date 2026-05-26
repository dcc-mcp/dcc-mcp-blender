"""Unit tests for material library and texture bake skill scripts."""

from __future__ import annotations

from types import SimpleNamespace

from tests.conftest import load_and_call, make_mock_bpy


class _Collection(list):
    def get(self, name):
        for item in self:
            if getattr(item, "name", None) == name:
                return item
        return None


class _Socket(SimpleNamespace):
    def __init__(self, name, default_value=None):
        super().__init__(
            name=name,
            identifier=name,
            default_value=default_value,
            type="VALUE",
            is_linked=False,
            node=None,
        )


class _Node:
    def __init__(self, name, node_type, inputs=None, outputs=None):
        self.name = name
        self.type = node_type
        self.bl_idname = node_type
        self.label = ""
        self.location = [0.0, 0.0]
        self.inputs = inputs or {}
        self.outputs = outputs or {}
        self.image = None
        for socket in [*self.inputs.values(), *self.outputs.values()]:
            socket.node = self


class _Nodes(_Collection):
    def __init__(self, nodes=None):
        super().__init__(nodes or [])
        self.active = None

    def new(self, type):  # noqa: A002
        if type == "ShaderNodeTexImage":
            node = _Node("Image Texture", type, outputs={"Color": _Socket("Color", [1.0, 1.0, 1.0, 1.0])})
        else:
            node = _Node(type, type)
        self.append(node)
        return node


class _Links(list):
    def new(self, from_socket, to_socket):
        link = SimpleNamespace(
            from_node=from_socket.node,
            from_socket=from_socket,
            to_node=to_socket.node,
            to_socket=to_socket,
        )
        self.append(link)
        return link


class _Material:
    def __init__(self, name="Mat"):
        self.name = name
        self.use_nodes = True
        self.diffuse_color = [1.0, 1.0, 1.0, 1.0]
        self.blend_method = "OPAQUE"
        principled = _Node(
            "Principled BSDF",
            "BSDF_PRINCIPLED",
            inputs={
                "Base Color": _Socket("Base Color", [1.0, 1.0, 1.0, 1.0]),
                "Metallic": _Socket("Metallic", 0.0),
                "Roughness": _Socket("Roughness", 0.5),
            },
            outputs={"BSDF": _Socket("BSDF")},
        )
        output = _Node("Material Output", "OUTPUT_MATERIAL", inputs={"Surface": _Socket("Surface")})
        self.node_tree = SimpleNamespace(nodes=_Nodes([principled, output]), links=_Links())


class _MaterialCollection(_Collection):
    def new(self, name):
        material = _Material(name)
        self.append(material)
        return material

    def remove(self, material):
        self[:] = [item for item in self if item is not material]


class _FakeImage:
    def __init__(self, name="image.png", filepath=""):
        self.name = name
        self.filepath = filepath
        self.filepath_raw = filepath
        self.size = [2, 2]
        self.source = "FILE"
        self.colorspace_settings = SimpleNamespace(name="sRGB")
        self.reloaded = False

    def reload(self):
        self.reloaded = True

    def save(self):
        return None


class _ImageCollection(_Collection):
    def load(self, path, check_existing=True):
        image = _FakeImage(name=str(path).split("\\")[-1].split("/")[-1], filepath=str(path))
        self.append(image)
        return image

    def new(self, name, width=2, height=2, alpha=True, float_buffer=False):
        image = _FakeImage(name=name)
        image.size = [width, height]
        self.append(image)
        return image


class _FakeScene(dict):
    def __init__(self):
        super().__init__()
        self.render = SimpleNamespace(engine="CYCLES")
        self.view_settings = SimpleNamespace(view_transform="AgX", look="None", exposure=0.0, gamma=1.0)

    def get(self, key, default=None):
        return dict.get(self, key, default)


class _FakeMeshData:
    def __init__(self):
        self.materials = []
        self.uv_layers = [object()]


class _FakeObject:
    def __init__(self, name="Cube", type="MESH"):
        self.name = name
        self.type = type
        self.data = _FakeMeshData()
        self.material_slots = []
        self.selected = False

    def select_set(self, value):
        self.selected = value


def _make_bpy(*objects, materials=None, images=None):
    bpy = make_mock_bpy()
    bpy.context.scene = _FakeScene()
    bpy.data.objects = _Collection(objects)
    bpy.data.materials = _MaterialCollection(materials or [])
    bpy.data.images = _ImageCollection(images or [])
    return bpy


class TestMaterialLibrary:
    def test_material_preset_round_trip_and_delete(self):
        material = _Material("HeroMat")
        cube = _FakeObject("Cube")
        bpy = _make_bpy(cube, materials=[material])

        save = load_and_call(
            "blender-material-library/scripts/save_material_preset.py",
            bpy,
            material_name="HeroMat",
            preset_name="hero",
        )
        listed = load_and_call("blender-material-library/scripts/list_material_presets.py", bpy)
        loaded = load_and_call(
            "blender-material-library/scripts/load_material_preset.py",
            bpy,
            preset_name="hero",
            target_object="Cube",
        )
        deleted = load_and_call(
            "blender-material-library/scripts/delete_material_preset.py",
            bpy,
            preset_name="hero",
        )

        assert save["success"] is True
        assert listed["context"]["count"] == 1
        assert loaded["success"] is True
        assert loaded["context"]["assigned"] is True
        assert cube.data.materials[0].name == "HeroMat"
        assert deleted["success"] is True

    def test_missing_material_preset_returns_error(self):
        bpy = _make_bpy()

        result = load_and_call(
            "blender-material-library/scripts/save_material_preset.py",
            bpy,
            material_name="Missing",
            preset_name="missing",
        )

        assert result["success"] is False

    def test_material_attribute_assignment_and_connections(self):
        material = _Material("HeroMat")
        bpy = _make_bpy(materials=[material])

        result = load_and_call(
            "blender-material-library/scripts/set_material_attribute.py",
            bpy,
            material_name="HeroMat",
            attribute="metallic",
            value=0.8,
        )
        connections = load_and_call(
            "blender-material-library/scripts/get_material_connections.py",
            bpy,
            material_name="HeroMat",
        )

        assert result["success"] is True
        assert result["context"]["value"] == 0.8
        assert connections["success"] is True
        assert connections["context"]["node_count"] == 2

    def test_shader_assignment_reports_slots(self):
        material = _Material("HeroMat")
        cube = _FakeObject("Cube")
        cube.data.materials.append(material)
        bpy = _make_bpy(cube, materials=[material])

        result = load_and_call(
            "blender-material-library/scripts/get_shader_assignment.py",
            bpy,
            object_name="Cube",
        )

        assert result["success"] is True
        assert result["context"]["assignments"][0]["material_name"] == "HeroMat"

    def test_assign_texture_requires_existing_image_path(self, tmp_path):
        material = _Material("HeroMat")
        bpy = _make_bpy(materials=[material])
        texture = tmp_path / "albedo.png"
        texture.write_bytes(b"png")

        ok = load_and_call(
            "blender-material-library/scripts/assign_texture.py",
            bpy,
            material_name="HeroMat",
            image_path=str(texture),
        )
        missing = load_and_call(
            "blender-material-library/scripts/assign_texture.py",
            bpy,
            material_name="HeroMat",
            image_path=str(tmp_path / "missing.png"),
        )

        assert ok["success"] is True
        assert missing["success"] is False

    def test_list_and_reload_images(self):
        image = _FakeImage("albedo.png", "albedo.png")
        bpy = _make_bpy(images=[image])

        listed = load_and_call("blender-material-library/scripts/list_images.py", bpy)
        reloaded = load_and_call("blender-material-library/scripts/reload_image.py", bpy, image_name="albedo.png")

        assert listed["success"] is True
        assert listed["context"]["count"] == 1
        assert reloaded["success"] is True
        assert image.reloaded is True

    def test_color_management_round_trip(self):
        bpy = _make_bpy()

        listed = load_and_call("blender-material-library/scripts/list_color_spaces.py", bpy)
        updated = load_and_call(
            "blender-material-library/scripts/set_color_management.py",
            bpy,
            view_transform="Standard",
            exposure=0.5,
        )

        assert listed["success"] is True
        assert updated["success"] is True
        assert updated["context"]["current"]["view_transform"] == "Standard"
        assert updated["context"]["current"]["exposure"] == 0.5


class TestTextureBake:
    def test_list_bake_targets(self):
        cube = _FakeObject("Cube")
        bpy = _make_bpy(cube)

        result = load_and_call("blender-texture-bake/scripts/list_bake_targets.py", bpy)

        assert result["success"] is True
        assert result["context"]["targets"][0]["object_name"] == "Cube"

    def test_bake_textures_dry_run_plans_files(self, tmp_path):
        cube = _FakeObject("Cube")
        bpy = _make_bpy(cube)

        result = load_and_call(
            "blender-texture-bake/scripts/bake_textures.py",
            bpy,
            object_name="Cube",
            maps=["diffuse", "normal"],
            output_dir=str(tmp_path),
            resolution=16,
            dry_run=True,
        )

        assert result["success"] is True
        assert result["context"]["written_files"] == []
        assert len(result["context"]["planned_files"]) == 2

    def test_bake_textures_rejects_unsupported_map(self, tmp_path):
        cube = _FakeObject("Cube")
        bpy = _make_bpy(cube)

        result = load_and_call(
            "blender-texture-bake/scripts/bake_textures.py",
            bpy,
            object_name="Cube",
            maps=["metallic"],
            output_dir=str(tmp_path),
        )

        assert result["success"] is False
        assert "supported_maps" in result["context"]

    def test_bake_textures_rejects_unsafe_path(self):
        cube = _FakeObject("Cube")
        bpy = _make_bpy(cube)

        result = load_and_call(
            "blender-texture-bake/scripts/bake_textures.py",
            bpy,
            object_name="Cube",
            maps=["diffuse"],
            output_dir="https://example.com/out",
        )

        assert result["success"] is False

    def test_bake_textures_missing_object(self, tmp_path):
        bpy = _make_bpy()

        result = load_and_call(
            "blender-texture-bake/scripts/bake_textures.py",
            bpy,
            object_name="Missing",
            maps=["diffuse"],
            output_dir=str(tmp_path),
        )

        assert result["success"] is False

    def test_explicit_ambient_occlusion_dry_run(self, tmp_path):
        cube = _FakeObject("Cube")
        bpy = _make_bpy(cube)

        result = load_and_call(
            "blender-texture-bake/scripts/bake_ambient_occlusion.py",
            bpy,
            object_name="Cube",
            output_path=str(tmp_path / "ao.png"),
            settings={"dry_run": True, "resolution": 16},
        )

        assert result["success"] is True
        assert result["context"]["map_name"] == "ambient_occlusion"
        assert result["context"]["written_files"] == []

    def test_transfer_maps_missing_target(self, tmp_path):
        source = _FakeObject("Source")
        bpy = _make_bpy(source)

        result = load_and_call(
            "blender-texture-bake/scripts/transfer_maps.py",
            bpy,
            source_object="Source",
            target_object="Missing",
            output_dir=str(tmp_path),
            dry_run=True,
        )

        assert result["success"] is False
