"""Unit tests for Blender interchange, export preset, and shot export skills."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import yaml

from tests.conftest import load_and_call, make_mock_bpy

SKILLS_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_blender" / "skills"
INTERCHANGE_DIR = SKILLS_ROOT / "blender-interchange"
PRESET_DIR = SKILLS_ROOT / "blender-export-preset"
SHOT_DIR = SKILLS_ROOT / "blender-shot-export"
GEOMETRY_DIR = SKILLS_ROOT / "blender-geometry"

INTERCHANGE_TOOLS = {
    "import_file",
    "import_fbx",
    "import_obj",
    "import_usd",
    "import_alembic",
    "export_gltf",
    "export_usd",
    "export_alembic",
    "batch_export",
}
PRESET_TOOLS = {"list_export_presets", "save_export_preset", "load_export_preset", "delete_export_preset"}
SHOT_TOOLS = {"get_shot_info", "export_camera"}


class FakeObjects(list):
    def get(self, name):
        return next((obj for obj in self if obj.name == name), None)


class FakeScene(dict):
    def __init__(self):
        super().__init__()
        self.frame_start = 1
        self.frame_end = 24
        self.frame_current = 1
        self.camera = None
        self.collection = MagicMock()
        self.render = MagicMock()
        self.render.fps = 24
        self.render.resolution_x = 1920
        self.render.resolution_y = 1080


class FakeVertex:
    def __init__(self, co):
        self.co = co


class FakePolygon:
    def __init__(self, vertices):
        self.vertices = vertices


class FakeMesh:
    def __init__(self):
        self.vertices = [
            FakeVertex((0.0, 0.0, 0.0)),
            FakeVertex((1.0, 0.0, 0.0)),
            FakeVertex((0.0, 1.0, 0.0)),
        ]
        self.polygons = [FakePolygon([0, 1, 2])]


class FakeObject:
    def __init__(self, name, obj_type="MESH"):
        self.name = name
        self.type = obj_type
        self.data = FakeMesh() if obj_type == "MESH" else MagicMock()
        self.location = [0.0, 0.0, 0.0]
        self.rotation_euler = [0.0, 0.0, 0.0]
        self.matrix_world = None
        self._selected = False

    def select_set(self, state):
        self._selected = bool(state)


def _bpy_with_scene(objects):
    bpy = make_mock_bpy()
    bpy.data.objects = FakeObjects(objects)
    bpy.context.scene = FakeScene()
    bpy.context.view_layer.objects.active = None
    return bpy


def _write_file_operator(text):
    def _operator(filepath, **_kwargs):
        Path(filepath).write_text(text, encoding="utf-8")
        return {"FINISHED"}

    return _operator


def test_interchange_preset_shot_tools_yaml_declares_modern_contracts():
    for skill_dir, expected in (
        (INTERCHANGE_DIR, INTERCHANGE_TOOLS),
        (PRESET_DIR, PRESET_TOOLS),
        (SHOT_DIR, SHOT_TOOLS),
    ):
        doc = yaml.safe_load((skill_dir / "tools.yaml").read_text(encoding="utf-8"))
        tools = {tool["name"]: tool for tool in doc["tools"]}
        assert set(tools) == expected
        for name, tool in tools.items():
            assert (skill_dir / tool["source_file"]).exists(), name
            assert tool["execution"] == "sync"
            assert tool["affinity"] == "main"
            assert isinstance(tool["timeout_hint_secs"], int)
            assert tool["input_schema"]["type"] == "object"
            assert tool["output_schema"]["properties"]["success"]["type"] == "boolean"
            assert "annotations" in tool

    geometry = yaml.safe_load((GEOMETRY_DIR / "tools.yaml").read_text(encoding="utf-8"))
    geometry_tools = {tool["name"]: tool for tool in geometry["tools"]}
    for name in ("export_fbx", "export_obj"):
        assert geometry_tools[name]["input_schema"]["type"] == "object"
        assert geometry_tools[name]["annotations"]["open_world_hint"] is True


def test_import_obj_reports_imported_objects_and_missing_file(tmp_path):
    source = tmp_path / "asset.obj"
    source.write_text("o Imported\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")
    bpy = _bpy_with_scene([])

    def import_obj(filepath, **_kwargs):
        assert filepath == str(source)
        bpy.data.objects.append(FakeObject("Imported"))
        return {"FINISHED"}

    bpy.ops.wm.obj_import.side_effect = import_obj

    result = load_and_call("blender-interchange/scripts/import_obj.py", bpy, path=str(source))

    assert result["success"] is True
    assert result["context"]["imported_object_names"] == ["Imported"]
    assert result["context"]["format"] == "obj"

    missing = load_and_call("blender-interchange/scripts/import_file.py", bpy, path=str(tmp_path / "missing.fbx"))
    assert missing["success"] is False


def test_import_alembic_reports_imported_cache_objects(tmp_path):
    source = tmp_path / "energy_fx.abc"
    source.write_bytes(b"Ogawa")
    bpy = _bpy_with_scene([])

    def alembic_import(filepath, **_kwargs):
        assert filepath == str(source)
        bpy.data.objects.append(FakeObject("EnergyFxCache"))
        return {"FINISHED"}

    bpy.ops.wm.alembic_import.side_effect = alembic_import

    result = load_and_call("blender-interchange/scripts/import_alembic.py", bpy, path=str(source))

    assert result["success"] is True
    assert result["context"]["format"] == "alembic"
    assert result["context"]["imported_object_names"] == ["EnergyFxCache"]


def test_import_file_supports_gltf(tmp_path):
    source = tmp_path / "asset.gltf"
    source.write_text("{}", encoding="utf-8")
    bpy = _bpy_with_scene([])

    def import_gltf(filepath, **_kwargs):
        assert filepath == str(source)
        bpy.data.objects.append(FakeObject("ImportedGlTF"))
        return {"FINISHED"}

    bpy.ops.import_scene.gltf.side_effect = import_gltf
    result = load_and_call("blender-interchange/scripts/import_file.py", bpy, path=str(source))

    assert result["success"] is True
    assert result["context"]["format"] == "gltf"
    assert result["context"]["imported_object_names"] == ["ImportedGlTF"]


def test_export_obj_fallback_and_gltf_batch_export(tmp_path):
    cube = FakeObject("Cube")
    bpy = _bpy_with_scene([cube])
    bpy.ops.wm.obj_export.side_effect = RuntimeError("operator unavailable")
    bpy.ops.export_scene.gltf.side_effect = _write_file_operator("gltf")

    obj_path = tmp_path / "mesh.obj"
    result = load_and_call("blender-geometry/scripts/export_obj.py", bpy, path=str(obj_path), object_names=["Cube"])
    assert result["success"] is True
    assert obj_path.read_text(encoding="utf-8").startswith("# Exported by dcc-mcp-blender")
    assert result["context"]["written_files"] == [str(obj_path)]

    preset = load_and_call(
        "blender-export-preset/scripts/save_export_preset.py",
        bpy,
        name="GameGLTF",
        format="gltf",
        options={"export_format": "GLTF_SEPARATE"},
    )
    assert preset["success"] is True

    gltf_path = tmp_path / "mesh.gltf"
    batch = load_and_call(
        "blender-interchange/scripts/batch_export.py",
        bpy,
        preset_name="GameGLTF",
        items=[{"path": str(gltf_path), "object_names": ["Cube"]}],
    )
    assert batch["success"] is True
    assert batch["context"]["written_files"] == [str(gltf_path)]
    assert gltf_path.read_text(encoding="utf-8") == "gltf"

    invalid = load_and_call(
        "blender-interchange/scripts/export_alembic.py",
        bpy,
        path=str(tmp_path / "bad.abc"),
        frame_range=[10, 1],
    )
    assert invalid["success"] is False


def test_export_preset_lifecycle():
    bpy = _bpy_with_scene([])

    saved = load_and_call(
        "blender-export-preset/scripts/save_export_preset.py",
        bpy,
        name="UsdShot",
        format="usd",
        options={"visible_objects_only": True},
    )
    assert saved["success"] is True

    listed = load_and_call("blender-export-preset/scripts/list_export_presets.py", bpy)
    assert listed["context"]["presets"] == [{"format": "usd", "name": "UsdShot", "option_count": 1}]

    loaded = load_and_call("blender-export-preset/scripts/load_export_preset.py", bpy, name="UsdShot")
    assert loaded["success"] is True
    assert loaded["context"]["normalized_options"] == {"visible_objects_only": True}

    deleted = load_and_call("blender-export-preset/scripts/delete_export_preset.py", bpy, name="UsdShot")
    assert deleted["success"] is True

    missing = load_and_call("blender-export-preset/scripts/load_export_preset.py", bpy, name="UsdShot")
    assert missing["success"] is False


def test_shot_info_and_camera_export(tmp_path):
    camera = FakeObject("Camera", "CAMERA")
    camera.data.name = "CameraData"
    camera.data.lens = 35.0
    camera.data.sensor_width = 32.0
    bpy = _bpy_with_scene([camera])
    bpy.context.scene.camera = camera

    shot = load_and_call("blender-shot-export/scripts/get_shot_info.py", bpy)
    assert shot["success"] is True
    assert shot["context"]["camera"]["camera_name"] == "Camera"
    assert shot["context"]["frame_range"] == [1, 24]

    output = tmp_path / "camera.json"
    exported = load_and_call(
        "blender-shot-export/scripts/export_camera.py",
        bpy,
        camera_name="Camera",
        path=str(output),
        frame_range=[5, 12],
    )
    assert exported["success"] is True
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["frame_range"] == [5, 12]

    invalid = load_and_call("blender-shot-export/scripts/get_shot_info.py", bpy, camera_name="Cube")
    assert invalid["success"] is False


def test_import_usd_reports_imported_objects_and_summary(tmp_path):
    """USD import should return imported objects with summary counts."""
    source = tmp_path / "scene.usda"
    source.write_text("#usda 1.0\n", encoding="utf-8")
    bpy = _bpy_with_scene([])

    def usd_import(filepath, **_kwargs):
        assert filepath == str(source)
        cube = FakeObject("UsdCube", "MESH")
        light = FakeObject("UsdLight", "LIGHT")
        bpy.data.objects.append(cube)
        bpy.data.objects.append(light)
        return {"FINISHED"}

    bpy.ops.wm.usd_import.side_effect = usd_import

    result = load_and_call(
        "blender-interchange/scripts/import_usd.py",
        bpy,
        filepath=str(source),
        scale=0.5,
        import_meshes=True,
        import_lights=True,
        import_materials=False,
        return_summary=True,
    )

    assert result["success"] is True
    assert result["context"]["imported_object_names"] == ["UsdCube", "UsdLight"]
    assert result["context"]["format"] == "usd"
    assert result["context"]["imported_count"] == 2
    assert "elapsed_ms" in result["context"]
    assert "summary" in result["context"]
    summary = result["context"]["summary"]
    assert summary["total_objects"] == 2
    assert summary["by_type"] == {"MESH": 1, "LIGHT": 1}


def test_import_usd_filters_only_unsupported_operator_options(tmp_path):
    """One unsupported Blender option must not discard the supported USD options."""
    source = tmp_path / "scene.usda"
    source.write_text("#usda 1.0\n", encoding="utf-8")
    bpy = _bpy_with_scene([])
    received = {}

    class Property:
        def __init__(self, identifier):
            self.identifier = identifier

    class UsdImportOperator:
        def get_rna_type(self):
            properties = [
                Property("rna_type"),
                Property("filepath"),
                Property("import_meshes"),
                Property("import_materials"),
                Property("import_cameras"),
                Property("import_lights"),
                Property("import_subdiv"),
                Property("scale"),
            ]
            return type("RnaType", (), {"properties": properties})()

        def __call__(self, **kwargs):
            received.update(kwargs)
            bpy.data.objects.append(FakeObject("UsdMesh"))
            return {"FINISHED"}

    bpy.ops.wm.usd_import = UsdImportOperator()

    result = load_and_call(
        "blender-interchange/scripts/import_usd.py",
        bpy,
        filepath=str(source),
        import_meshes=True,
        import_materials=True,
        import_cameras=True,
        import_lights=True,
        import_textures=True,
        import_subdiv=True,
        scale=0.5,
    )

    assert result["success"] is True
    assert received == {
        "filepath": str(source),
        "import_meshes": True,
        "import_materials": True,
        "import_cameras": True,
        "import_lights": True,
        "import_subdiv": True,
        "scale": 0.5,
    }
    assert result["context"]["warnings"] == ["Ignored unsupported options: ['import_textures']"]


def test_import_usd_reports_missing_file(tmp_path):
    """USD import should fail gracefly for missing file."""
    bpy = _bpy_with_scene([])
    missing = tmp_path / "missing.usda"
    result = load_and_call(
        "blender-interchange/scripts/import_usd.py",
        bpy,
        filepath=str(missing),
    )
    assert result["success"] is False


def test_import_usd_with_collection(tmp_path):
    """USD import should optionally place objects into a named collection."""
    source = tmp_path / "asset.usdc"
    source.write_text("#usda 1.0\n", encoding="utf-8")
    bpy = _bpy_with_scene([])

    def usd_import(filepath, **_kwargs):
        bpy.data.objects.append(FakeObject("UsdMesh"))
        return {"FINISHED"}

    bpy.ops.wm.usd_import.side_effect = usd_import

    result = load_and_call(
        "blender-interchange/scripts/import_usd.py",
        bpy,
        filepath=str(source),
        collection_name="USD_Assets",
    )
    assert result["success"] is True
    assert result["context"]["collection_name"] == "USD_Assets"


def test_import_usd_exposes_typed_options(tmp_path):
    """Ensure import_usd tool schema exposes typed USD import options."""
    import yaml

    doc = yaml.safe_load((INTERCHANGE_DIR / "tools.yaml").read_text(encoding="utf-8"))
    tool = next((t for t in doc["tools"] if t["name"] == "import_usd"), None)
    assert tool is not None, "import_usd tool must exist in tools.yaml"

    props = tool["input_schema"]["properties"]
    assert "filepath" in props
    assert "scale" in props
    assert "import_meshes" in props
    assert "import_materials" in props
    assert "import_cameras" in props
    assert "import_lights" in props
    assert "import_textures" in props
    assert "import_subdiv" in props
    assert "prim_path_mask" in props
    assert "collection_name" in props
    assert "return_summary" in props
    assert "options" in props

    required = tool["input_schema"]["required"]
    assert required == ["filepath"]

    assert tool["affinity"] == "main"
    assert tool["execution"] == "sync"
