"""Owned background Blender render jobs."""

from __future__ import annotations

import os
import re
import signal
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Tuple

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

_FRAME_TOKEN = re.compile(r"#+")
_OPENEXR_MAGIC = b"\x76\x2f\x31\x01"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_OUTPUT_FORMATS = {
    "OPEN_EXR_MULTILAYER": (".exr", _OPENEXR_MAGIC),
    "OPEN_EXR": (".exr", _OPENEXR_MAGIC),
    "PNG": (".png", _PNG_MAGIC),
}
# Scene ``render.image_settings.file_format`` values that a background worker
# can reproduce. Kept identical to ``_OUTPUT_FORMATS`` on purpose: a scene set
# to plain ``OPEN_EXR`` must stay single-layer instead of silently becoming a
# multi-layer container, and anything else has to fail loudly rather than fall
# back to EXR.
_SCENE_OUTPUT_FORMATS = ("OPEN_EXR_MULTILAYER", "OPEN_EXR", "PNG")
# Cycles device names a worker accepts through ``-- --cycles-device``. Kept as
# the single source of truth for the hint a device failure returns so it cannot
# drift away from the enum published by the skill contract.
_DEVICES = ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL", "CPU")
# Blender's error when ``--cycles-device`` names a device the host cannot
# provide, matched case-insensitively against a worker's log tail: OPTIX on
# macOS (Windows/Linux only) or on any host without an NVIDIA GPU.
_CYCLES_DEVICE_ERROR = "found no cycles device of the specified type"
# Bytes read from the end of each worker log for failure attribution.
_LOG_TAIL_BYTES = 4096
_JOBS: Dict[str, Dict[str, Any]] = {}
_LOCK = threading.Lock()


def _launch_worker(command, directory, stdout_path, stderr_path):
    command = list(command)
    # Blender may report its relative launch path on macOS. Resolve it before
    # Popen switches cwd to the output directory; bare PATH commands stay bare.
    executable = Path(command[0])
    if os.sep in command[0] or (os.altsep and os.altsep in command[0]):
        command[0] = str(executable.resolve())
    env = os.environ.copy()
    env["DCC_MCP_BACKGROUND_RENDER"] = "1"
    popen_kwargs = {"env": env, "cwd": str(directory)}
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    else:
        popen_kwargs["start_new_session"] = True
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        return subprocess.Popen(command, stdout=stdout, stderr=stderr, **popen_kwargs)


def _normalize_output_format(output_format: str) -> str:
    """Return the canonical name of a supported background render format."""
    name = str(output_format).strip().upper()
    if name not in _OUTPUT_FORMATS:
        raise ValueError("output_format must be one of: {}".format(", ".join(sorted(_OUTPUT_FORMATS))))
    return name


def _output_format_spec(output_format: str) -> Tuple[str, bytes]:
    return _OUTPUT_FORMATS[_normalize_output_format(output_format)]


def _scene_file_format() -> str:
    """Read ``render.image_settings.file_format`` from the live scene."""
    import bpy  # Lazy import: requires Blender's embedded Python.

    settings = bpy.context.scene.render.image_settings
    return str(getattr(settings, "file_format", "")).strip().upper()


def _resolve_output_format(output_format: str = None, scene_format: str = None) -> str:
    """Pick the background render format for a job.

    An explicit ``output_format`` always wins. Otherwise the live scene's
    ``render.image_settings.file_format`` is reused, which is what
    ``set_render_settings(file_format=...)`` writes. Scene formats outside
    ``_SCENE_OUTPUT_FORMATS`` raise instead of falling back to EXR, so a
    mis-set scene is reported before a whole frame range is rendered.
    """
    if output_format is not None and str(output_format).strip():
        return _normalize_output_format(output_format)
    name = _scene_file_format() if scene_format is None else str(scene_format).strip().upper()
    if name not in _SCENE_OUTPUT_FORMATS:
        raise ValueError(
            "Scene render format {!r} is not supported by background render jobs. "
            "Set output_format explicitly or change render.image_settings.file_format to one of: {}".format(
                name, ", ".join(_SCENE_OUTPUT_FORMATS)
            )
        )
    return name


