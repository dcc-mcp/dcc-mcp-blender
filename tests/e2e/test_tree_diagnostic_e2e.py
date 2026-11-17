"""Native tree diagnostics collected by every supported Blender CI host."""

import json
import struct
import sys
import time
import types
import zlib
from pathlib import Path

import pytest

bpy = pytest.importorskip("bpy")

from dcc_mcp_blender import _tree_diagnostic_ops as diagnostics  # noqa: E402


@pytest.fixture
def tree_host():
    """Give this test a fresh adapter lifecycle after earlier server-stop tests."""
    from dcc_mcp_blender.server import BlenderMcpServer

    server = BlenderMcpServer(port=0)
    yield server
    server.stop()


def _write_alpha(path, opaque=False):
    """Public synthetic RGB PNG fixture with two disconnected opaque strips."""

    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))

    raw = bytearray()
    for y in range(32):
        raw.append(0)
        for x in range(32):
            value = 255 if opaque or (4 <= y < 28 and (4 <= x < 12 or 20 <= x < 28)) else 0
            raw.extend([value] * 3)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 32, 32, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def _channel(path, channel):
    """Read actual Blender-decoded pixels without an optional imaging package."""
    image = bpy.data.images.load(str(path), check_existing=False)
    try:
        assert tuple(image.size) == (128, 128)
        return [round(value * 255) for value in image.pixels[:][channel::4]]
    finally:
        bpy.data.images.remove(image)


@pytest.mark.e2e
def test_real_blender_worker_generates_images(tmp_path, monkeypatch, tree_host):
    binary = bpy.app.binary_path
    monkeypatch.setitem(
        sys.modules,
        "bpy",
        types.SimpleNamespace(app=types.SimpleNamespace(binary_path=binary, version=bpy.app.version)),
    )
    obj = tmp_path / "tree.obj"
    _write_alpha(tmp_path / "alpha.png")
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
    if not result["success"]:
        print(json.dumps(result, indent=2))
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
    close = _channel(Path(result["context"]["job_directory"]) / "card_closeup.png", 3)
    assert max(close) > 0 and min(close) == 0
    masked_front = _channel(Path(result["context"]["job_directory"]) / "full_front_mask.png", 0)
    _write_alpha(tmp_path / "alpha.png", opaque=True)
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
    opaque_dir = Path(comparison["context"]["job_directory"])
    opaque_close = _channel(opaque_dir / "card_closeup.png", 3)
    opaque_front = _channel(opaque_dir / "full_front_mask.png", 0)
    # The same geometry and camera with white alpha must show many more pixels
    # than the two opaque strips in the first image. Background pixels and edge
    # antialiasing alone cannot satisfy this comparison.
    assert sum(b - a > 32 for a, b in zip(close, opaque_close)) > 200
    assert sum(b - a > 32 for a, b in zip(masked_front, opaque_front)) > 100
    path = Path(result["context"]["job_directory"]) / "full_front.png"
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
    directory = Path(rejected["context"]["job_directory"])
    assert "missing.mtl" in (directory / "stderr.log").read_text(encoding="utf-8", errors="replace")
    assert not list(directory.glob("*.png"))
