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


@pytest.mark.parametrize("timeout", [False, True])
def test_owned_worker_cancellation_and_timeout(tmp_path, monkeypatch, timeout):
    class Process:
        returncode = None
        terminated = False

        def poll(self):
            return self.returncode

        def terminate(self):
            self.terminated = True
            self.returncode = -1

        def wait(self, timeout=None):
            return self.returncode

    process = Process()
    obj = tmp_path / "source.obj"
    obj.write_text("# fixture", encoding="utf-8")
    binary = tmp_path / "blender.exe"
    binary.write_text("fixture", encoding="utf-8")
    monkeypatch.setitem(
        sys.modules, "bpy", types.SimpleNamespace(app=types.SimpleNamespace(binary_path=str(binary), version=(5, 1, 0)))
    )
    monkeypatch.setattr(diagnostics.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(diagnostics, "_TIMEOUT_SECONDS", 0.05 if timeout else 30)
    result = diagnostics.start_tree_diagnostic(str(obj), str(tmp_path), {"Wood": "wood", "Card": "card"})
    assert result["success"]
    job = result["context"]["job_id"]
    if timeout:
        for _ in range(100):
            if process.terminated:
                break
            time.sleep(0.01)
        state = diagnostics.get_tree_diagnostic(job)
        assert not state["success"] and state["context"]["status"] == "timed_out"
    else:
        assert diagnostics.cancel_tree_diagnostic(job)["context"]["cancellation_requested"]
        assert diagnostics.get_tree_diagnostic(job)["context"]["status"] == "cancelled"
    assert process.terminated


@pytest.mark.e2e
def test_real_blender_worker_generates_images(tmp_path, monkeypatch):
    binary = os.environ.get("BLENDER_EXECUTABLE")
    if not binary:
        pytest.skip("Set BLENDER_EXECUTABLE to an installed Blender")
    monkeypatch.setitem(
        sys.modules, "bpy", types.SimpleNamespace(app=types.SimpleNamespace(binary_path=binary, version=(5, 1, 0)))
    )
    obj = tmp_path / "tree.obj"
    image_module = pytest.importorskip("PIL.Image")
    image = image_module.new("RGB", (32, 32), "black")
    for x in range(4, 12):
        for y in range(4, 28):
            image.putpixel((x, y), (255, 255, 255))
    for x in range(20, 28):
        for y in range(4, 28):
            image.putpixel((x, y), (255, 255, 255))
    image.save(tmp_path / "alpha.png")
    obj.write_text(
        "  mtllib wood.mtl card.mtl\nv 0 0 0\nv 1 0 0\nv 0 0 1\nv 0 0 2\n"
        "v 2 0 2\nv 2 0 4\nv 0 0 4\nvt 0 0\nvt 1 0\nvt 1 1\nvt 0 1\n"
        "usemtl Wood\nf 1 2 3\nusemtl Card\nf 4/1 5/2 6/3 7/4\n",
        encoding="utf-8",
    )
    (tmp_path / "wood.mtl").write_text("newmtl Wood\nKd .3 .2 .1\n", encoding="utf-8")
    (tmp_path / "card.mtl").write_text("newmtl Card\nKd .1 .7 .1\nmap_d alpha.png\n", encoding="utf-8")
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
    assert len(manifest["material_libraries"]) == 2
    assert manifest["render_settings"]["resolution_x"] == 128
    assert all(len(view["transform"]["matrix_world"]) == 4 for view in manifest["cameras"].values())
    assert manifest["card_closeup"]["transform"]["clip_end"] > 0
    assert len(manifest["lights"]) == 2
    assert any(t["path"].endswith("alpha.png") for t in manifest["textures"])
    assert not any("no MTL map_d" in warning for warning in manifest["warnings"])
    close = image_module.open(tmp_path / ("tree-diagnostic-" + job) / "card_closeup.png").getchannel("A")
    bounds = close.getbbox()
    assert bounds is not None
    cropped = close.crop(bounds)
    assert cropped.getextrema()[0] == 0 and cropped.getextrema()[1] > 0
    masked_front = image_module.open(tmp_path / ("tree-diagnostic-" + job) / "full_front_mask.png").convert("L")
    opaque = image_module.new("RGB", (32, 32), "white")
    opaque.save(tmp_path / "alpha.png")
    comparison = diagnostics.start_tree_diagnostic(str(obj), str(tmp_path), {"Wood": "wood", "Card": "card"}, 128)
    assert comparison["success"]
    opaque_job = comparison["context"]["job_id"]
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        state = diagnostics.get_tree_diagnostic(opaque_job)
        if not state["success"] or state["context"]["status"] != "running":
            break
        time.sleep(0.1)
    assert state["success"] and state["context"]["status"] == "completed", state
    opaque_dir = tmp_path / ("tree-diagnostic-" + opaque_job)
    opaque_close = image_module.open(opaque_dir / "card_closeup.png").getchannel("A")
    opaque_front = image_module.open(opaque_dir / "full_front_mask.png").convert("L")
    # The same geometry and camera with white alpha must show many more pixels
    # than the two opaque strips in the first image. Background pixels and edge
    # antialiasing alone cannot satisfy this comparison.
    assert sum(b - a > 32 for a, b in zip(close.tobytes(), opaque_close.tobytes())) > 200
    assert sum(b - a > 32 for a, b in zip(masked_front.tobytes(), opaque_front.tobytes())) > 100
    path = tmp_path / ("tree-diagnostic-" + job) / "full_front.png"
    path.write_bytes(b"tampered")
    assert not diagnostics.get_tree_diagnostic(job)["success"]

    missing = tmp_path / "missing.obj"
    missing.write_text(obj.read_text(encoding="utf-8").replace("card.mtl", "missing.mtl"), encoding="utf-8")
    rejected = diagnostics.start_tree_diagnostic(str(missing), str(tmp_path), {"Wood": "wood", "Card": "card"}, 128)
    assert rejected["success"]
    job2 = rejected["context"]["job_id"]
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        state = diagnostics.get_tree_diagnostic(job2)
        if not state["success"] or state["context"]["status"] != "running":
            break
        time.sleep(0.1)
    assert not state["success"]
    directory = tmp_path / ("tree-diagnostic-" + job2)
    assert "missing.mtl" in (directory / "stderr.log").read_text(encoding="utf-8", errors="replace")
    assert not list(directory.glob("*.png"))
