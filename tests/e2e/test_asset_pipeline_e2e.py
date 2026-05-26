"""E2E tests for Blender validation and local pipeline skills."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

bpy = pytest.importorskip("bpy", reason="bpy not available - run inside Blender Python interpreter")

pytestmark = pytest.mark.e2e

from tests.e2e.conftest import load_skill  # noqa: E402


def _new_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


class TestAssetPipelineE2E:
    def setup_method(self):
        _new_scene()

    def test_validate_scene_and_create_publish_manifest(self):
        bpy.ops.mesh.primitive_cube_add()
        cube_name = bpy.context.active_object.name

        tag_mod = load_skill("blender-pipeline", "tag_asset_metadata")
        tag_result = tag_mod.tag_asset_metadata(cube_name, {"asset_type": "prop", "department": "layout"})
        assert tag_result["success"] is True

        validate_mod = load_skill("blender-validation", "validate_mesh")
        validate_result = validate_mod.validate_mesh(cube_name, rules={"require_uvs": False})
        assert validate_result["success"] is True
        assert validate_result["context"]["report"]["passed"] is True

        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "publish_manifest.json"
            manifest_mod = load_skill("blender-pipeline", "create_publish_manifest")
            manifest_result = manifest_mod.create_publish_manifest(
                object_names=[cube_name],
                output_path=str(manifest_path),
                metadata={"target": "smoke"},
            )
            assert manifest_result["success"] is True
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            assert payload["assets"][0]["metadata"]["asset_type"] == "prop"
