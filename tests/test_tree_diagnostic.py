import json
import os
import sys
import time
import types

import pytest

from dcc_mcp_blender import _tree_diagnostic_ops as diagnostics


def test_reject_missing_mapping(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "bpy", types.SimpleNamespace())
    obj = tmp_path / "tree.obj"
    obj.write_text("# fixture", encoding="utf-8")
    result = diagnostics.start_tree_diagnostic(str(obj), str(tmp_path), {"wood": "wood"})
    assert not result["success"]
    assert not list(tmp_path.glob("tree-diagnostic-*"))


def test_reject_unknown_job():
    assert not diagnostics.get_tree_diagnostic("not-owned")["success"]
    assert not diagnostics.cancel_tree_diagnostic("not-owned")["success"]


@pytest.mark.e2e
def test_real_blender_worker_generates_images(tmp_path, monkeypatch):
    binary = os.environ.get("BLENDER_EXECUTABLE")
    if not binary:
        pytest.skip("Set BLENDER_EXECUTABLE to an installed Blender")
    monkeypatch.setitem(
        sys.modules, "bpy", types.SimpleNamespace(app=types.SimpleNamespace(binary_path=binary, version=(5, 1, 0)))
    )
    obj = tmp_path / "tree.obj"
    obj.write_text(
        "mtllib tree.mtl\nv 0 0 0\nv 1 0 0\nv 0 0 1\nv 0 0 2\n"
        "v 2 0 2\nv 2 0 4\nv 0 0 4\nusemtl Wood\nf 1 2 3\n"
        "usemtl Card\nf 4 5 6 7\n",
        encoding="utf-8",
    )
    (tmp_path / "tree.mtl").write_text("newmtl Wood\nKd .3 .2 .1\nnewmtl Card\nKd .1 .7 .1\n", encoding="utf-8")
    result = diagnostics.start_tree_diagnostic(str(obj), str(tmp_path), {"Wood": "wood", "Card": "card"}, 128)
    assert result["success"], result
    job = result["context"]["job_id"]
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        result = diagnostics.get_tree_diagnostic(job)
        if not result["success"] or result["context"]["status"] != "running":
            break
        time.sleep(0.1)
    assert result["success"] and result["context"]["status"] == "completed", result
    manifest = json.loads(open(result["context"]["manifest_path"], encoding="utf-8").read())
    assert len(manifest["images"]) == 17
    assert set(manifest["cameras"]) == {"front", "back", "left", "right"}
    assert any("transparency" in warning for warning in manifest["warnings"])
    path = tmp_path / ("tree-diagnostic-" + job) / "full_front.png"
    path.write_bytes(b"tampered")
    assert not diagnostics.get_tree_diagnostic(job)["success"]
