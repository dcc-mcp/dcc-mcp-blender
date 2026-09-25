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

# Scene ``render.image_settings.file_format`` values a job must reproduce,
# mapped to the extension the worker has to write for them.
# ``OPEN_EXR_MULTILAYER`` belongs here because the scene path owns it: a scene
# saved with it has to stay multi-layer instead of silently degrading to a
# single-layer EXR. Hosts that no longer accept the value skip the case rather
# than fail it; the explicit ``output_format`` argument below still reaches the
# worker's ``--render-format`` on every host.
SCENE_FORMATS = {
    "OPEN_EXR": ".exr",
    "OPEN_EXR_MULTILAYER": ".exr",
    "PNG": ".png",
}


def _scene_format_accepted(name: str) -> bool:
    """Report whether this host still accepts ``name`` as a scene format.

    Blender 5.x keeps ``OPEN_EXR_MULTILAYER`` listed in the property's
    ``enum_items`` but rejects the assignment with "enum ... not found in
    (...)", so reading the enum is not a faithful gate -- only a round-trip
    assignment is. The previous value is restored either way, so probing a
    value costs nothing beyond the assignment itself.
    """
    settings = bpy.context.scene.render.image_settings
    previous = settings.file_format
    try:
        settings.file_format = name
    except (TypeError, ValueError):
        return False
    finally:
        settings.file_format = previous
    return True


# Probed once at collection time: a host's answer cannot change mid-session,
# and skipping a value it does not offer beats reporting a false failure.
SCENE_FORMAT_CASES = [
    pytest.param(
        name,
        marks=pytest.mark.skipif(
            not _scene_format_accepted(name),
            reason="Blender {} rejects {} on render.image_settings.file_format".format(
                ".".join(str(part) for part in bpy.app.version), name
            ),
        ),
    )
    for name in sorted(SCENE_FORMATS)
]


TERMINAL = {"completed", "failed", "cancelled"}

# CI runners have no GPU, and Blender consumes the trailing
# ``--cycles-device`` argument a job appends: asking for OPTIX there fails with
# "Found no Cycles device of the specified type". Pinning CPU below keeps the
# device pass-through exercised and the cases portable across the whole matrix.
# ``test_start_render_job_uses_scene_device_when_unset`` deliberately omits
# ``device`` instead: that is the default path, and it is what used to force
# OPTIX on every lane, including the macOS lanes where OptiX is unsupported.
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


@pytest.mark.parametrize("scene_format", SCENE_FORMAT_CASES)
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
        # Cancel before dropping the entry: ``_JOBS[job_id]["process"]`` is the
        # only handle on the detached worker, so a timeout or a failed assertion
        # above would otherwise leave a ``blender --background`` running forever.
        # Harmless on the green path -- cancelling a finished job is a no-op.
        if job_id is not None:
            jobs.cancel_render_job(job_id)
        jobs._JOBS.pop(job_id, None)


def test_start_render_job_uses_scene_device_when_unset(tmp_path):
    """Omitting ``device`` renders with the Cycles device saved in the scene.

    Regression guard for a default of ``device="OPTIX"``: Blender answers
    "Found no Cycles device of the specified type" there, so every macOS lane
    (OptiX is Windows/Linux only) and every GPU-less host failed by default.
    With no ``--cycles-device`` appended the worker honours
    ``scene.cycles.device``, which this scene sets to CPU.
    """
    scene = _prepare_scene(tmp_path)
    previous_format = scene.render.image_settings.file_format
    output_dir = tmp_path / "scene_device"
    scene.render.image_settings.file_format = "PNG"
    scene.cycles.device = "CPU"
    job_id = None
    try:
        result = start_render_job(str(output_dir / "beauty_####"), 1, 2)
        assert result["success"], result
        job_id = result["context"]["job_id"]

        context = _await_completion(job_id)
        assert context["status"] == "completed", (context, _worker_logs(context))
        assert context["expected_frame_count"] == 2, context
        assert context["written_frame_count"] == 2, context

        written = _frame_names(output_dir)
        assert written == ["beauty_0001.png", "beauty_0002.png"], written
    finally:
        scene.render.image_settings.file_format = previous_format
        if job_id is not None:
            jobs.cancel_render_job(job_id)
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
        if job_id is not None:
            jobs.cancel_render_job(job_id)
        jobs._JOBS.pop(job_id, None)
