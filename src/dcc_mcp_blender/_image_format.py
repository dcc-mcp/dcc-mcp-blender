"""Image output compatibility across Blender's media-type API transition."""

from __future__ import annotations

from typing import Any

MULTILAYER_EXR = "OPEN_EXR_MULTILAYER"


def media_type_for_format(file_format: str) -> str:
    if file_format == MULTILAYER_EXR:
        return "MULTI_LAYER_IMAGE"
    return "VIDEO" if file_format == "FFMPEG" else "IMAGE"


def set_image_format(settings: Any, file_format: str) -> None:
    """Set media type before the dynamically filtered file-format enum.

    Blender versions without media_type retain their original format API.
    This function never silently substitutes another output container.
    """
    name = str(file_format).strip().upper()
    previous_format = settings.file_format
    previous_media = getattr(settings, "media_type", None)
    try:
        if previous_media is not None:
            settings.media_type = media_type_for_format(name)
        settings.file_format = name
    except Exception:
        # Switching media may reset the format before the format setter rejects
        # an unavailable container. Restore the original pair in dependency order.
        if previous_media is not None:
            settings.media_type = previous_media
        settings.file_format = previous_format
        raise


def image_format(settings: Any) -> str:
    """Read the actual container, including the new multi-layer media type."""
    if getattr(settings, "media_type", None) == "MULTI_LAYER_IMAGE":
        return MULTILAYER_EXR
    return str(getattr(settings, "file_format", "")).strip().upper()


def worker_format_expression(file_format: str) -> str:
    """Build a small native worker expression independent of adapter imports."""
    name = str(file_format).strip().upper()
    # The worker owns no adapter environment. Use only Blender's native RNA,
    # with data literals so a format string cannot inject executable Python.
    return (
        "import bpy\n"
        "_dcc_output_settings = bpy.context.scene.render.image_settings\n"
        "if hasattr(_dcc_output_settings, 'media_type'):\n"
        "    _dcc_output_settings.media_type = {!r}\n"
        "_dcc_output_settings.file_format = {!r}\n"
    ).format(media_type_for_format(name), name)
