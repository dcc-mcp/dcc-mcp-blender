"""Native compositor ownership, editing and output semantics on 4.5 / 5.x.

Run inside an isolated Blender background process. Render fixtures use raw bpy;
all compositor setup, graph mutations and enable operations use typed tools.
"""

from __future__ import annotations

import math

import pytest

bpy = pytest.importorskip("bpy")
pytestmark = pytest.mark.e2e

from dcc_mcp_blender import _compositor_ops as comp  # noqa: E402
from dcc_mcp_blender import _node_graph_ops as graph  # noqa: E402


def _tree(scene=None):
    scene = scene or bpy.context.scene
    return scene.compositing_node_group if bpy.app.version >= (5, 0, 0) else scene.node_tree


def _enabled(scene=None):
    scene = scene or bpy.context.scene
    return scene.render.use_compositing if bpy.app.version >= (5, 0, 0) else scene.use_nodes


@pytest.fixture(autouse=True)
def empty_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def _ok(result):
    assert result["success"], result
    return result["context"]


def _state():
    tree = _tree()
    return (
        tree.as_pointer() if tree else None,
        _enabled(),
        tuple((n.name, n.bl_idname) for n in tree.nodes) if tree else (),
        tuple(
            (
                link.from_node.name,
                link.from_socket.identifier,
                link.to_node.name,
                link.to_socket.identifier,
                link.is_muted,
            )
            for link in tree.links
        )
        if tree
        else (),
    )


