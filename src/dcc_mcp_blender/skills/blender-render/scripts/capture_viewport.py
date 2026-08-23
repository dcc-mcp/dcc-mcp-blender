"""Capture the active Blender viewport to an image file."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _view3d_override(context):
    """Return a complete VIEW_3D operator context without changing UI state."""
    current_window = getattr(context, "window", None)
    windows = []
    if current_window is not None:
        windows.append(current_window)
    window_manager = getattr(context, "window_manager", None)
    for window in getattr(window_manager, "windows", ()) if window_manager is not None else ():
        windows.append(window)

    for window in windows:
        screen = getattr(window, "screen", None)
        for area in getattr(screen, "areas", ()) if screen is not None else ():
            if getattr(area, "type", None) != "VIEW_3D":
                continue
            region = next(
                (
                    candidate
                    for candidate in getattr(area, "regions", ())
                    if getattr(candidate, "type", None) == "WINDOW"
                ),
                None,
            )
            if region is None:
                continue
            spaces = getattr(area, "spaces", None)
            space = getattr(spaces, "active", None)
            if space is None or getattr(space, "type", "VIEW_3D") != "VIEW_3D":
                continue
            return {
                "window": window,
                "screen": screen,
                "area": area,
                "region": region,
                "space_data": space,
            }
    return None


def _image_format(filepath: str, current: str) -> str:
    formats = {
        ".bmp": "BMP",
        ".exr": "OPEN_EXR",
        ".jpeg": "JPEG",
        ".jpg": "JPEG",
        ".png": "PNG",
        ".tga": "TARGA",
        ".tif": "TIFF",
        ".tiff": "TIFF",
    }
    return formats.get(Path(filepath).suffix.lower(), current)


def _output_dimensions(bpy, filepath: str) -> tuple[int, int]:
    image = None
    try:
        image = bpy.data.images.load(filepath, check_existing=False)
        if image is None:
            raise RuntimeError("Blender could not load the viewport output")
        return int(image.size[0]), int(image.size[1])
    finally:
        if image is not None:
            bpy.data.images.remove(image)


def capture_viewport(
    filepath: str,
    resolution_x: Optional[int] = None,
    resolution_y: Optional[int] = None,
) -> dict:
    """Capture the active viewport.

    Args:
        filepath: Destination image path.
        resolution_x: Optional temporary output width.
        resolution_y: Optional temporary output height.

    Returns:
        ActionResultModel dict with the written filepath.
    """
    try:
        import bpy

        if not filepath:
            return skill_error("Missing filepath", "Provide a filepath for the viewport image.")

        override = _view3d_override(bpy.context)
        if override is None:
            return skill_error(
                "VIEW_3D context unavailable",
                "Open a Blender 3D Viewport and retry; no full-window screenshot fallback is used.",
            )
        temp_override = getattr(bpy.context, "temp_override", None)
        if not callable(temp_override):
            return skill_error(
                "VIEW_3D context override unavailable",
                "This Blender runtime cannot safely isolate a 3D Viewport capture.",
            )

        scene = bpy.context.scene
        old_filepath = scene.render.filepath
        old_x = scene.render.resolution_x
        old_y = scene.render.resolution_y
        old_percentage = scene.render.resolution_percentage
        old_format = scene.render.image_settings.file_format
        old_use_extension = scene.render.use_file_extension

        percentage = max(1, int(old_percentage))
        current_x = max(1, int(old_x) * percentage // 100)
        current_y = max(1, int(old_y) * percentage // 100)
        target_x = int(resolution_x) if resolution_x is not None else current_x
        target_y = int(resolution_y) if resolution_y is not None else current_y
        if target_x < 1 or target_y < 1:
            return skill_error(
                "Invalid viewport resolution",
                "resolution_x and resolution_y must each be at least 1 pixel.",
            )

        try:
            scene.render.filepath = filepath
            scene.render.resolution_x = target_x
            scene.render.resolution_y = target_y
            scene.render.resolution_percentage = 100
            scene.render.image_settings.file_format = _image_format(filepath, old_format)
            scene.render.use_file_extension = False

            with temp_override(**override):
                if not bpy.ops.render.opengl.poll():
                    raise RuntimeError("OpenGL viewport render is unavailable in the selected VIEW_3D")
                operator_result = bpy.ops.render.opengl(write_still=True, view_context=True)
            if "FINISHED" not in operator_result:
                raise RuntimeError(
                    f"OpenGL viewport render did not finish (operator result: {sorted(operator_result)})"
                )
            width, height = _output_dimensions(bpy, filepath)
            if (width, height) != (target_x, target_y):
                raise RuntimeError(
                    f"Viewport output dimensions {width}x{height} do not match requested {target_x}x{target_y}"
                )
        finally:
            scene.render.filepath = old_filepath
            scene.render.resolution_x = old_x
            scene.render.resolution_y = old_y
            scene.render.resolution_percentage = old_percentage
            scene.render.image_settings.file_format = old_format
            scene.render.use_file_extension = old_use_extension

        return skill_success(
            "Viewport captured",
            filepath=filepath,
            method="viewport_opengl",
            width=width,
            height=height,
            prompt="Viewport image saved. Use the file path to inspect the current view.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(
            exc,
            message=f"Failed to capture viewport: {exc}",
            possible_solutions=["Ensure a non-temporary VIEW_3D area is available, then retry."],
            failure_stage="viewport_capture",
            method="viewport_opengl",
        )


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`capture_viewport`."""
    return capture_viewport(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
