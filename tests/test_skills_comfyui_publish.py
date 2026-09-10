"""Tests for Blender-owned artifacts consumed by official ComfyUI."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml
from dcc_mcp_core.asset_import import AssetDescriptor

import dcc_mcp_blender._comfyui_publish_ops as publish_ops

ROOT = Path(__file__).parent.parent


def test_pipeline_declares_comfyui_publish_contract():
    skill = ROOT / "src" / "dcc_mcp_blender" / "skills" / "blender-pipeline"
    tools = yaml.safe_load((skill / "tools.yaml").read_text(encoding="utf-8"))["tools"]
    tool = next(item for item in tools if item["name"] == "publish_comfyui_asset")
    assert tool["affinity"] == "main"
    assert tool["input_schema"]["required"] == ["export_root", "asset_name"]
    assert (skill / tool["source_file"]).is_file()


def test_publish_creates_verified_official_comfyui_artifact(tmp_path, monkeypatch):
    payload = b"glTF-test-payload"

    def fake_export(path, object_names=None, options=None):
        assert object_names == ["Cube"]
        assert options["export_format"] == "GLB"
        Path(path).write_bytes(payload)
        return {"success": True, "context": {"written_files": [path]}}

    monkeypatch.setattr(publish_ops, "export_gltf", fake_export)
    result = publish_ops.publish_comfyui_asset(str(tmp_path), "Hero Cube", ["Cube"])

    assert result["success"] is True
    context = result["context"]
    assert context["official_comfyui_ready"] is True
    assert context["sync_extension_required"] is False
    assert context["sha256"] == hashlib.sha256(payload).hexdigest()
    assert Path(context["filepath"]).name == "Hero-Cube.glb"
    descriptor = json.loads(Path(context["manifest_path"]).read_text(encoding="utf-8"))
    assert descriptor == context["descriptor"]
    assert descriptor["variants"][0]["format"] == "glb"
    parsed = AssetDescriptor.from_dict(descriptor)
    parsed.validate()
    assert parsed.to_dict() == descriptor


def test_publish_rejects_invalid_names_and_non_array_object_names(tmp_path):
    assert publish_ops.publish_comfyui_asset(str(tmp_path), "...", ["Cube"])["success"] is False
    assert publish_ops.publish_comfyui_asset(str(tmp_path), "Cube", "Cube")["success"] is False
