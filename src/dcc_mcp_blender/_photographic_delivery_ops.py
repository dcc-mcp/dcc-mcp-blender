"""Photographic video delivery and native Blender FFmpeg configuration."""

from __future__ import annotations

import math
import subprocess
from pathlib import Path
from typing import Any

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

from dcc_mcp_blender._image_format import set_image_format

VIDEO_VERSION = "dcc-mcp-blender.photographic-delivery.v1"
VIDEO_FPS = 24
VIDEO_CRF = 15
VIDEO_PIXEL_FORMAT = "yuv420p"
VIDEO_COLOR_SPACE = "bt709"


def _resolve_scene(bpy: Any, scene_name: str | None) -> tuple[Any | None, dict | None]:
    if scene_name:
        scene = bpy.data.scenes.get(str(scene_name))
        if scene is None:
            return None, skill_error(f"Scene not found: {scene_name}", f"No scene named '{scene_name}'.")
        return scene, None
    scene = getattr(bpy.context, "scene", None)
    if scene is None:
        return None, skill_error("No active scene", "bpy.context.scene is unavailable.")
    return scene, None


def _finite_integer(value: Any, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return int(value)


def _path(value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValueError(f"{label} must be a non-empty local filesystem path")
    if "://" in value:
        raise ValueError(f"{label} must be a local filesystem path")
    return Path(value).expanduser().resolve()


def _set_property(scene: Any, key: str, value: Any) -> None:
    scene[key] = value


def _get_property(scene: Any, key: str, default: Any = None) -> Any:
    getter = getattr(scene, "get", None)
    return getter(key, default) if callable(getter) else default


def configure_photographic_video_output(
    filepath: str,
    scene_name: str | None = None,
    overwrite: bool = True,
) -> dict:
    """Configure Blender's native FFmpeg output for the photographic contract."""
    try:
        output_path = _path(filepath, "filepath")
        if not isinstance(overwrite, bool):
            raise ValueError("overwrite must be a boolean")

        import bpy

        scene, error = _resolve_scene(bpy, scene_name)
        if error:
            return error
        render = scene.render
        settings = render.image_settings
        ffmpeg = getattr(render, "ffmpeg", None)
        if ffmpeg is None:
            return skill_error("FFmpeg settings unavailable", "The Blender build does not expose scene.render.ffmpeg.")
        required = [
            (settings, "media_type", "scene.render.image_settings.media_type"),
            (settings, "file_format", "scene.render.image_settings.file_format"),
            (render, "fps", "scene.render.fps"),
            (render, "fps_base", "scene.render.fps_base"),
            (render, "filepath", "scene.render.filepath"),
            (ffmpeg, "format", "scene.render.ffmpeg.format"),
            (ffmpeg, "codec", "scene.render.ffmpeg.codec"),
            (ffmpeg, "constant_rate_factor", "scene.render.ffmpeg.constant_rate_factor"),
            (ffmpeg, "custom_constant_rate_factor", "scene.render.ffmpeg.custom_constant_rate_factor"),
        ]
        missing = [path for owner, attribute, path in required if not hasattr(owner, attribute)]
        if missing:
            return skill_error(
                "Photographic video output unavailable",
                "The Blender build does not expose: " + ", ".join(missing),
                unsupported_properties=missing,
            )
        snapshot = [
            (render, "filepath", render.filepath),
            (render, "fps", render.fps),
            (render, "fps_base", render.fps_base),
            (settings, "media_type", settings.media_type),
            (settings, "file_format", settings.file_format),
            (render, "use_file_extension", getattr(render, "use_file_extension", None)),
            (render, "use_overwrite", getattr(render, "use_overwrite", None)),
            (ffmpeg, "format", ffmpeg.format),
            (ffmpeg, "codec", ffmpeg.codec),
            (ffmpeg, "constant_rate_factor", ffmpeg.constant_rate_factor),
            (ffmpeg, "custom_constant_rate_factor", ffmpeg.custom_constant_rate_factor),
        ]
        try:
            render.filepath = str(output_path)
            render.fps = VIDEO_FPS
            render.fps_base = 1.0
            set_image_format(settings, "FFMPEG")
            ffmpeg.format = "MPEG4"
            ffmpeg.codec = "H264"
            ffmpeg.constant_rate_factor = "CUSTOM"
            ffmpeg.custom_constant_rate_factor = VIDEO_CRF
            if hasattr(render, "use_file_extension"):
                render.use_file_extension = True
            if hasattr(render, "use_overwrite"):
                render.use_overwrite = overwrite
        except Exception as exc:
            for owner, attribute, value in reversed(snapshot):
                if value is not None:
                    try:
                        setattr(owner, attribute, value)
                    except Exception:
                        pass
            return skill_error("Photographic video output failed", str(exc))

        _set_property(scene, "dcc_mcp_photographic_video_contract", VIDEO_VERSION)
        _set_property(scene, "dcc_mcp_photographic_video_pixel_format", VIDEO_PIXEL_FORMAT)
        _set_property(scene, "dcc_mcp_photographic_video_color_space", "BT.709")
        return skill_success(
            "Photographic video output configured",
            video_version=VIDEO_VERSION,
            filepath=str(output_path),
            fps=VIDEO_FPS,
            container="MPEG4",
            codec="H264",
            crf=VIDEO_CRF,
            pixel_format=VIDEO_PIXEL_FORMAT,
            color_space="BT.709",
            native_settings={
                "media_type": getattr(settings, "media_type", None),
                "file_format": getattr(settings, "file_format", None),
                "format": getattr(ffmpeg, "format", None),
                "codec": getattr(ffmpeg, "codec", None),
                "constant_rate_factor": getattr(ffmpeg, "constant_rate_factor", None),
                "custom_constant_rate_factor": getattr(ffmpeg, "custom_constant_rate_factor", None),
            },
            prompt="Render JPEG frames at 24 fps, then use encode_photographic_video for exact yuv420p and BT.709 metadata.",
        )
    except ValueError as exc:
        return skill_error("Invalid photographic video request", str(exc))
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to configure photographic video output")


def validate_photographic_video_output(scene_name: str | None = None) -> dict:
    """Validate native settings and the exact external encoder contract."""
    try:
        import bpy

        scene, error = _resolve_scene(bpy, scene_name)
        if error:
            return error
        render = scene.render
        settings = render.image_settings
        ffmpeg = getattr(render, "ffmpeg", None)
        issues: list[dict[str, Any]] = []
        expected = {
            "media_type": "VIDEO",
            "file_format": "FFMPEG",
            "fps": VIDEO_FPS,
            "fps_base": 1.0,
            "format": "MPEG4",
            "codec": "H264",
            "constant_rate_factor": "CUSTOM",
            "custom_constant_rate_factor": VIDEO_CRF,
        }
        actual = {
            "media_type": getattr(settings, "media_type", None),
            "file_format": getattr(settings, "file_format", None),
            "fps": getattr(render, "fps", None),
            "fps_base": getattr(render, "fps_base", None),
            "format": getattr(ffmpeg, "format", None),
            "codec": getattr(ffmpeg, "codec", None),
            "constant_rate_factor": getattr(ffmpeg, "constant_rate_factor", None),
            "custom_constant_rate_factor": getattr(ffmpeg, "custom_constant_rate_factor", None),
        }
        for field, value in expected.items():
            actual_value = actual.get(field)
            if isinstance(value, float) and isinstance(actual_value, (int, float)):
                matches = math.isclose(float(value), float(actual_value), abs_tol=1e-6)
            else:
                matches = actual_value == value
            if not matches:
                issues.append(
                    {
                        "code": "PHOTO_VIDEO_SETTING_MISMATCH",
                        "severity": "error",
                        "field": field,
                        "expected": value,
                        "actual": actual_value,
                    }
                )
        if _get_property(scene, "dcc_mcp_photographic_video_pixel_format") != VIDEO_PIXEL_FORMAT:
            issues.append(
                {"code": "PHOTO_VIDEO_PIXEL_FORMAT_MISSING", "severity": "error", "expected": VIDEO_PIXEL_FORMAT}
            )
        if _get_property(scene, "dcc_mcp_photographic_video_color_space") != "BT.709":
            issues.append({"code": "PHOTO_VIDEO_COLOR_SPACE_MISSING", "severity": "error", "expected": "BT.709"})
        return skill_success(
            "Photographic video validation completed",
            valid=not issues,
            issues=issues,
            expected=expected,
            actual=actual,
            pixel_format=VIDEO_PIXEL_FORMAT,
            color_space="BT.709",
            encoder_command_contract={
                "codec": "libx264",
                "crf": VIDEO_CRF,
                "pixel_format": VIDEO_PIXEL_FORMAT,
                "colorspace": VIDEO_COLOR_SPACE,
                "color_primaries": VIDEO_COLOR_SPACE,
                "color_trc": VIDEO_COLOR_SPACE,
                "fps": VIDEO_FPS,
            },
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to validate photographic video output")


def _sequence_pattern(pattern: str) -> str:
    if "%" in pattern:
        return pattern
    output: list[str] = []
    index = 0
    while index < len(pattern):
        if pattern[index] != "#":
            output.append(pattern[index])
            index += 1
            continue
        end = index
        while end < len(pattern) and pattern[end] == "#":
            end += 1
        output.append(f"%0{end - index}d")
        index = end
    return "".join(output)


def encode_photographic_video(
    input_pattern: str,
    output_path: str,
    start_frame: int,
    end_frame: int,
    ffmpeg_path: str = "ffmpeg",
    overwrite: bool = False,
    timeout_seconds: int = 3600,
) -> dict:
    """Encode rendered frames with the exact H.264/yuv420p/BT.709 contract."""
    try:
        input_value = _path(input_pattern, "input_pattern")
        output = _path(output_path, "output_path")
        start = _finite_integer(start_frame, "start_frame")
        end = _finite_integer(end_frame, "end_frame")
        if end < start:
            raise ValueError("end_frame must be greater than or equal to start_frame")
        if not isinstance(ffmpeg_path, str) or not ffmpeg_path.strip():
            raise ValueError("ffmpeg_path must be a non-empty executable path")
        timeout = _finite_integer(timeout_seconds, "timeout_seconds", 1)
        pattern = _sequence_pattern(str(input_value))
        output.parent.mkdir(parents=True, exist_ok=True)
        command = [
            ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-framerate",
            str(VIDEO_FPS),
            "-start_number",
            str(start),
            "-i",
            pattern,
            "-frames:v",
            str(end - start + 1),
            "-c:v",
            "libx264",
            "-crf",
            str(VIDEO_CRF),
            "-pix_fmt",
            VIDEO_PIXEL_FORMAT,
            "-colorspace",
            VIDEO_COLOR_SPACE,
            "-color_primaries",
            VIDEO_COLOR_SPACE,
            "-color_trc",
            VIDEO_COLOR_SPACE,
            "-r",
            str(VIDEO_FPS),
            "-an",
        ]
        if overwrite:
            command.append("-y")
        command.append(str(output))
        try:
            completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError:
            return skill_error("FFmpeg unavailable", f"Executable not found: {ffmpeg_path}")
        except subprocess.TimeoutExpired:
            return skill_error("FFmpeg timed out", f"Encoding exceeded {timeout} seconds.", command=command)
        if completed.returncode != 0:
            return skill_error(
                "Photographic video encoding failed",
                (completed.stderr or completed.stdout or "ffmpeg returned a non-zero exit code").strip(),
                return_code=completed.returncode,
                command=command,
            )
        if not output.is_file() or output.stat().st_size <= 0:
            return skill_error("Photographic video output missing", f"FFmpeg did not create {output}.", command=command)
        return skill_success(
            "Photographic video encoded",
            output_path=str(output),
            start_frame=start,
            end_frame=end,
            frame_count=end - start + 1,
            fps=VIDEO_FPS,
            codec="H264",
            crf=VIDEO_CRF,
            pixel_format=VIDEO_PIXEL_FORMAT,
            color_space="BT.709",
            command=command,
        )
    except ValueError as exc:
        return skill_error("Invalid photographic video request", str(exc))
    except Exception as exc:
        return skill_exception(exc, message="Failed to encode photographic video")
