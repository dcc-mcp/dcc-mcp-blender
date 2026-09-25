"""Real Blender background render jobs honour the resolved output format.

These tests drive ``start_render_job`` end to end in a real Blender process:
the job saves the scene, launches a detached ``blender --background`` worker
with ``--render-format <FMT> --use-extension 1``, and only reports
``completed`` once every expected frame exists with the magic bytes of the
resolved format. Asserting on the files that land on disk is what pins the
format decision: a job that silently fell back to EXR writes ``.exr`` frames
and fails here instead of being discovered later by ffmpeg or ImageMagick.
"""

import time
from pathlib import Path

import pytest

bpy = pytest.importorskip("bpy")
pytestmark = pytest.mark.e2e

from dcc_mcp_blender import _render_job_ops as jobs  # noqa: E402
from dcc_mcp_blender._render_job_ops import get_render_job, start_render_job  # noqa: E402

# Scene ``render.image_settings.file_format`` values every supported Blender
# still exposes, mapped to the extension the worker must write for them.
# ``OPEN_EXR_MULTILAYER`` is deliberately absent: Blender 5.x dropped it from
# the scene enum, so it is covered through the explicit ``output_format``
# argument below instead, which reaches the worker's ``--render-format``.
SCENE_FORMATS = {
    "OPEN_EXR": ".exr",
    "PNG": ".png",
}

TERMINAL = {"completed", "failed", "cancelled"}

# CI runners have no GPU, and Blender consumes the trailing
# ``--cycles-device`` argument a job appends: asking for OPTIX there fails with
# "Found no Cycles device of the specified type". CPU keeps the job portable
# across the whole matrix while still exercising the device pass-through.
DEVICE = "CPU"


def _prepare_scene(tmp_path):
    """Build a tiny Cycles scene and save it so a job can submit it."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_cube_add()
    bpy.ops.object.camera_add(location=(4, -6, 3))
    camera = bpy.context.active_object
    camera.rotation_euler = (-camera.location).to_track_quat("-Z", "Y").to_euler()
    scene = bpy.context.scene
    scene.camera = camera
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 1
    scene.render.resolution_x = 32
    scene.render.resolution_y = 32
    bpy.ops.wm.save_as_mainfile(filepath=str(tmp_path / "scene.blend"))
    return scene


def _await_completion(job_id, timeout=300):
    """Poll ``get_render_job`` until the owned worker reaches a terminal state."""
    deadline = time.monotonic() + timeout
    while True:
        response = get_render_job(job_id)
        assert response["success"], response
        context = response["context"]
        if context["status"] in TERMINAL or time.monotonic() >= deadline:
            return context
        time.sleep(0.2)


def _worker_logs(context):
    """Tail the detached worker's logs so a failed job explains itself."""
    log = {}
    for key in ("stdout_path", "stderr_path"):
        try:
            log[key] = Path(context[key]).read_text(errors="replace")[-1500:]
        except (KeyError, OSError):
            pass
    return log


def _frame_names(output_dir):
    return sorted(path.name for path in output_dir.iterdir() if not path.name.startswith("."))


@pytest.mark.parametrize("scene_format", sorted(SCENE_FORMATS))
def test_start_render_job_writes_scene_format(tmp_path, scene_format):
    """A saved scene's ``file_format`` decides the frames the worker writes."""
    scene = _prepare_scene(tmp_path)
    previous_format = scene.render.image_settings.file_format
    output_dir = tmp_path / "renders"
    scene.render.image_settings.file_format = scene_format
    job_id = None
    try:
        result = start_render_job(str(output_dir / "beauty_####"), 1, 2, device=DEVICE)
        assert result["success"], result
        job_id = result["context"]["job_id"]
        assert result["context"]["output_format"] == scene_format, result

        context = _await_completion(job_id)
        assert context["status"] == "completed", (context, _worker_logs(context))
        assert context["output_format"] == scene_format, context
        assert context["expected_frame_count"] == 2, context
        assert context["written_frame_count"] == 2, context

        suffix = SCENE_FORMATS[scene_format]
        written = _frame_names(output_dir)
        assert written == ["beauty_0001" + suffix, "beauty_0002" + suffix], written
        for name in written:
            path = output_dir / name
            assert path.stat().st_size > 0, path
            assert jobs._is_valid_output(path, output_format=scene_format), (path, scene_format)
    finally:
        scene.render.image_settings.file_format = previous_format
        jobs._JOBS.pop(job_id, None)


def test_start_render_job_explicit_format_overrides_scene(tmp_path):
    """An explicit ``output_format`` wins over the saved scene's format.

    Also keeps ``--render-format OPEN_EXR_MULTILAYER`` exercised on every
    Blender in the matrix: it is the job default, and Blender 5.x no longer
    offers the value through the scene enum.
    """
    scene = _prepare_scene(tmp_path)
    previous_format = scene.render.image_settings.file_format
    output_dir = tmp_path / "explicit"
    scene.render.image_settings.file_format = "PNG"
    job_id = None
    try:
        result = start_render_job(
            str(output_dir / "beauty_####"), 5, 5, output_format="OPEN_EXR_MULTILAYER", device=DEVICE
        )
        assert result["success"], result
        job_id = result["context"]["job_id"]
        assert result["context"]["output_format"] == "OPEN_EXR_MULTILAYER", result

        context = _await_completion(job_id)
        assert context["status"] == "completed", (context, _worker_logs(context))
        assert context["output_format"] == "OPEN_EXR_MULTILAYER", context

        written = _frame_names(output_dir)
        assert written == ["beauty_0005.exr"], written
        assert jobs._is_valid_output(output_dir / written[0], output_format="OPEN_EXR_MULTILAYER")
    finally:
        scene.render.image_settings.file_format = previous_format
        jobs._JOBS.pop(job_id, None)