def _expected_output_path(
    output_pattern: str,
    frame: int,
    *,
    output_format: str = "OPEN_EXR_MULTILAYER",
) -> Path:
    suffix, _magic = _output_format_spec(output_format)
    if not Path(output_pattern).is_absolute():
        raise ValueError("output_pattern must be an absolute path")
    matches = list(_FRAME_TOKEN.finditer(output_pattern))
    if not matches:
        raise ValueError("output_pattern must contain a # frame placeholder")
    if len(matches) != 1:
        raise ValueError("output_pattern must contain exactly one # frame placeholder")
    match = matches[0]
    value = output_pattern[: match.start()] + str(frame).zfill(len(match.group())) + output_pattern[match.end() :]
    path = Path(value)
    return path if path.suffix.lower() == suffix else Path(value + suffix)


def _select_frames(
    output_pattern: str,
    start_frame: int,
    end_frame: int,
    step: int,
    *,
    resume_missing: bool,
    output_format: str = "OPEN_EXR_MULTILAYER",
) -> List[int]:
    if start_frame > end_frame:
        raise ValueError("start_frame must be less than or equal to end_frame")
    if step < 1:
        raise ValueError("step must be at least 1")
    frames = list(range(start_frame, end_frame + 1, step))
    _expected_output_path(output_pattern, frames[0], output_format=output_format)
    if not resume_missing:
        return frames
    return [
        frame
        for frame in frames
        if not _is_valid_output(
            _expected_output_path(output_pattern, frame, output_format=output_format),
            output_format=output_format,
        )
    ]


def _is_valid_output(path: Path, *, output_format: str = "OPEN_EXR_MULTILAYER") -> bool:
    _suffix, magic = _output_format_spec(output_format)
    try:
        if not path.is_file() or path.stat().st_size < len(magic):
            return False
        with path.open("rb") as stream:
            return stream.read(len(magic)) == magic
    except OSError:
        return False


def _log_tail(source: Dict[str, Any], key: str) -> str:
    """Return the tail of one worker log file, or "" when it cannot be read.

    A failed job used to report only ``status: failed``, leaving the caller to
    open the log paths itself. Carrying the tails here is what lets an agent
    tell a device failure from a bad output path without a second round trip.

    Seeks to the end instead of reading the whole file: render logs can be
    large, and a failed job re-reads them on every poll.
    """
    try:
        with open(source[key], "rb") as stream:
            stream.seek(0, os.SEEK_END)
            stream.seek(max(stream.tell() - _LOG_TAIL_BYTES, 0))
            return stream.read().decode("utf-8", "replace")
    except (KeyError, OSError, TypeError, ValueError):
        return ""


def _failed_job_context(context: Dict[str, Any]) -> Dict[str, Any]:
    """Add worker log tails to a failed job's context, plus a device hint.

    Works for every job kind because both the animation and the multiview
    context carry ``stdout_path`` / ``stderr_path``. Both logs are read because
    Blender reports the device error on stdout on some platforms and on stderr
    on others.
    """
    enriched = dict(context)
    stderr_tail = _log_tail(context, "stderr_path")
    stdout_tail = _log_tail(context, "stdout_path")
    enriched["stderr_tail"] = stderr_tail
    enriched["stdout_tail"] = stdout_tail
    hint = _device_failure_hint(stderr_tail) or _device_failure_hint(stdout_tail)
    if hint:
        enriched["failure_hint"] = hint
    return enriched


def _failure_message(context: Dict[str, Any]) -> str:
    """Summarise a failed job using only fields the context actually has.

    The device hint wins because it is actionable; a job that already recorded
    its own ``error`` (multiview receipts do) is quoted; otherwise the caller
    is pointed at the tails, which are always present on this path.
    """
    if context.get("failure_hint"):
        return context["failure_hint"]
    if context.get("error"):
        return "Render job failed: {}".format(context["error"])
    return "Render job failed; see stderr_tail and stdout_tail for the worker's last output."


