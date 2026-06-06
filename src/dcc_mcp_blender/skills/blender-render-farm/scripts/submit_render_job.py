"""Submit the current Blender scene to a render farm (Flamenco, Deadline, or generic)."""

# Import future modules
from __future__ import annotations

# Import built-in modules
import json
import os
import subprocess
import tempfile
from typing import Optional

# Import local modules
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def submit_render_job(
    farm: str = "flamenco",
    job_name: Optional[str] = None,
    pool: str = "blender",
    priority: int = 50,
    start_frame: Optional[int] = None,
    end_frame: Optional[int] = None,
    chunk_size: int = 10,
    deadline_command: Optional[str] = None,
    flamenco_server_url: Optional[str] = None,
    flamenco_project_id: Optional[str] = None,
) -> dict:
    """Submit the current Blender scene to a render farm.

    Supports three farm backends:

    - ``"flamenco"``: Submit to a Flamenco Manager via the REST API.
    - ``"deadline"``: Submit to Thinkbox Deadline via ``deadlinecommand`` CLI.
    - ``"generic"``: Write a JSON job spec to a directory for a custom dispatcher.

    Args:
        farm: Render farm backend (``"flamenco"``, ``"deadline"``, or ``"generic"``).
        job_name: Display name for the job.  Defaults to scene stem.
        pool: Worker pool / farm name.  Default: ``"blender"``.
        priority: Job priority 0-100.  Default: 50.
        start_frame: Override start frame.
        end_frame: Override end frame.
        chunk_size: Frames per task.  Default: 10.
        deadline_command: Path to ``deadlinecommand`` binary (Deadline only).
        flamenco_server_url: Flamenco Manager URL (Flamenco only).
        flamenco_project_id: Flamenco project UUID (Flamenco only).

    Returns:
        ToolResult dict with the job ID on success.
    """

    try:
        import bpy  # noqa: PLC0415

        scene_path = bpy.data.filepath or ""
        if not scene_path:
            return skill_error(
                "Scene must be saved before submitting",
                "Save the scene first with save_scene",
            )

        scene_stem = os.path.splitext(os.path.basename(scene_path))[0]
        name = job_name or scene_stem

        scene = bpy.context.scene
        render = scene.render

        sf = start_frame if start_frame is not None else scene.frame_start
        ef = end_frame if end_frame is not None else scene.frame_end

        if farm == "deadline":
            return _submit_to_deadline(
                name=name,
                scene_path=scene_path,
                pool=pool,
                priority=priority,
                sf=sf,
                ef=ef,
                chunk_size=chunk_size,
                render_engine=render.engine,
                output_path=render.filepath,
                deadline_command=deadline_command,
            )
        elif farm == "flamenco":
            return _submit_to_flamenco(
                name=name,
                scene_path=scene_path,
                sf=sf,
                ef=ef,
                chunk_size=chunk_size,
                priority=priority,
                render_engine=render.engine,
                output_path=render.filepath,
                flamenco_server_url=flamenco_server_url,
                flamenco_project_id=flamenco_project_id,
            )
        elif farm == "generic":
            return _submit_generic(
                name=name,
                scene_path=scene_path,
                sf=sf,
                ef=ef,
                chunk_size=chunk_size,
                render_engine=render.engine,
                output_path=render.filepath,
                resolution_x=render.resolution_x,
                resolution_y=render.resolution_y,
                file_format=render.image_settings.file_format,
            )
        else:
            return skill_error(
                "Unknown farm type: '{}'".format(farm),
                "Supported farms: flamenco, deadline, generic",
            )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to submit render job")


