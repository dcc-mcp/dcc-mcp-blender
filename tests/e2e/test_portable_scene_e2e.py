"""Native portable-copy acceptance on the supported Blender CI host matrix."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

bpy = pytest.importorskip("bpy", reason="Requires native Blender")
pytestmark = pytest.mark.e2e

from dcc_mcp_blender._animation_ops import action_fcurves  # noqa: E402
from tests.e2e.conftest import load_skill  # noqa: E402

PRIVATE_RENDER = "/workspace/portable-copy-fixture/private-render-directory/long-output.png"
PRIVATE_BROWSER = b"/workspace/portable-copy-fixture/private-browser-directory/"
RELATIVE_RENDER = "//renders/image.png"


@pytest.fixture(autouse=True)
def empty_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    yield
    bpy.ops.wm.read_factory_settings(use_empty=True)


def _scene_fixture():
    scene = bpy.context.scene
    bpy.ops.mesh.primitive_cube_add()
    cube = bpy.context.object
    cube.name = "PortableCube"
    for frame, x in ((1, 0.0), (5, 0.5), (9, 1.0)):
        cube.location.x = x
        cube.keyframe_insert(data_path="location", frame=frame)
    text = bpy.data.curves.new("PortableLabel", type="FONT")
    text.body = "PORTABLE / 01"
    text.size = 0.2
    label = bpy.data.objects.new("PortableLabel", text)
    scene.collection.objects.link(label)
    label.location = (-1.0, 0.0, 1.1)
    bpy.ops.object.camera_add(location=(4.0, -6.0, 4.0))
    camera = bpy.context.object
    camera.name = "PortableCamera"
    camera.rotation_euler = (-camera.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = camera
    scene.world = bpy.data.worlds.new("PortableWorld")
    scene.world.color = (0.3, 0.3, 0.3)
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 1
    scene.cycles.seed = 0
    scene.cycles.use_adaptive_sampling = False
    scene.cycles.use_denoising = False
    scene.render.resolution_x = scene.render.resolution_y = 32
    scene.render.resolution_percentage = 100
    scene.frame_set(5)
    scene.render.filepath = PRIVATE_RENDER


def _scene_readback():
    objects = {}
    for obj in bpy.data.objects:
        value = {
            "type": obj.type,
            "matrix": tuple(tuple(row) for row in obj.matrix_world),
            "materials": tuple(material.name if material else None for material in getattr(obj.data, "materials", ())),
            "keys": tuple(
                (
                    curve.data_path,
                    curve.array_index,
                    tuple(
                        (tuple(point.co), tuple(point.handle_left), tuple(point.handle_right))
                        for point in curve.keyframe_points
                    ),
                )
                for _, curve in action_fcurves(obj)
            ),
        }
        if obj.type == "MESH":
            value["vertices"] = tuple(tuple(vertex.co) for vertex in obj.data.vertices)
            value["faces"] = tuple(tuple(face.vertices) for face in obj.data.polygons)
        elif obj.type == "FONT":
            value["text"] = (obj.data.body, obj.data.size, obj.data.font.filepath)
        elif obj.type == "CAMERA":
            value["camera"] = (obj.data.type, obj.data.lens, obj.data.ortho_scale)
        objects[obj.name] = value
    return {"objects": objects, "camera": bpy.context.scene.camera.name, "frame": bpy.context.scene.frame_current}


def _render_pixels(path):
    scene = bpy.context.scene
    previous = scene.render.filepath
    scene.render.filepath = str(path)
    try:
        bpy.ops.render.render(write_still=True)
        image = bpy.data.images.load(str(path), check_existing=False)
        try:
            assert tuple(image.size) == (32, 32)
            return tuple(image.pixels)
        finally:
            bpy.data.images.remove(image)
    finally:
        scene.render.filepath = previous


def test_typed_copy_relocated_reopen_preserves_native_state_and_render(tmp_path):
    _scene_fixture()
    reference = _render_pixels(tmp_path / "reference.png")
    assert len(reference) == 32 * 32 * 4 and max(reference[::4]) > 0.0
    source = tmp_path / "source.blend"
    assert load_skill("blender-scene", "save_scene").main(filepath=str(source))["success"]
    original_bytes = source.read_bytes()
    expected = _scene_readback()
    assert len(expected["objects"]["PortableCube"]["keys"]) == 3
    target = tmp_path / "portable.blend"
    copy = load_skill("blender-portable-scene", "save_portable_scene_copy")

    result = copy.main(filepath=str(target), allowed_output_root=str(tmp_path), render_path=RELATIVE_RENDER)

    assert result["success"], result
    data = target.read_bytes()
    assert data.startswith(b"BLENDER")
    assert result["context"]["bytes"] == len(data)
    assert result["context"]["sha256"] == hashlib.sha256(data).hexdigest()
    assert b"portable-copy-fixture" not in data
    assert bpy.context.scene.render.filepath == PRIVATE_RENDER
    assert Path(bpy.data.filepath).resolve() == source.resolve()
    assert source.read_bytes() == original_bytes
    assert _scene_readback() == expected
    assert not list(tmp_path.glob(".blend-publish-*"))
    rejected = copy.main(filepath=str(target), allowed_output_root=str(tmp_path))
    assert rejected["success"] is False
    assert target.read_bytes() == data and _scene_readback() == expected

    relocated = tmp_path / "relocated"
    relocated.mkdir()
    delivered = relocated / target.name
    shutil.copyfile(str(target), str(delivered))
    source.unlink()
    target.unlink()
    assert load_skill("blender-scene", "open_scene").main(filepath=str(delivered))["success"]
    assert bpy.context.scene.render.filepath == RELATIVE_RENDER
    assert _scene_readback() == expected
    assert _render_pixels(relocated / "image.png") == reference


def test_native_file_browser_buffer_is_cleared_and_logically_restored(tmp_path):
    areas = [area for screen in bpy.data.screens for area in screen.areas]
    assert areas, "Factory startup did not provide native screen areas"
    areas[0].type = "FILE_BROWSER"
    params = areas[0].spaces.active.params
    if params is None:
        pytest.skip("Native file-browser params are not initialized in this background host")
    params.directory = PRIVATE_BROWSER
    bpy.context.scene.render.filepath = PRIVATE_RENDER
    target = tmp_path / "browser.blend"

    result = load_skill("blender-portable-scene", "save_portable_scene_copy").main(
        filepath=str(target), allowed_output_root=str(tmp_path), render_path=RELATIVE_RENDER
    )

    assert result["success"], result
    assert result["context"]["browser_directories_sanitized"] >= 1
    assert params.directory == PRIVATE_BROWSER
    assert bpy.context.scene.render.filepath == PRIVATE_RENDER
    assert b"portable-copy-fixture" not in target.read_bytes()
    assert load_skill("blender-scene", "open_scene").main(filepath=str(target))["success"]
    restored_browser = next(
        space.params
        for screen in bpy.data.screens
        for area in screen.areas
        for space in area.spaces
        if space.type == "FILE_BROWSER" and space.params is not None
    )
    assert restored_browser.directory == b"//"


def test_native_out_of_profile_dependency_does_not_publish(tmp_path):
    text = bpy.data.texts.new("UnsupportedScript")
    text.write("# Synthetic unsupported dependency\n")
    bpy.context.scene.render.filepath = PRIVATE_RENDER
    target = tmp_path / "rejected.blend"
    result = load_skill("blender-portable-scene", "save_portable_scene_copy").main(
        filepath=str(target), allowed_output_root=str(tmp_path)
    )
    assert result["success"] is False
    assert not target.exists() and not list(tmp_path.glob(".blend-publish-*"))
    assert bpy.context.scene.render.filepath == PRIVATE_RENDER
    assert bpy.data.texts.get(text.name) is text
