"""Validate a Blender scene for render farm submission."""

# Import future modules
from __future__ import annotations

# Import built-in modules
import os

# Import local modules
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def validate_scene_for_farm() -> dict:
    """Check the open Blender scene for common farm-submission issues.

    Checks performed:
    - Scene is saved (not untitled)
    - Active camera exists
    - Render frame range is valid (start < end)
    - Output path is set
    - No missing external files (textures, linked libraries, etc.)

    Returns:
        ToolResult dict with ``context.issues`` list and ``context.valid`` flag.
    """

    try:
        import bpy  # noqa: PLC0415

        issues = []  # type: List[str]

        # 1. Scene is saved
        scene_path = bpy.data.filepath or ""
        if not scene_path:
            issues.append("Scene is unsaved (untitled) — save before submitting")

        # 2. Active camera
        scene = bpy.context.scene
        if not scene.camera:
            issues.append("No active camera found — set a camera before submitting")

        # 3. Render frame range
        start = scene.frame_start
        end = scene.frame_end
        if end <= start:
            issues.append("Render frame range invalid: frame_start={} frame_end={}".format(start, end))

        # 4. Output path
        output_path = scene.render.filepath or ""
        if not output_path:
            issues.append("No render output path set")

        # 5. Missing external files
        if hasattr(bpy.data, "images"):
            for img in bpy.data.images:
                if img.filepath and not img.packed_file:
                    abs_path = img.filepath_from_user()
                    if abs_path and not os.path.isfile(abs_path):
                        issues.append("Missing image file: '{}' on image '{}'".format(img.filepath, img.name))

        # 6. Missing linked libraries
        if hasattr(bpy.data, "libraries"):
            for lib in bpy.data.libraries:
                if lib.filepath and not os.path.isfile(lib.filepath):
                    issues.append("Missing library: '{}' (name: {})".format(lib.filepath, lib.name))

        valid = len(issues) == 0
        if valid:
            return skill_success(
                "Scene is valid for farm submission",
                prompt="Use write_render_job to create a job spec for the render farm.",
                valid=True,
                issues=[],
                scene_path=scene_path,
            )
        else:
            return skill_success(
                "Scene has {} issue(s) that should be resolved before submission".format(len(issues)),
                prompt="Fix the listed issues, then re-run validate_scene_for_farm.",
                valid=False,
                issues=issues,
                scene_path=scene_path,
            )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to validate scene")


@skill_entry
def main(**kwargs):
    return validate_scene_for_farm(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
