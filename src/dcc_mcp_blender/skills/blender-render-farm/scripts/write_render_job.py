"""Write a JSON render job specification for a render farm dispatcher."""

# Import future modules
from __future__ import annotations

# Import built-in modules
import json
import os
from typing import Optional

# Import local modules
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def write_render_job(
    output_dir: str,
    job_name: Optional[str] = None,
    renderer: Optional[str] = None,
    start_frame: Optional[int] = None,
    end_frame: Optional[int] = None,
    step: int = 1,
    chunk_size: int = 10,
    priority: int = 50,
) -> dict:
    """Write a render job JSON spec from the current scene settings.

    Args:
        output_dir: Directory where the ``.json`` job file is written.
        job_name: Job display name.  Defaults to the scene file stem.
        renderer: Override render engine name (e.g. ``"CYCLES"``, ``"BLENDER_EEVEE"``).
            Defaults to the scene's active render engine.
        start_frame: Override start frame.  Defaults to scene render frame_start.
        end_frame: Override end frame.  Defaults to scene render frame_end.
        step: Frame step / increment.  Default: 1.
        chunk_size: Frames per render task.  Default: 10.
        priority: Job priority (0=low, 100=high).  Default: 50.

    Returns:
        ToolResult dict with ``context.job_file`` path and job spec summary.
    """

    try:
        import bpy  # noqa: PLC0415

        scene_path = bpy.data.filepath or ""
        scene_stem = os.path.splitext(os.path.basename(scene_path))[0] or "untitled"

        name = job_name or scene_stem

        scene = bpy.context.scene
        render = scene.render

        sf = start_frame if start_frame is not None else scene.frame_start
        ef = end_frame if end_frame is not None else scene.frame_end

        active_renderer = renderer
        if not active_renderer:
            active_renderer = render.engine

        render_output = render.filepath or ""

        # Collect extra render settings for the job spec
        cycles_samples = None
        eevee_samples = None
        if active_renderer == "CYCLES" and hasattr(scene, "cycles"):
            cycles_samples = scene.cycles.samples
        elif "EEVEE" in active_renderer and hasattr(scene, "eevee"):
            eevee_samples = scene.eevee.taa_render_samples

        job_spec = {
            "name": name,
            "scene_file": scene_path,
            "renderer": active_renderer,
            "start_frame": sf,
            "end_frame": ef,
            "step": step,
            "chunk_size": chunk_size,
            "priority": priority,
            "output_dir": render_output,
            "resolution_x": render.resolution_x,
            "resolution_y": render.resolution_y,
            "resolution_percentage": render.resolution_percentage,
            "file_format": render.image_settings.file_format,
        }
        if cycles_samples is not None:
            job_spec["samples"] = cycles_samples
        if eevee_samples is not None:
            job_spec["samples"] = eevee_samples

        os.makedirs(output_dir, exist_ok=True)
        job_file = os.path.join(output_dir, "{}.json".format(name))
        with open(job_file, "w") as fh:
            json.dump(job_spec, fh, indent=2)

        frame_count = max(0, (ef - sf) // step + 1)
        task_count = max(1, (frame_count + chunk_size - 1) // chunk_size)

        return skill_success(
            "Wrote render job spec '{}' to '{}'".format(name, job_file),
            prompt="Use submit_render_job to send this job to the render farm.",
            job_file=job_file,
            name=name,
            renderer=active_renderer,
            frame_range="{}-{}".format(sf, ef),
            frame_count=frame_count,
            task_count=task_count,
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to write render job")


@skill_entry
def main(**kwargs):
    return write_render_job(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