def test_native_compositor_create_read_update_remove_and_reopen(tmp_path):
    _ok(comp.setup_compositor_tree())
    tree = _tree()
    pointer = tree.as_pointer()
    output_type = "NodeGroupOutput" if bpy.app.version >= (5, 0, 0) else "CompositorNodeComposite"
    output = next(n for n in tree.nodes if n.bl_idname == output_type)
    _ok(comp.setup_compositor_tree())
    assert _tree().as_pointer() == pointer
    assert len(tree.nodes) == 2 and len(tree.links) == 1
    math_node = _ok(comp.create_compositor_node("math", name="Typed Math"))
    expected_math = "ShaderNodeMath" if bpy.app.version >= (5, 0, 0) else "CompositorNodeMath"
    assert math_node["node_type"] == expected_math
    assert math_node["node"]["bl_idname"] == expected_math
    _ok(comp.set_compositor_node_value("Typed Math", "Value", 0.25))
    assert _ok(comp.get_compositor_node_value("Typed Math", "Value"))["value"] == pytest.approx(0.25)
    _ok(comp.delete_compositor_node("Typed Math"))
    _ok(comp.create_compositor_node("blur", name="Typed Blur", location=[10, 20]))
    _ok(comp.set_compositor_node_value("Typed Blur", "Image", [0.8, 0.02, 0.01, 1]))
    value = _ok(comp.get_compositor_node_value("Typed Blur", "Image"))["value"]
    assert value == pytest.approx([0.8, 0.02, 0.01, 1])
    _ok(comp.connect_compositor_nodes("Typed Blur", "Image", output.name, output.inputs[0].identifier))
    assert any(link.from_node.name == "Typed Blur" for link in tree.links)
    assert _ok(graph.get_compositor_node_tree())["node_count"] == 3
    assert _ok(graph.list_nodes({"kind": "compositor"}))["count"] == 3
    _ok(comp.set_compositor_enabled(enabled=False))
    assert not _enabled() and _tree().as_pointer() == pointer
    if bpy.app.version >= (5, 0, 0):
        assert _ok(graph.get_compositor_node_tree())["node_count"] == 3
        assert _ok(graph.list_nodes({"kind": "compositor"}))["count"] == 3
        _ok(comp.list_compositor_node_links())
        assert not _enabled()
    _ok(comp.set_compositor_enabled(enabled=True))
    path = str(tmp_path / "compositor.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
    assert _enabled()
    assert _ok(comp.get_compositor_node_value("Typed Blur", "Image"))["value"] == pytest.approx(value)
    _ok(comp.disconnect_compositor_nodes(from_node="Typed Blur"))
    _ok(comp.delete_compositor_node("Typed Blur"))
    assert not any(n.name == "Typed Blur" for n in _tree().nodes)
    _ok(comp.clear_compositor_tree())
    assert len(_tree().nodes) == 0 and len(_tree().links) == 0


def test_native_invalid_calls_do_not_change_existing_graph():
    _ok(comp.setup_compositor_tree())
    _ok(comp.create_compositor_node("blur", name="Keep"))
    before = _state()
    for call in (
        lambda: comp.setup_compositor_tree(template="invalid", clear=True),
        lambda: comp.create_compositor_node("blur", name="Keep"),
        lambda: comp.create_compositor_node("blur", location=[math.nan, 0]),
        lambda: comp.create_compositor_node("CompositorNodeNotReal"),
        lambda: comp.connect_compositor_nodes("missing", "Image", "Keep", "Image"),
        lambda: comp.set_compositor_node_value("Keep", "missing", 1),
    ):
        result = call()
        assert not result["success"], result
        assert _state() == before


def test_native_named_scene_isolation():
    other = bpy.data.scenes.new("Other")
    _ok(comp.setup_compositor_tree(scene_name=other.name))
    _ok(comp.create_compositor_node("blur", name="Other Blur", scene_name=other.name))
    assert _tree() is None
    result = _ok(graph.list_nodes({"kind": "compositor", "scene_name": other.name}))
    assert result["count"] == 3
    render_layers = next(n for n in _tree(other).nodes if n.bl_idname == "CompositorNodeRLayers")
    if bpy.app.version >= (5, 0, 0):
        assert render_layers.scene == other


def test_native_modern_clear_does_not_destroy_shared_group():
    if bpy.app.version < (5, 0, 0):
        pytest.skip("Independent compositor groups were introduced in Blender 5.0")
    _ok(comp.setup_compositor_tree())
    original = _tree()
    other = bpy.data.scenes.new("Shared Other")
    other.compositing_node_group = original
    _ok(comp.setup_compositor_tree(template="empty", clear=True))
    assert _tree() != original
    assert other.compositing_node_group == original
    assert len(original.nodes) == 2 and len(_tree().nodes) == 0


def test_native_compositor_changes_decoded_output_pixels(tmp_path):
    scene = bpy.context.scene
    camera = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    scene.collection.objects.link(camera)
    scene.camera = camera
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 1
    scene.cycles.use_denoising = False
    scene.render.resolution_x = scene.render.resolution_y = 8
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Standard"
    scene.world = bpy.data.worlds.new("Black World")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0, 0, 0, 1)
    _ok(comp.setup_compositor_tree())
    _ok(comp.create_compositor_node("blur", name="Color Input"))
    _ok(comp.set_compositor_node_value("Color Input", "Image", [0.8, 0.02, 0.01, 1]))
    output = next(n for n in _tree().nodes if n.bl_idname in {"NodeGroupOutput", "CompositorNodeComposite"})
    _ok(comp.connect_compositor_nodes("Color Input", "Image", output.name, output.inputs[0].identifier))

    def render_pixels(name):
        scene.render.filepath = str(tmp_path / name)
        bpy.ops.render.render(write_still=True)
        image = bpy.data.images.load(scene.render.filepath, check_existing=False)
        try:
            assert tuple(image.size) == (8, 8)
            pixels = list(image.pixels)
            assert len(pixels) == 8 * 8 * 4 and all(math.isfinite(v) for v in pixels)
            return pixels
        finally:
            bpy.data.images.remove(image)

    enabled = render_pixels("enabled.png")
    _ok(comp.set_compositor_enabled(enabled=False))
    disabled = render_pixels("disabled.png")
    assert max(enabled[::4]) > 0.5
    assert max(disabled[::4]) < 0.05
    assert sum(enabled[::4]) > sum(disabled[::4]) + 16


def test_native_modern_active_output_and_muted_link_failure():
    if bpy.app.version < (5, 0, 0):
        pytest.skip("Independent compositor groups were introduced in Blender 5.0")
    _ok(comp.setup_compositor_tree())
    tree = _tree()
    inactive = tree.nodes.get("Composite")
    active = tree.nodes.new("NodeGroupOutput")
    active.name = "Active Output"
    active.is_active_output = True
    assert active.inputs[0].identifier != active.inputs[0].name
    _ok(comp.setup_compositor_tree())
    assert active.is_active_output and not inactive.is_active_output
    assert any(link.to_node == active for link in tree.links)
    # An invalid first output is preflighted without touching unrelated links.
    original = next(iter(tree.links))
    original.is_muted = True
    tree.interface.new_socket(name="Invalid", in_out="OUTPUT", socket_type="NodeSocketFloat")
    invalid = next(item for item in tree.interface.items_tree if item.name == "Invalid")
    tree.interface.move(invalid, 0)
    before = _state()
    assert not comp.setup_compositor_tree()["success"]
    assert _state() == before
    assert original.is_muted
