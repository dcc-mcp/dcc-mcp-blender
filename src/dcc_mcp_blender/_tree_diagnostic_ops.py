"""Run Blender-owned, isolated OBJ diagnostic previews in background workers."""

from __future__ import annotations

import atexit
import hashlib
import json
import subprocess
import threading
import uuid
from pathlib import Path

from dcc_mcp_core.skill import skill_error, skill_success

_JOBS = {}
_LOCK = threading.RLock()
_TIMEOUT_SECONDS = 600


def _stop_running(job, reason):
    process = job["process"]
    if process.poll() is not None:
        return False
    job["end_reason"] = reason
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)
    return True


def _timeout_job(job_id):
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is not None:
            try:
                _stop_running(job, "timed_out")
            except (OSError, subprocess.TimeoutExpired) as exc:
                job["stop_error"] = str(exc)


def _shutdown_jobs():
    with _LOCK:
        for job in _JOBS.values():
            job["timer"].cancel()
            try:
                _stop_running(job, "host_shutdown")
            except (OSError, subprocess.TimeoutExpired):
                pass


atexit.register(_shutdown_jobs)


def _hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def start_tree_diagnostic(obj_path, output_directory, material_categories, resolution=768):
    """Start a private subprocess using the current Blender host binary."""
    try:
        import bpy

        obj = Path(obj_path).expanduser().resolve(strict=True)
        root = Path(output_directory).expanduser().resolve(strict=True)
        if not obj.is_file() or obj.suffix.lower() != ".obj" or not root.is_dir():
            raise ValueError("Expected an OBJ file and existing output directory")
        if not isinstance(material_categories, dict) or not material_categories:
            raise ValueError("An explicit material mapping is required")
        if any(not isinstance(k, str) or not k or v not in {"wood", "card"} for k, v in material_categories.items()):
            raise ValueError("Each material must map to wood or card")
        if set(material_categories.values()) != {"wood", "card"}:
            raise ValueError("Both wood and card categories must be provided")
        if type(resolution) is not int or not 128 <= resolution <= 2048:
            raise ValueError("resolution must be an integer between 128 and 2048")
        if tuple(bpy.app.version) < (4, 5, 0):
            raise ValueError("Blender 4.5 or newer is required")
        binary = Path(bpy.app.binary_path).resolve(strict=True)
        if not binary.is_file():
            raise ValueError("Current Blender binary is unavailable")
        job_id = uuid.uuid4().hex
        directory = root / ("tree-diagnostic-" + job_id)
        directory.mkdir(exist_ok=False)
        config = {
            "obj": str(obj),
            "output": str(directory),
            "source_sha256": _hash(obj),
            "material_categories": material_categories,
            "resolution": resolution,
        }
        (directory / "request.json").write_text(json.dumps(config), encoding="utf-8")
        worker = Path(__file__).with_name("_tree_diagnostic_worker.py")
        command = [
            str(binary),
            "--background",
            "--factory-startup",
            "--disable-autoexec",
            "--python-exit-code",
            "1",
            "--python",
            str(worker),
            "--",
            str(directory / "request.json"),
        ]
        stdout = (directory / "stdout.log").open("wb")
        stderr = (directory / "stderr.log").open("wb")
        try:
            process = subprocess.Popen(
                command,
                stdout=stdout,
                stderr=stderr,
                stdin=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        finally:
            stdout.close()
            stderr.close()
        with _LOCK:
            _JOBS[job_id] = {
                "process": process,
                "directory": directory,
                "source": obj,
                "source_sha": config["source_sha256"],
                "end_reason": None,
            }
            timer = threading.Timer(_TIMEOUT_SECONDS, _timeout_job, args=(job_id,))
            timer.daemon = True
            _JOBS[job_id]["timer"] = timer
            timer.start()
        return skill_success("Tree diagnostics started", job_id=job_id, job_directory=str(directory), status="running")
    except Exception as exc:
        return skill_error("Tree diagnostics could not start", str(exc))


def get_tree_diagnostic(job_id):
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return skill_error("Unknown tree diagnostic job", "Job is not held by this Blender process")
        rc = job["process"].poll()
        context = {"job_id": job_id, "job_directory": str(job["directory"])}
        if rc is None and job.get("stop_error"):
            return skill_error("Worker could not be stopped", job["stop_error"], status="stop_failed", **context)
        if rc is None:
            return skill_success("Tree diagnostics running", status="running", **context)
        job["timer"].cancel()
        if job["end_reason"] == "cancelled":
            return skill_success("Tree diagnostics cancelled", status="cancelled", **context)
        if job["end_reason"] == "timed_out":
            return skill_error(
                "Tree diagnostics timed out", "Worker exceeded its 600-second limit", status="timed_out", **context
            )
        if rc != 0:
            return skill_error("Tree diagnostics failed", "Check stderr.log and stdout.log", return_code=rc, **context)
        try:
            manifest_path = job["directory"] / "preview-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if _hash(job["source"]) != job["source_sha"] or manifest["source"]["sha256"] != job["source_sha"]:
                raise ValueError("OBJ changed during the diagnostic job")
            expected = {
                f"{kind}_{view}{suffix}.png"
                for kind in ("full", "bare")
                for view in ("front", "back", "left", "right")
                for suffix in ("", "_mask")
            }
            expected.add("card_closeup.png")
            if set(manifest["images"]) != expected:
                raise ValueError("Diagnostic image set is incomplete")
            for name, digest in manifest["images"].items():
                if Path(name).name != name or _hash(job["directory"] / name) != digest:
                    raise ValueError("Diagnostic image hash mismatch: " + name)
            return skill_success(
                "Tree diagnostics completed", status="completed", manifest_path=str(manifest_path), **context
            )
        except Exception as exc:
            return skill_error("Invalid diagnostic evidence", str(exc), **context)


def cancel_tree_diagnostic(job_id):
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return skill_error("Unknown tree diagnostic job", "Job is not held by this Blender process")
        try:
            cancelled = _stop_running(job, "cancelled")
            if cancelled:
                job["timer"].cancel()
            return skill_success("Cancellation requested", job_id=job_id, cancellation_requested=cancelled)
        except (OSError, subprocess.TimeoutExpired) as exc:
            job["stop_error"] = str(exc)
            return skill_error("Could not terminate diagnostic worker", str(exc), job_id=job_id)
