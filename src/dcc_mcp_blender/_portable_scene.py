"""Publish a bounded self-contained native scene copy with audited path metadata."""

from __future__ import annotations

import hashlib
import os
import re
import stat
import tempfile
from pathlib import Path

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success
from dcc_mcp_core.skills_helper import check_dcc_cancelled


def _safe_destination(filepath, allowed_output_root, extensions=(".blend",)):
    root = Path(allowed_output_root).absolute()
    target = Path(filepath).absolute()
    for path in (root, target.parent, target):
        for component in [path, *path.parents]:
            try:
                attributes = getattr(component.lstat(), "st_file_attributes", 0)
            except FileNotFoundError:
                attributes = 0
            if component.is_symlink() or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
                raise ValueError("Output paths cannot contain symlinks or reparse points")
    root = root.resolve(strict=True)
    if not root.is_dir() or not target.parent.is_dir() or root not in target.resolve().parents:
        raise ValueError("Select a file in the explicitly authorized existing output root")
    if target.suffix.lower() not in extensions or target.exists():
        raise ValueError("Select a new supported output file; existing files are never overwritten")
    return target


def _relative_render_path(value):
    if not isinstance(value, str) or not value.startswith("//") or "\\" in value:
        raise ValueError("Use an explicit Blender-relative render path beginning //")
    pieces = value[2:].split("/")
    if any(not p or p in {".", ".."} or re.fullmatch(r"[A-Za-z0-9_.-]+", p) is None for p in pieces):
        raise ValueError("Render path must have bounded plain relative components")
    if len(value) > 240:
        raise ValueError("Render path is too long")
    return value


def _path_audit(data):
    """Conservative printable-path scan, not an arbitrary-content secret scanner."""
    matches = []
    for value in re.findall(rb"[\x20-\x7e]{5,}", data):
        text = value.decode("ascii")
        if re.search(
            r"(?:/workspace/|rkspace/|dcc-showcase-production/|/home/|/Users/|/tmp/|/private/|[A-Za-z]:[\\/]|file://|https?://)",
            text,
        ):
            matches.append(text)
    return matches


def _set_clean_native_string(owner, name, value):
    """Clear stale native C-buffer contents through its bounded RNA setter."""
    maximum = owner.bl_rna.properties[name].length_max
    if type(maximum) is not int or not len(value) < maximum <= 65536:
        raise ValueError("Unrecognized native path buffer bound")
    neutral = b"~" if isinstance(value, bytes) else "~"
    setattr(owner, name, neutral * (maximum - 1))
    setattr(owner, name, value)


def _clear_browser_directory(params):
    _set_clean_native_string(params, "directory", b"//")


def save_portable_scene_copy(filepath, allowed_output_root, render_path="//renders/hero.png"):
    """Save a new audited copy of a self-contained scene without changing its source."""
    restored = []
    previous_render = None
    try:
        target = _safe_destination(filepath, allowed_output_root)
        render_path = _relative_render_path(render_path)
        import bpy

        for group in ("libraries", "texts", "movieclips", "sounds", "volumes", "cache_files"):
            if len(getattr(bpy.data, group, ())):
                return skill_error(
                    "Scene is outside the self-contained export profile", f"Unsupported data group: {group}"
                )
        for image in bpy.data.images:
            if image.source not in {"FILE", "GENERATED", "VIEWER"}:
                return skill_error(
                    "Image needs a separate dependency audit", "Movie and sequence images are unsupported"
                )
            if image.source == "FILE" and image.filepath and not image.packed_file:
                return skill_error("External image is not packed", "Resolve image dependencies with typed tools first")
        for font in getattr(bpy.data, "fonts", ()):
            if font.filepath != "<builtin>" or font.library is not None:
                return skill_error("External font requires a separate audit", "Only built-in fonts are supported")
        for obj in bpy.data.objects:
            if any(
                m.type not in {"BEVEL", "SUBSURF", "SOLIDIFY", "WEIGHTED_NORMAL", "TRIANGULATE"} for m in obj.modifiers
            ):
                return skill_error(
                    "Modifier needs a separate dependency audit",
                    "This export profile accepts only simple self-contained modifiers",
                )
            if getattr(getattr(obj, "animation_data", None), "drivers", None):
                return skill_error(
                    "Drivers require a separate audit", "Only native keyframes are covered by this export profile"
                )
        for saved_scene in getattr(bpy.data, "scenes", ()):
            if saved_scene.sequence_editor is not None:
                return skill_error(
                    "Sequencer requires a separate dependency audit", "Sequence editors are outside this export profile"
                )
        node_trees = list(getattr(bpy.data, "node_groups", ()))
        for group in ("materials", "worlds", "lights"):
            for owner in getattr(bpy.data, group, ()):
                if getattr(owner, "node_tree", None) is not None:
                    node_trees.append(owner.node_tree)
        if any(node.type in {"SCRIPT", "TEX_IES"} for tree in node_trees for node in tree.nodes):
            return skill_error(
                "External shader dependency requires a separate audit",
                "Script and IES nodes are outside this export profile",
            )
        scene = bpy.context.scene
        previous_render = scene.render.filepath
        check_dcc_cancelled()
        _set_clean_native_string(scene.render, "filepath", render_path)
        for screen in bpy.data.screens:
            for area in screen.areas:
                for space in area.spaces:
                    if space.type == "FILE_BROWSER" and getattr(space, "params", None) is not None:
                        params = space.params
                        restored.append((params, params.directory))
                        # RNA writes may retain bytes beyond the new NUL terminator.
                        # Fill the bounded native buffer before shortening it, so
                        # no prior directory text is serialized as padding.
                        _clear_browser_directory(params)
        with tempfile.TemporaryDirectory(prefix=".blend-publish-", dir=str(target.parent)) as directory:
            staged = Path(directory) / "scene.blend"
            check_dcc_cancelled()
            bpy.ops.wm.save_as_mainfile(
                filepath=str(staged), copy=True, compress=False, check_existing=False, relative_remap=False
            )
            if staged.stat().st_size > 256 * 1024 * 1024:
                raise ValueError("Native scene exceeds the 256 MiB publication limit")
            data = staged.read_bytes()
            if not data.startswith(b"BLENDER"):
                raise ValueError("Expected an uncompressed native scene within the 256 MiB bound")
            leaks = _path_audit(data)
            if leaks:
                return skill_error(
                    "Native path audit did not pass", "No public copy was published", path_match_count=len(leaks)
                )
            check_dcc_cancelled()
            os.link(staged, target)
        return skill_success(
            "New native scene copy saved and path-audited",
            path=str(target),
            bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            browser_directories_sanitized=len(restored),
            render_path=render_path,
            scope="Self-contained scene; render path and file-browser directory metadata",
            not_claimed=[
                "comprehensive secret detection",
                "arbitrary scene sanitization",
                "native reopen or render acceptance",
            ],
        )
    except Exception as exc:
        return skill_exception(exc, message="Native scene copy was not published")
    finally:
        if previous_render is not None:
            bpy.context.scene.render.filepath = previous_render
        for params, directory in restored:
            params.directory = directory
