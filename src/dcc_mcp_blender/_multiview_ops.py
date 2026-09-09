"""Submit bounded multiview jobs through the existing render process registry."""

from __future__ import annotations

import json
import math
import uuid
from pathlib import Path

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

from dcc_mcp_blender._multiview_receipt import multiview_context, write_receipt


def start_multiview_render_job(
    output_directory, camera_names, passes=("beauty", "wire"), resolution_x=1200, resolution_y=1200, wire_radius=0.008
):
    try:
        import bpy

        from dcc_mcp_blender import _render_job_ops as jobs

        root = Path(output_directory)
        if not root.is_absolute():
            raise ValueError("output_directory must be absolute")
        if not isinstance(camera_names, (list, tuple)) or not 1 <= len(camera_names) <= 8:
            raise ValueError("camera_names must contain 1 to 8 unique camera names")
        if any(not isinstance(name, str) or not name for name in camera_names) or len(set(camera_names)) != len(
            camera_names
        ):
            raise ValueError("camera_names must contain unique nonempty strings")
        if (
            not isinstance(passes, (list, tuple))
            or not passes
            or len(passes) > 2
            or any(p not in ("beauty", "wire") for p in passes)
            or len(set(passes)) != len(passes)
        ):
            raise ValueError("passes must be a unique selection of beauty and wire")
        for value in (resolution_x, resolution_y):
            if isinstance(value, bool) or not isinstance(value, int) or not 16 <= value <= 4096:
                raise ValueError("Image dimensions must be integers from 16 to 4096")
        if (
            isinstance(wire_radius, bool)
            or not isinstance(wire_radius, (int, float))
            or not math.isfinite(wire_radius)
            or not 0 < wire_radius <= 1
        ):
            raise ValueError("wire_radius must be finite and between 0 (exclusive) and 1 scene unit")
        for name in camera_names:
            camera = bpy.context.scene.objects.get(name)
            if camera is None or camera.type != "CAMERA":
                raise ValueError("Not a camera in the active scene: " + name)
        if "wire" in passes:
            edge_count = sum(
                len(obj.data.edges) for obj in bpy.context.scene.objects if obj.type == "MESH" and not obj.hide_render
            )
            if edge_count > 100000:
                raise ValueError("Wire pass exceeds 100000 source edges")
        job_id = uuid.uuid4().hex
        directory = root / ("dcc-mcp-multiview-" + job_id)
        directory.mkdir(parents=True, exist_ok=False)
        request = dict(
            job_id=job_id,
            camera_names=list(camera_names),
            passes=list(passes),
            resolution_x=resolution_x,
            resolution_y=resolution_y,
            wire_radius=wire_radius,
        )
        (directory / "request.json").write_text(json.dumps(request), encoding="utf-8")
        result = dict(
            job_id=job_id,
            kind="multiview",
            status="running",
            items=[
                dict(camera=name, **{"pass": render_pass}, status="pending")
                for name in camera_names
                for render_pass in passes
            ],
        )
        write_receipt(directory, result)
        try:
            # copy=True preserves the live filename and unsaved source changes.
            saved = bpy.ops.wm.save_as_mainfile(
                filepath=str(directory / "scene.blend"), copy=True, check_existing=False
            )
            if "FINISHED" not in saved:
                raise RuntimeError("Saving the isolated scene copy did not finish")
            worker = Path(__file__).with_name("_multiview_worker.py")
            command = [
                str(bpy.app.binary_path),
                "--background",
                "--factory-startup",
                "--disable-autoexec",
                "--python-exit-code",
                "1",
                "--python",
                str(worker),
                "--",
                str(directory),
            ]
            process = jobs._launch_worker(command, directory, directory / "stdout.log", directory / "stderr.log")
        except Exception as exc:
            result["status"] = "failed"
            result["error"] = str(exc)
            write_receipt(directory, result)
            return skill_error("Multiview submission failed", str(exc), job_id=job_id, job_directory=str(directory))
        job = dict(job_id=job_id, kind="multiview", job_directory=str(directory), process=process, status="running")
        with jobs._LOCK:
            jobs._JOBS[job_id] = job
        return skill_success(
            "Multiview render submitted",
            **multiview_context(job),
            prompt="Poll get_render_job; retain job_directory for receipt recovery after an adapter restart.",
        )
    except (TypeError, ValueError) as exc:
        return skill_error("Invalid multiview request", str(exc))
    except Exception as exc:
        return skill_exception(exc, message="Failed to submit multiview render")
