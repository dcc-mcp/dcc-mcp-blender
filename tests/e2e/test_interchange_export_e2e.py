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
