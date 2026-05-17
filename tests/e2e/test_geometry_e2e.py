"""E2E tests for blender-geometry inside a real Blender interpreter."""

from __future__ import annotations

import tempfile
import threading
from pathlib import Path

import pytest

bpy = pytest.importorskip("bpy", reason="bpy not available - run inside Blender Python interpreter")

pytestmark = pytest.mark.e2e

from tests.e2e.conftest import load_skill  # noqa: E402


def _new_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


class TestGeometrySkillsE2E:
    def setup_method(self):
        _new_scene()

    def test_create_sphere_reports_main_thread(self):
        mod = load_skill("blender-geometry", "create_sphere")

        result = mod.create_sphere(radius=1.25, name="E2E Sphere", location=[1.0, 2.0, 3.0])

        assert result["success"] is True
        assert "E2E Sphere" in bpy.data.objects
        assert result["context"]["thread_ident"] == threading.get_ident()

    def test_save_and_export_files_exist(self):
        load_skill("blender-geometry", "create_sphere").create_sphere(name="Export Sphere")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            blend_path = tmp_path / "scene.blend"
            fbx_path = tmp_path / "scene.fbx"
            obj_path = tmp_path / "scene.obj"

            assert load_skill("blender-geometry", "save_blend").save_blend(str(blend_path))["success"] is True
            assert load_skill("blender-geometry", "export_fbx").export_fbx(str(fbx_path))["success"] is True
            assert load_skill("blender-geometry", "export_obj").export_obj(str(obj_path))["success"] is True

            exists_mod = load_skill("blender-geometry", "file_exists")
            for path in (blend_path, fbx_path, obj_path):
                result = exists_mod.file_exists(str(path))
                assert result["success"] is True
                assert result["context"]["exists"] is True
                assert result["context"]["size"] > 0
