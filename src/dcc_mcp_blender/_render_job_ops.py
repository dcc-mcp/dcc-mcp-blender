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
    "PNG": (".png", _PNG_MAGIC),
}
_JOBS: Dict[str, Dict[str, Any]] = {}
_LOCK = threading.Lock()


def _output_format_spec(output_format: str) -> Tuple[str, bytes]:
    name = str(output_format).strip().upper()
    try:
        return _OUTPUT_FORMATS[name]
    except KeyError as exc:
        raise ValueError("output_format must be one of: OPEN_EXR_MULTILAYER, PNG") from exc


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


def _build_blender_command(
    *,
    blender_path: str,
    scene_path: str,
    output_pattern: str,
    frames: List[int],
    device: str,
    factory_startup: bool,
    output_format: str = "OPEN_EXR_MULTILAYER",
) -> List[str]:
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
    device: str = "OPTIX",
    save_before_render: bool = True,
    factory_startup: bool = False,
    output_format: str = "OPEN_EXR_MULTILAYER",
) -> dict:
    """Save the current scene and submit an isolated animation render."""
    try:
        import bpy  # Lazy import: requires Blender's embedded Python.

        frames = _select_frames(
            output_pattern,
            start_frame,
            end_frame,
            step,
            resume_missing=resume_missing,
            output_format=output_format,
        )
        scene_path = str(getattr(bpy.data, "filepath", ""))
        if not scene_path:
            return skill_error("Scene is not saved", "Save the .blend file before starting a background render.")
        if save_before_render:
            bpy.ops.wm.save_as_mainfile(filepath=scene_path)

        output_dir = _expected_output_path(output_pattern, start_frame, output_format=output_format).parent
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
                output_format=output_format,
            )
            env = os.environ.copy()
            env["DCC_MCP_BACKGROUND_RENDER"] = "1"
            popen_kwargs: Dict[str, Any] = {"env": env, "cwd": str(output_dir)}
            if os.name == "nt":
                popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
            else:
                popen_kwargs["start_new_session"] = True
            with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
                process = subprocess.Popen(command, stdout=stdout, stderr=stderr, **popen_kwargs)

        job = {
            "job_id": job_id,
            "process": process,
            "status": "running" if process is not None else "completed",
            "frames": frames,
            "output_pattern": output_pattern,
            "output_format": str(output_format).strip().upper(),
            "scene_path": scene_path,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "started_at": time.time(),
        }
        with _LOCK:
            _JOBS[job_id] = job
        return skill_success(
            "Background render job submitted" if frames else "All requested frames already exist",
            **_job_context(job),
            prompt="Use get_render_job to monitor progress and cancel_render_job to stop the owned worker.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to start background render job")


def get_render_job(job_id: str) -> dict:
    with _LOCK:
        job = _JOBS.get(job_id)
    if job is None:
        return skill_error("Render job not found", "Unknown job_id: {}".format(job_id))
    return skill_success("Render job status", **_job_context(job))


def cancel_render_job(job_id: str) -> dict:
    with _LOCK:
        job = _JOBS.get(job_id)
    if job is None:
        return skill_error("Render job not found", "Unknown job_id: {}".format(job_id))
    _job_context(job)
    if job["status"] not in {"completed", "failed", "cancelled"}:
        process = job.get("process")
        if process is not None:
            _terminate_process_tree(process)
        job["status"] = "cancelled"
    return skill_success("Render job cancelled", **_job_context(job))


def _job_context(job: Dict[str, Any]) -> Dict[str, Any]:
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
    return {
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
