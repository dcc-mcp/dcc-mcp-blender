"""E2E tests for Blender interchange and export tools.

Requires a real Blender Python interpreter.
"""

from __future__ import annotations

import pytest

bpy = pytest.importorskip("bpy", reason="bpy not available - run inside Blender Python interpreter")

pytestmark = pytest.mark.e2e

from tests.e2e.conftest import load_skill  # noqa: E402


def _new_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


class TestInterchangeExportE2E:
    def setup_method(self):
        _new_scene()

    def test_import_obj_export_obj_and_camera_metadata(self, tmp_path):
        obj_path = tmp_path / "input.obj"
        obj_path.write_text(
            "o ImportedTriangle\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n",
            encoding="utf-8",
        )

        import_mod = load_skill("blender-interchange", "import_obj")
        imported = import_mod.import_obj(path=str(obj_path))
        assert imported["success"] is True
        assert imported["context"]["imported_count"] >= 1

        export_mod = load_skill("blender-geometry", "export_obj")
        exported_path = tmp_path / "output.obj"
        exported = export_mod.export_obj(path=str(exported_path))
        assert exported["success"] is True
        assert exported_path.is_file()
        assert exported_path.stat().st_size > 0

        bpy.ops.object.camera_add(location=(0, -5, 3), rotation=(1.0, 0.0, 0.0))
        camera = bpy.context.active_object
        camera.name = "ShotCam"
        bpy.context.scene.camera = camera

        shot_mod = load_skill("blender-shot-export", "get_shot_info")
        shot = shot_mod.get_shot_info(camera_name="ShotCam", frame_range=[1, 12])
        assert shot["success"] is True
        assert shot["context"]["frame_range"] == [1, 12]

        camera_mod = load_skill("blender-shot-export", "export_camera")
        camera_json = tmp_path / "camera.json"
        camera_export = camera_mod.export_camera(camera_name="ShotCam", path=str(camera_json))
        assert camera_export["success"] is True
        assert camera_json.is_file()

    def test_fbx_json_enum_flags_filter_actual_exported_objects(self, tmp_path):
        bpy.ops.mesh.primitive_cube_add()
        mesh = bpy.context.object
        mesh.name = "FlagMesh"
        bpy.ops.object.camera_add()
        camera = bpy.context.object
        camera.name = "ExcludedCamera"
        mesh.select_set(True)
        camera.select_set(True)
        options = {"object_types": ["MESH"], "bake_anim": False, "global_scale": 2.0}
        batch = load_skill("blender-interchange", "batch_export")
        target = tmp_path / "flags.fbx"
        result = batch.batch_export(
            items=[
                {
                    "path": str(target),
                    "format": "fbx",
                    "object_names": [mesh.name, camera.name],
                    "options": options,
                }
            ]
        )
        assert result["success"] is True
        assert result["context"]["results"][0]["normalized_options"] == options
        assert target.is_file() and target.stat().st_size > 0
        _new_scene()
        importer = load_skill("blender-interchange", "import_fbx")
        imported = importer.import_fbx(path=str(target))
        assert imported["success"] is True
        assert [obj.type for obj in bpy.data.objects] == ["MESH"]
        assert bpy.context.scene.objects[0].animation_data is None

    @pytest.mark.parametrize(
        "options",
        [
            {"unknown_option": True},
            {"object_types": ["INVALID"]},
            {"object_types": "MESH"},
            {"global_scale": "invalid"},
        ],
    )
    def test_native_invalid_fbx_options_do_not_write_artifacts(self, tmp_path, options):
        bpy.ops.mesh.primitive_cube_add()
        export = load_skill("blender-geometry", "export_fbx")
        target = tmp_path / "invalid.fbx"
        result = export.export_fbx(path=str(target), options=options)
        assert result["success"] is False
        assert not target.exists()

    @pytest.mark.parametrize("textures", [True, False])
    def test_typed_usd_import_options_match_supported_rna(self, tmp_path, textures):
        target = tmp_path / "triangle.usda"
        target.write_text(
            '#usda 1.0\ndef Mesh "Triangle" {\n'
            " point3f[] points = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]\n"
            " int[] faceVertexCounts = [3]\n int[] faceVertexIndices = [0, 1, 2]\n}\n",
            encoding="utf-8",
        )
        importer = load_skill("blender-interchange", "import_usd")
        result = importer.import_usd(filepath=str(target), import_textures=textures, import_subdiv=False)
        assert result["success"] is True
        assert result["context"]["imported_count"] >= 1
