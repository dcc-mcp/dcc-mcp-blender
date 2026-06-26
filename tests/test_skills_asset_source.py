"""Unit tests for blender-asset-source skill: search_assets and descriptor shape.

Tests cover:
- Filesystem search with real temporary directory
- Name/type filtering
- Edge cases: empty dir, missing path, permission error
- Blender asset library scan (mock)
- AssetDescriptor shape and required fields
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from tests.conftest import load_and_call, make_mock_bpy


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("dummy content", encoding="utf-8")


class TestSearchAssetsFilesystem:
    def test_returns_descriptors_for_supported_files(self, tmp_path):
        """Filesystem scan returns one AssetDescriptor per supported file."""
        _touch(tmp_path / "chair.fbx")
        _touch(tmp_path / "table.obj")
        _touch(tmp_path / "scene.blend")
        _touch(tmp_path / "readme.txt")  # unsupported — should be ignored

        result = load_and_call(
            "blender-asset-source/scripts/search_assets.py",
            make_mock_bpy(),
            source="filesystem",
            path=str(tmp_path),
        )

        assert result["success"] is True
        descriptors = result["context"]["descriptors"]
        assert len(descriptors) == 3
        found_types = {d["asset_type"] for d in descriptors}
        assert found_types == {"fbx", "obj", "blend"}

    def test_descriptor_shape(self, tmp_path):
        """Every descriptor has the required fields and correct types."""
        _touch(tmp_path / "test_model.fbx")

        result = load_and_call(
            "blender-asset-source/scripts/search_assets.py",
            make_mock_bpy(),
            source="filesystem",
            path=str(tmp_path),
        )

        desc = result["context"]["descriptors"][0]
        assert isinstance(desc["name"], str) and desc["name"] == "test_model"
        assert isinstance(desc["path"], str) and desc["path"].endswith("test_model.fbx")
        assert isinstance(desc["asset_type"], str) and desc["asset_type"] == "fbx"
        assert isinstance(desc["source"], str) and desc["source"] == "filesystem"
        assert isinstance(desc["size_bytes"], int) and desc["size_bytes"] > 0
        assert isinstance(desc["modified_at"], str) and len(desc["modified_at"]) > 0
        assert isinstance(desc["metadata"], dict)

    def test_filters_by_query(self, tmp_path):
        """Case-insensitive name query filters results."""
        _touch(tmp_path / "character_hero.fbx")
        _touch(tmp_path / "character_villain.fbx")
        _touch(tmp_path / "prop_chair.obj")

        result = load_and_call(
            "blender-asset-source/scripts/search_assets.py",
            make_mock_bpy(),
            source="filesystem",
            path=str(tmp_path),
            query="character",
        )

        names = {d["name"] for d in result["context"]["descriptors"]}
        assert names == {"character_hero", "character_villain"}

    def test_filters_by_asset_type(self, tmp_path):
        """asset_types parameter restricts results."""
        _touch(tmp_path / "mesh.fbx")
        _touch(tmp_path / "mesh.obj")
        _touch(tmp_path / "scene.usd")

        result = load_and_call(
            "blender-asset-source/scripts/search_assets.py",
            make_mock_bpy(),
            source="filesystem",
            path=str(tmp_path),
            asset_types=["fbx", "usd"],
        )

        types = {d["asset_type"] for d in result["context"]["descriptors"]}
        assert types == {"fbx", "usd"}

    def test_rejects_unsupported_asset_type(self, tmp_path):
        """Unknown asset type produces an error."""
        result = load_and_call(
            "blender-asset-source/scripts/search_assets.py",
            make_mock_bpy(),
            source="filesystem",
            path=str(tmp_path),
            asset_types=["exe"],
        )

        assert result["success"] is False
        assert "Unsupported" in result["message"]

    def test_empty_directory(self, tmp_path):
        """Empty directory returns zero results without error."""
        result = load_and_call(
            "blender-asset-source/scripts/search_assets.py",
            make_mock_bpy(),
            source="filesystem",
            path=str(tmp_path),
        )

        assert result["success"] is True
        assert result["context"]["count"] == 0

    def test_missing_path_returns_error(self):
        """Nonexistent directory returns an error."""
        result = load_and_call(
            "blender-asset-source/scripts/search_assets.py",
            make_mock_bpy(),
            source="filesystem",
            path="/nonexistent/path/12345",
        )

        assert result["success"] is False
        assert "Directory not found" in result["message"]

    def test_no_path_and_no_blend_file_returns_error(self):
        """Missing path with no open Blender file returns error."""
        bpy = make_mock_bpy()
        bpy.data.filepath = ""

        result = load_and_call(
            "blender-asset-source/scripts/search_assets.py",
            bpy,
            source="filesystem",
        )

        assert result["success"] is False
        assert "No search path" in result["message"]

    def test_respects_max_results(self, tmp_path):
        """max_results caps the number of returned descriptors."""
        for i in range(10):
            _touch(tmp_path / f"asset_{i}.fbx")

        result = load_and_call(
            "blender-asset-source/scripts/search_assets.py",
            make_mock_bpy(),
            source="filesystem",
            path=str(tmp_path),
            max_results=3,
        )

        assert result["success"] is True
        assert result["context"]["count"] == 3

    def test_uses_blend_file_directory_as_fallback(self, tmp_path):
        """When no path is given, use the blend file's parent directory."""
        _touch(tmp_path / "asset.fbx")
        bpy = make_mock_bpy()
        bpy.data.filepath = str(tmp_path / "scene.blend")

        result = load_and_call(
            "blender-asset-source/scripts/search_assets.py",
            bpy,
            source="filesystem",
        )

        assert result["success"] is True
        assert result["context"]["count"] == 1


