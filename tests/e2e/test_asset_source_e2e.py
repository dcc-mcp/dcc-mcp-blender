"""Discover an actual registered library without persistent preference changes."""

from __future__ import annotations

from pathlib import Path

import pytest

bpy = pytest.importorskip("bpy", reason="Requires native Blender")
pytestmark = pytest.mark.e2e

from tests.e2e.conftest import load_skill  # noqa: E402


def test_registered_local_library_is_discoverable(tmp_path):
    libraries = bpy.context.preferences.filepaths.asset_libraries
    fixture = tmp_path / "registered_asset_probe.obj"
    fixture.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")
    before = [(library.name, library.path) for library in libraries]
    # Blender 3.6 exposes a read-only RNA collection; the registration operator
    # is the common API across legacy and current releases. Never save prefs.
    assert bpy.ops.preferences.asset_library_add(directory=str(tmp_path)) == {"FINISHED"}
    library = next(item for item in libraries if Path(item.path).resolve() == tmp_path.resolve())
    library.name = "RegisteredDiscoveryProbe"
    try:
        result = load_skill("blender-asset-source", "search_assets").main(
            source="asset_library", query="registered_asset_probe", asset_types=["obj"]
        )
        assert result["success"], result
        context = result["context"]
        assert context["asset_library_status"] in {"scanned", "partial"}
        if context["asset_library_status"] == "partial":
            assert context["warnings"]
        descriptor = next(item for item in context["descriptors"] if item["metadata"]["library_name"] == library.name)
        assert descriptor["source"] == "asset_library"
        assert descriptor["name"] == fixture.stem
        assert descriptor["size_bytes"] == fixture.stat().st_size
    finally:
        index = next(index for index, item in enumerate(libraries) if item.as_pointer() == library.as_pointer())
        assert bpy.ops.preferences.asset_library_remove(index=index) == {"FINISHED"}
    assert [(library.name, library.path) for library in libraries] == before
