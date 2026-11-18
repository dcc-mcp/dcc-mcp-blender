"""Exercise photographic post and delivery in native Blender."""

from __future__ import annotations

import pytest

bpy = pytest.importorskip("bpy", reason="requires a real Blender interpreter")

import dcc_mcp_blender._photographic_post_ops as post_ops  # noqa: E402
from dcc_mcp_blender._compositor_compat import modern_compositor  # noqa: E402
from dcc_mcp_blender._photographic_post_ops import _output_node, _output_target  # noqa: E402
from tests.e2e.conftest import load_skill  # noqa: E402

pytestmark = pytest.mark.e2e


@pytest.fixture
def scene():
    if tuple(bpy.app.version) < (5, 0, 0):
        pytest.skip("the photographic finish targets Blender 5")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    return bpy.context.scene


def test_photographic_post_round_trip(scene):
    configure = load_skill("blender-photographic-post", "configure_photographic_post")
    validate = load_skill("blender-photographic-post", "validate_photographic_post")

    result = configure.main(grain_size=32, grain_seed=17)
    assert result["success"] is True, result
    report = validate.main()
    assert report["success"] is True, report
    assert report["context"]["valid"] is True, report

    image = bpy.data.images[result["context"]["grain_image"]]
    before = list(image.pixels[:4])
    scene.frame_set(2)
    after = list(image.pixels[:4])
    assert before != after


def test_photographic_post_failure_restores_existing_stack(scene, monkeypatch):
    configure = load_skill("blender-photographic-post", "configure_photographic_post")
    validate = load_skill("blender-photographic-post", "validate_photographic_post")

    first = configure.main(grain_size=32, grain_seed=17)
    assert first["success"] is True, first
    tree = scene.compositing_node_group
    output = _output_node(tree, modern_compositor(bpy, scene))
    target = _output_target(tree, output, modern_compositor(bpy, scene))
    before_nodes = sorted(node.name for node in tree.nodes if node.name.startswith("DCC Photo Post "))
    before_source = target.links[0].from_node.name
    before_properties = {
        key: scene.get(key)
        for key in (
            "dcc_mcp_photographic_post_contract",
            "dcc_mcp_photographic_post_settings",
            "dcc_mcp_photographic_post_grain",
        )
    }
    original_new_node = post_ops._new_node

    def failing_new_node(tree, node_type, name, location):
        if "Candidate S Curve" in name:
            raise RuntimeError("injected compositor failure")
        return original_new_node(tree, node_type, name, location)

    monkeypatch.setattr(post_ops, "_new_node", failing_new_node)
    failed = configure.main(grain_size=32, grain_seed=18)

    assert failed["success"] is False, failed
    assert sorted(node.name for node in tree.nodes if node.name.startswith("DCC Photo Post ")) == before_nodes
    assert target.links[0].from_node.name == before_source
    assert {key: scene.get(key) for key in before_properties} == before_properties
    report = validate.main()
    assert report["success"] is True and report["context"]["valid"] is True, report


def test_photographic_video_output_round_trip(scene, tmp_path):
    configure = load_skill("blender-photographic-delivery", "configure_photographic_video_output")
    validate = load_skill("blender-photographic-delivery", "validate_photographic_video_output")

    result = configure.main(filepath=str(tmp_path / "toy.mp4"))
    assert result["success"] is True, result
    report = validate.main()
    assert report["success"] is True, report
    assert report["context"]["actual"]["custom_constant_rate_factor"] == 15