def _submit_to_deadline(
    name: str,
    scene_path: str,
    pool: str,
    priority: int,
    sf: int,
    ef: int,
    chunk_size: int,
    render_engine: str,
    output_path: str,
    deadline_command: Optional[str],
) -> dict:
    """Submit to Thinkbox Deadline via deadlinecommand CLI."""
    from dcc_mcp_core import check_dcc_cancelled  # noqa: PLC0415

    check_dcc_cancelled()

    # Locate deadlinecommand
    cmd = deadline_command
    if not cmd:
        for candidate in ["deadlinecommand", "deadlinecommand.exe"]:
            result = subprocess.run(
                ["where", candidate] if os.name == "nt" else ["which", candidate],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                cmd = candidate
                break
    if not cmd:
        return skill_error(
            "deadlinecommand not found",
            "Install Thinkbox Deadline client and ensure it is on PATH",
        )

    check_dcc_cancelled()

    # Build minimal job info files
    job_info = {
        "Plugin": "Blender",
        "Name": name,
        "Pool": pool,
        "Priority": str(priority),
        "Frames": "{}-{}".format(sf, ef),
        "ChunkSize": str(chunk_size),
        "OutputDirectory0": output_path,
    }
    import bpy as _bpy  # noqa: PLC0415

    plugin_info = {
        "SceneFile": scene_path,
        "Version": _bpy.app.version_string if hasattr(_bpy.app, "version_string") else "4.0",
        "Renderer": render_engine,
    }

    with tempfile.TemporaryDirectory() as tmp:
        job_file = os.path.join(tmp, "job_info.job")
        plugin_file = os.path.join(tmp, "plugin_info.job")

        with open(job_file, "w") as fh:
            for k, v in job_info.items():
                fh.write("{}={}\n".format(k, v))
        with open(plugin_file, "w") as fh:
            for k, v in plugin_info.items():
                fh.write("{}={}\n".format(k, v))

        proc = subprocess.run(
            [cmd, job_file, plugin_file],
            capture_output=True,
            text=True,
            timeout=60,
        )

    if proc.returncode != 0:
        return skill_error(
            "Deadline submission failed",
            proc.stderr.strip() or proc.stdout.strip(),
        )

    # Parse job ID from output
    job_id = ""
    for line in proc.stdout.splitlines():
        if "JobID" in line or "Job ID" in line:
            parts = line.split("=", 1) if "=" in line else line.split(":", 1)
            if len(parts) == 2:
                job_id = parts[1].strip()
                break

    return skill_success(
        "Submitted '{}' to Deadline (job ID: {})".format(name, job_id or "unknown"),
        prompt="Use get_render_job_status with farm='deadline' and the job ID to monitor progress.",
        job_id=job_id,
        name=name,
        farm="deadline",
        pool=pool,
        frame_range="{}-{}".format(sf, ef),
    )


def _submit_to_flamenco(
    name: str,
    scene_path: str,
    sf: int,
    ef: int,
    chunk_size: int,
    priority: int,
    render_engine: str,
    output_path: str,
    flamenco_server_url: Optional[str],
    flamenco_project_id: Optional[str],
) -> dict:
    """Submit to Flamenco Manager via its REST API.

    Aligns with the Flamenco \"Simple Blender Render\" job type schema
    (v3 API).  Required settings: ``blender_cmd``, ``filepath``,
    ``frames``, ``chunk_size``, ``render_output``, ``render_engine``,
    ``add_path_components``.
    """
    try:
        import urllib.request  # noqa: PLC0415

        from dcc_mcp_core import check_dcc_cancelled  # noqa: PLC0415

        server_url = flamenco_server_url or os.environ.get("FLAMENCO_SERVER_URL", "http://localhost:8080")
        server_url = server_url.rstrip("/")

        check_dcc_cancelled()

        # Build job payload matching Flamenco "blender-render" job type
        job_payload = {
            "name": name,
            "type": "blender-render",
            "description": "Submitted from dcc-mcp-blender",
            "settings": {
                "blender_cmd": "blender",
                "filepath": scene_path,
                "render_engine": render_engine,
                "render_output": output_path,
                "frames": "{}-{}".format(sf, ef),
                "chunk_size": chunk_size,
                "add_path_components": True,
            },
            "priority": priority,
        }
        if flamenco_project_id:
            job_payload["project_id"] = flamenco_project_id

        # Submit job via Flamenco REST API
        api_url = "{}/api/v3/jobs".format(server_url)
        data = json.dumps(job_payload).encode("utf-8")
        req = urllib.request.Request(
            api_url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            job_id = result.get("id", "")

        return skill_success(
            "Submitted '{}' to Flamenco (job ID: {})".format(name, job_id),
            prompt="Use get_render_job_status with farm='flamenco' and the job ID to monitor progress.",
            job_id=job_id,
            name=name,
            farm="flamenco",
            server_url=server_url,
            frame_range="{}-{}".format(sf, ef),
            priority=priority,
        )
    except ImportError:
        return skill_error(
            "urllib not available",
            "Python standard library was stripped; install python or use deadline farm",
        )
    except Exception as exc:
        return skill_error(
            "Flamenco submission failed",
            str(exc),
        )


def _submit_generic(
    name: str,
    scene_path: str,
    sf: int,
    ef: int,
    chunk_size: int,
    render_engine: str,
    output_path: str,
    resolution_x: int,
    resolution_y: int,
    file_format: str,
) -> dict:
    """Write a generic render job spec and return the file path."""
    from dcc_mcp_core import check_dcc_cancelled  # noqa: PLC0415

    check_dcc_cancelled()

    job_spec = {
        "name": name,
        "scene_file": scene_path,
        "renderer": render_engine,
        "start_frame": sf,
        "end_frame": ef,
        "chunk_size": chunk_size,
        "output_dir": output_path,
        "resolution_x": resolution_x,
        "resolution_y": resolution_y,
        "file_format": file_format,
    }

    output_dir = os.path.join(tempfile.gettempdir(), "render_jobs")
    os.makedirs(output_dir, exist_ok=True)
    job_file = os.path.join(output_dir, "{}.json".format(name))

    with open(job_file, "w") as fh:
        json.dump(job_spec, fh, indent=2)

    frame_count = max(0, (ef - sf) + 1)
    task_count = max(1, (frame_count + chunk_size - 1) // chunk_size)

    return skill_success(
        "Wrote generic render job spec '{}'".format(name),
        prompt=("The job spec was written to {}. Use a custom dispatcher to pick up and run the job.".format(job_file)),
        job_file=job_file,
        name=name,
        farm="generic",
        frame_range="{}-{}".format(sf, ef),
        frame_count=frame_count,
        task_count=task_count,
    )


@skill_entry
def main(**kwargs):
    return submit_render_job(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
