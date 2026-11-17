"""Tree-specific artifact verification, independent of job supervision."""

from __future__ import annotations

import json
from pathlib import Path

from dcc_mcp_blender._render_worker_receipt import file_hash


def verify_tree_preview(directory):
    directory = Path(directory)
    request = json.loads((directory / "request.json").read_text(encoding="utf-8"))
    manifest_path = directory / "preview-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_hash = request["source_sha256"]
    if file_hash(request["obj"]) != source_hash or manifest["source"]["sha256"] != source_hash:
        raise ValueError("OBJ changed during the diagnostic job")
    expected = {
        "{}_{}{}.png".format(kind, view, suffix)
        for kind in ("full", "bare")
        for view in ("front", "back", "left", "right")
        for suffix in ("", "_mask")
    }
    expected.add("card_closeup.png")
    if set(manifest["images"]) != expected:
        raise ValueError("Diagnostic image set is incomplete")
    for name, digest in manifest["images"].items():
        if file_hash(directory / name) != digest:
            raise ValueError("Diagnostic image hash mismatch: " + name)
    return str(manifest_path)
