"""Native RNA/saved-scene acceptance for render CPU threads, without rendering.

These tests require a real supported Blender host. Mock unit tests do not
substitute for this boundary, and no process-wide CPU cap is asserted here.
Run in a process without a positive -t/--threads override; factory scene reset
does not remove a process override. Test override diagnostics separately.
"""

from __future__ import annotations

import pytest

bpy = pytest.importorskip("bpy", reason="requires a real Blender interpreter")

from tests.e2e.conftest import load_skill  # noqa: E402

pytestmark = pytest.mark.e2e


@pytest.fixture
def scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    return bpy.context.scene


def _set(**params):
    return load_skill("blender-render", "set_render_settings").main(**params)


def _assert_readback(result, mode, count=None):
    assert result["success"] is True, result
    if count is None:
        count = bpy.context.scene.render.threads
    read = load_skill("blender-render", "get_render_info").main()
    assert read["success"] is True, read
    for context in (result["context"], read["context"]):
        assert context["threads_mode"] == bpy.context.scene.render.threads_mode == mode
        assert context["threads"] == bpy.context.scene.render.threads == count


def test_native_switch_fixed_auto_and_omission(scene):
    _assert_readback(_set(threads=2), "FIXED", 2)
    _assert_readback(_set(resolution_x=640), "FIXED", 2)
    _assert_readback(_set(threads_mode="AUTO"), "AUTO")
    _assert_readback(_set(resolution_x=320), "AUTO")
    _assert_readback(_set(threads_mode="FIXED", threads=4), "FIXED", 4)


@pytest.mark.parametrize("bound", ["hard_min", "hard_max"])
def test_native_rna_boundaries_are_retained_without_clamping(scene, bound):
    count = getattr(scene.render.bl_rna.properties["threads"], bound)
    _assert_readback(_set(threads=count), "FIXED", count)


@pytest.mark.parametrize(
    "params",
    [
        {"threads": True},
        {"threads": 0},
        {"threads": -1},
        {"threads": 2.0},
        {"threads": "2"},
        {"threads": float("nan")},
        {"threads": float("inf")},
        {"threads_mode": "fixed"},
        {"threads_mode": "FIXED"},
        {"threads_mode": "AUTO", "threads": 2},
    ],
)
def test_invalid_threads_preserve_native_scene_settings(scene, params):
    render = scene.render
    before = (render.engine, render.resolution_x, render.fps, render.filepath, render.threads_mode, render.threads)
    result = _set(engine="BLENDER_WORKBENCH", resolution_x=640, fps=30, output_path="//changed", **params)
    assert result["success"] is False, result
    assert (
        render.engine,
        render.resolution_x,
        render.fps,
        render.filepath,
        render.threads_mode,
        render.threads,
    ) == before


def test_above_native_maximum_is_rejected_without_mutation(scene):
    render = scene.render
    before = (render.resolution_x, render.threads_mode, render.threads)
    result = _set(resolution_x=640, threads=render.bl_rna.properties["threads"].hard_max + 1)
    assert result["success"] is False, result
    assert (render.resolution_x, render.threads_mode, render.threads) == before


@pytest.mark.parametrize("mode", ["FIXED", "AUTO"])
def test_thread_settings_survive_native_save_reopen(scene, tmp_path, mode):
    _assert_readback(_set(threads=4), "FIXED", 4)
    if mode == "AUTO":
        _assert_readback(_set(threads_mode="AUTO"), "AUTO")
    expected_count = scene.render.threads
    path = str(tmp_path / "render-thread-settings.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    _assert_readback(_set(threads=2), "FIXED", 2)
    bpy.ops.wm.open_mainfile(filepath=path)
    read = load_skill("blender-render", "get_render_info").main()
    _assert_readback(read, mode, expected_count)
    # Only a test inspects saved count by changing mode: the production tool
    # never probes hidden state this way or assumes AUTO readback is storage.
    bpy.context.scene.render.threads_mode = "FIXED"
    assert bpy.context.scene.render.threads == 4
