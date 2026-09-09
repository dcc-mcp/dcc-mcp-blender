"""Real isolated Blender multi-camera deliverables without source mutation."""

import time

import pytest

bpy = pytest.importorskip("bpy")
pytestmark = pytest.mark.e2e

from dcc_mcp_blender._multiview_ops import start_multiview_render_job  # noqa: E402
from dcc_mcp_blender._render_job_ops import get_render_job  # noqa: E402


def test_multiview_images_and_source_topology(tmp_path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_cube_add()
    cube = bpy.context.active_object
    cube.modifiers.new("Subdivision", "SUBSURF")
    for name, position in [("Front", (4, -6, 3)), ("Side", (6, 2, 3))]:
        data = bpy.data.cameras.new(name)
        camera = bpy.data.objects.new(name, data)
        bpy.context.scene.collection.objects.link(camera)
        camera.location = position
        camera.rotation_euler = (-camera.location).to_track_quat("-Z", "Y").to_euler()
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x = 333
    before = (bpy.data.filepath, scene.render.resolution_x, cube.modifiers[0].show_render, len(bpy.data.objects))
    result = start_multiview_render_job(str(tmp_path), ["Front", "Side"], resolution_x=64, resolution_y=64)
    assert result["success"], result
    job_id = result["context"]["job_id"]
    directory = result["context"]["job_directory"]
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        context = get_render_job(job_id)["context"]
        if context["status"] in {"completed", "failed", "cancelled"}:
            break
        time.sleep(0.1)
    assert context["status"] == "completed", context
    assert len(context["items"]) == 4
    assert all(item["image"]["width"] == 64 and item["image"]["height"] == 64 for item in context["items"])
    assert all(item["source_edge_count"] == 12 for item in context["items"] if item["pass"] == "wire")
    assert before == (
        bpy.data.filepath,
        scene.render.resolution_x,
        cube.modifiers[0].show_render,
        len(bpy.data.objects),
    )
    assert bpy.context.active_object == cube
    from dcc_mcp_blender import _render_job_ops

    del _render_job_ops._JOBS[job_id]
    assert get_render_job(job_id, directory)["context"]["status"] == "completed"


def test_worker_preserves_partial_failure(tmp_path):
    import importlib.util
    import json
    from pathlib import Path

    from dcc_mcp_blender import _render_job_ops
    from dcc_mcp_blender._multiview_receipt import write_receipt

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_cube_add()
    bpy.ops.object.camera_add(location=(4, -6, 3))
    camera = bpy.context.active_object
    camera.rotation_euler = (-camera.location).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.render.engine = "BLENDER_WORKBENCH"
    bpy.ops.wm.save_as_mainfile(filepath=str(tmp_path / "scene.blend"))
    (tmp_path / "request.json").write_text(
        json.dumps(dict(job_id="partial", resolution_x=32, resolution_y=32, wire_radius=0.01))
    )
    write_receipt(
        tmp_path,
        dict(
            job_id="partial",
            kind="multiview",
            status="running",
            items=[
                {"camera": "Missing", "pass": "beauty", "status": "pending"},
                {"camera": camera.name, "pass": "wire", "status": "pending"},
            ],
        ),
    )
    spec = importlib.util.spec_from_file_location(
        "partial_worker", Path(_render_job_ops.__file__).with_name("_multiview_worker.py")
    )
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    worker.run(tmp_path)
    result = get_render_job("partial", str(tmp_path))["context"]
    assert result["status"] == "failed"
    assert result["items"][0]["status"] == "failed"
    assert result["items"][1]["status"] == "completed"