def _device_failure_hint(log_tail: str) -> str:
    """Attribute an unresolvable Cycles device to the ``device`` argument.

    Returns "" unless the tail carries Blender's "Found no Cycles device of the
    specified type". In that case the failure is caused by the device the job
    was asked to use, so the hint names ``device`` and suggests ``CPU``; the
    caller can then retry instead of reporting an anonymous failure.
    """
    if _CYCLES_DEVICE_ERROR not in log_tail.lower():
        return ""
    return (
        "Blender found no Cycles device of the type this job requested. Retry start_render_job with "
        'device="CPU", or with a device this host actually provides ({}). '
        "OptiX requires an NVIDIA GPU and is unavailable on macOS.".format(", ".join(_DEVICES))
    )


def _build_blender_command(
    *,
    blender_path: str,
    scene_path: str,
    output_pattern: str,
    frames: List[int],
    device: str = None,
    factory_startup: bool,
    output_format: str = "OPEN_EXR_MULTILAYER",
) -> List[str]:
    """Build the ``blender --background`` command for an owned render job.

    ``device=None`` omits ``-- --cycles-device`` entirely so the worker falls
    back to the Cycles device stored in the .blend file. Passing a device is an
    explicit override and stays the only way to override an artist's scene.
    """
    format_name = str(output_format).strip().upper()
    _output_format_spec(format_name)
    command = [blender_path, "--background"]
    if factory_startup:
        command.append("--factory-startup")
    command.extend(
        [
            scene_path,
            "--render-output",
            output_pattern,
            "--render-format",
            format_name,
            "--use-extension",
            "1",
        ]
    )
    for frame in frames:
        command.extend(("--render-frame", str(frame)))
    if device:
        command.extend(("--", "--cycles-device", device.upper()))
    return command


def start_render_job(
    output_pattern: str,
    start_frame: int,
    end_frame: int,
    step: int = 1,
    resume_missing: bool = True,
    device: str = None,
    save_before_render: bool = True,
    factory_startup: bool = False,
    output_format: str = None,
) -> dict:
    """Save the current scene and submit an isolated animation render.

    ``output_format`` defaults to the live scene's
    ``render.image_settings.file_format`` so ``set_render_settings`` controls
    the frames a job writes instead of every job silently emitting EXR.

    ``device`` defaults to ``None``: no ``--cycles-device`` is appended and the
    worker uses the Cycles device saved in the .blend (CPU for a new scene).
    Forcing a device here overrides the artist's scene, and ``OPTIX`` in
    particular fails with "Found no Cycles device of the specified type" on
    macOS and on every host without an NVIDIA GPU. Pass one of ``OPTIX``,
    ``CUDA``, ``HIP``, ``ONEAPI``, ``METAL``, ``CPU`` only to override.
    """
    try:
        import bpy  # Lazy import: requires Blender's embedded Python.

        try:
            resolved_format = _resolve_output_format(output_format)
        except ValueError as exc:
            return skill_error(
                "Unsupported render output format",
                str(exc),
                prompt="Call set_render_settings or set_render_output with a supported file_format, then retry.",
            )
        frames = _select_frames(
            output_pattern,
            start_frame,
            end_frame,
            step,
            resume_missing=resume_missing,
            output_format=resolved_format,
        )
        scene_path = str(getattr(bpy.data, "filepath", ""))
        if not scene_path:
            return skill_error("Scene is not saved", "Save the .blend file before starting a background render.")
        if save_before_render:
            bpy.ops.wm.save_as_mainfile(filepath=scene_path)

        output_dir = _expected_output_path(output_pattern, start_frame, output_format=resolved_format).parent
        output_dir.mkdir(parents=True, exist_ok=True)
        job_id = uuid.uuid4().hex
        stdout_path = output_dir / (".dcc-mcp-render-{}.out.log".format(job_id))
        stderr_path = output_dir / (".dcc-mcp-render-{}.err.log".format(job_id))
        process = None
        if frames:
            command = _build_blender_command(
                blender_path=str(bpy.app.binary_path),
                scene_path=scene_path,
                output_pattern=output_pattern,
                frames=frames,
                device=device,
                factory_startup=factory_startup,
                output_format=resolved_format,
            )
            process = _launch_worker(command, output_dir, stdout_path, stderr_path)

        job = {
            "job_id": job_id,
            "process": process,
            "status": "running" if process is not None else "completed",
            "frames": frames,
            "output_pattern": output_pattern,
            "output_format": resolved_format,
            "scene_path": scene_path,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "started_at": time.time(),
        }
        with _LOCK:
            _JOBS[job_id] = job
        return skill_success(
            "Background render job submitted ({})".format(resolved_format)
            if frames
            else "All requested frames already exist ({})".format(resolved_format),
            **_job_context(job),
            prompt="Use get_render_job to monitor progress and cancel_render_job to stop the owned worker.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to start background render job")


