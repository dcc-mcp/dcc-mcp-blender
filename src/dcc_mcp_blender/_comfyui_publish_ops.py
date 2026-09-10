"""Publish Blender geometry for official ComfyUI and optional DCC sync."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

from dcc_mcp_blender._interchange_ops import export_gltf

_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def publish_comfyui_asset(
    export_root: str,
    asset_name: str,
    object_names: Sequence[str] | None = None,
    options: Mapping[str, Any] | None = None,
) -> dict:
    """Export a verified GLB revision consumable by official ComfyUI."""
    slug = _UNSAFE_NAME.sub("-", asset_name.strip()).strip(".-")[:96]
    if not slug:
        return skill_error("Invalid asset_name", "asset_name must contain a letter, number, dot, dash, or underscore.")
    if isinstance(object_names, (str, bytes)):
        return skill_error("Invalid object_names", "object_names must be an array of Blender object names.")
    try:
        root = Path(export_root).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        target = (root / f"{slug}.glb").resolve()
        if target.parent != root:
            return skill_error("Invalid export target", "The resolved asset path must remain inside export_root.")

        export_options = dict(options or {})
        export_options["export_format"] = "GLB"
        result = export_gltf(str(target), object_names=object_names, options=export_options)
        if not result.get("success"):
            return result
        if not target.is_file() or target.stat().st_size <= 0:
            return skill_error("GLB export verification failed", f"Expected a non-empty export at {target}.")

        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        revision = digest[:16]
        descriptor = {
            "asset_id": f"blender/{slug}/{revision}",
            "up_axis": "z",
            "unit_hint": "meter",
            "meters_per_unit": 1.0,
            "variants": [{"local_path": str(target), "format": "glb", "preferred": True, "mime": "model/gltf-binary"}],
            "tags": ["blender", "comfyui", "3d"],
            "extra": {
                "display_name": asset_name.strip(),
                "producer": "dcc-mcp-blender",
                "sha256": digest,
                "revision": revision,
                "object_names": list(object_names or []),
            },
        }
        manifest_path = target.with_suffix(".dcc-mcp.json")
        temporary = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
        temporary.write_text(json.dumps(descriptor, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(manifest_path)
        return skill_success(
            f"Published Blender asset for ComfyUI: {target}",
            filepath=str(target),
            manifest_path=str(manifest_path),
            sha256=digest,
            revision=revision,
            descriptor=descriptor,
            official_comfyui_ready=True,
            sync_extension_required=False,
            prompt=(
                "Use the official ComfyUI upload/workflow path with filepath, or call "
                "comfyui-workflow stage_3d_asset for optional latest-revision sync."
            ),
        )
    except Exception as exc:
        return skill_exception(exc, message="Failed to publish Blender asset for ComfyUI")


__all__ = ["publish_comfyui_asset"]