class TestSearchAssetsAssetLibrary:
    def test_asset_library_scan_returns_results(self, tmp_path):
        """Mock asset library scan returns descriptors from library paths."""
        lib_dir = tmp_path / "asset_library"
        _touch(lib_dir / "hero.fbx")
        _touch(lib_dir / "sword.obj")

        bpy = make_mock_bpy()
        mock_lib = MagicMock()
        mock_lib.name = "MyAssets"
        mock_lib.path = str(lib_dir)
        bpy.data.asset_libraries = [mock_lib]

        result = load_and_call(
            "blender-asset-source/scripts/search_assets.py",
            bpy,
            source="asset_library",
        )

        assert result["success"] is True
        descriptors = result["context"]["descriptors"]
        assert len(descriptors) == 2
        for d in descriptors:
            assert d["source"] == "asset_library"
            assert d["metadata"].get("library_name") == "MyAssets"

    def test_asset_library_marks_source_correctly(self, tmp_path):
        """Descriptors from asset library have source='asset_library'."""
        lib_dir = tmp_path / "my_lib"
        _touch(lib_dir / "asset.blend")

        bpy = make_mock_bpy()
        mock_lib = MagicMock()
        mock_lib.name = "TestLib"
        mock_lib.path = str(lib_dir)
        bpy.data.asset_libraries = [mock_lib]

        result = load_and_call(
            "blender-asset-source/scripts/search_assets.py",
            bpy,
            source="asset_library",
        )

        for d in result["context"]["descriptors"]:
            assert d["source"] == "asset_library"


class TestSearchAssetsErrors:
    def test_no_bpy_returns_empty_for_asset_library(self):
        """Without bpy, asset_library source returns no results gracefully."""
        from dcc_mcp_blender._asset_source_ops import search_assets

        with patch.dict(sys.modules, {"bpy": None}):
            result = search_assets(source="asset_library")

        assert result["success"] is True
        assert result["context"]["count"] == 0

    def test_descriptor_fields_match_contract(self, tmp_path):
        """All AssetDescriptor fields present and non-null for a real file."""
        _touch(tmp_path / "test.usd")

        result = load_and_call(
            "blender-asset-source/scripts/search_assets.py",
            make_mock_bpy(),
            source="filesystem",
            path=str(tmp_path),
        )

        desc = result["context"]["descriptors"][0]
        required_fields = {"name", "path", "asset_type", "source", "size_bytes", "modified_at", "metadata"}
        assert required_fields.issubset(desc.keys()), f"Missing fields: {required_fields - desc.keys()}"
        for field in required_fields:
            assert desc[field] is not None, f"Field {field} is None"

    def test_permission_error_on_directory(self, tmp_path):
        """Permission error when scanning returns appropriate error."""
        from dcc_mcp_blender._asset_source_ops import _scan_filesystem

        with patch.object(Path, "iterdir", side_effect=PermissionError("denied")):
            results, error = _scan_filesystem(tmp_path)

        assert len(results) == 0
        assert error is not None
        assert "Permission denied" in error["message"]