def get_render_job(job_id: str, job_directory: str = None) -> dict:
    with _LOCK:
        job = _JOBS.get(job_id)
    if job is None:
        if job_directory is None:
            return skill_error("Render job not found", "Unknown job_id: {}".format(job_id))
        job = dict(job_id=job_id, kind="multiview", job_directory=job_directory)
    try:
        context = _job_context(job)
    except (OSError, ValueError, KeyError) as exc:
        return skill_error("Render receipt unavailable", str(exc))
    if context["status"] != "failed":
        return skill_success("Render job status", **context)
    # Enriched here rather than in ``_job_context`` so every job kind gets the
    # tails: ``multiview_context`` returns early and never reaches the
    # animation branch below. A failed job is a successful status read, but the
    # message has to say why instead of reporting an anonymous failure.
    context = _failed_job_context(context)
    message = _failure_message(context)
    return skill_success(
        message,
        **context,
        prompt=context.get("failure_hint") or "Read stderr_tail and stdout_tail, then resubmit the job.",
    )


def cancel_render_job(job_id: str, job_directory: str = None) -> dict:
    with _LOCK:
        job = _JOBS.get(job_id)
    if job is None:
        if job_directory is None:
            return skill_error("Render job not found", "Unknown job_id: {}".format(job_id))
        job = dict(job_id=job_id, kind="multiview", job_directory=job_directory)
    if job.get("kind") == "multiview":
        from dcc_mcp_blender._multiview_receipt import TERMINAL, multiview_context

        try:
            context = multiview_context(job)
            if context["status"] not in TERMINAL:
                (Path(job["job_directory"]) / "cancel").touch()
                context["cancellation_requested"] = True
            return skill_success("Multiview cancellation requested at the next image boundary", **context)
        except (OSError, ValueError, KeyError) as exc:
            return skill_error("Render receipt unavailable", str(exc))
    _job_context(job)
    if job["status"] not in {"completed", "failed", "cancelled"}:
        process = job.get("process")
        if process is not None:
            _terminate_process_tree(process)
        job["status"] = "cancelled"
    return skill_success("Render job cancelled", **_job_context(job))


def _job_context(job: Dict[str, Any]) -> Dict[str, Any]:
    if job.get("kind") == "multiview":
        from dcc_mcp_blender._multiview_receipt import multiview_context

        return multiview_context(job)
    process = job.get("process")
    output_format = str(job.get("output_format", "OPEN_EXR_MULTILAYER")).strip().upper()
    _output_format_spec(output_format)
    if job["status"] == "running" and process is not None:
        return_code = process.poll()
        if return_code is not None:
            expected = [
                _expected_output_path(
                    job["output_pattern"],
                    frame,
                    output_format=output_format,
                )
                for frame in job["frames"]
            ]
            job["status"] = (
                "completed"
                if return_code == 0 and all(_is_valid_output(path, output_format=output_format) for path in expected)
                else "failed"
            )
    written = [
        frame
        for frame in job["frames"]
        if _is_valid_output(
            _expected_output_path(
                job["output_pattern"],
                frame,
                output_format=output_format,
            ),
            output_format=output_format,
        )
    ]
    written_set = set(written)
    missing = [frame for frame in job["frames"] if frame not in written_set]
    expected_count = len(job["frames"])
    context = {
        "job_id": job["job_id"],
        "status": job["status"],
        "pid": None if process is None else process.pid,
        "expected_frame_count": expected_count,
        "written_frame_count": len(written),
        "progress": 1.0 if expected_count == 0 else len(written) / expected_count,
        "missing_frame_sample": missing[:32],
        "output_pattern": job["output_pattern"],
        "output_format": output_format,
        "stdout_path": job["stdout_path"],
        "stderr_path": job["stderr_path"],
    }
    return context


def _terminate_process_tree(process: Any) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            capture_output=True,
        )
        return
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except (OSError, ProcessLookupError):
        process.terminate()
