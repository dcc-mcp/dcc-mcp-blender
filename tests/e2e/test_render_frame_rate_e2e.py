"""Verify fractional render timebases against native Blender RNA, without rendering."""

from __future__ import annotations

import pytest

bpy = pytest.importorskip("bpy", reason="requires a real Blender interpreter")

from tests.e2e.conftest import load_skill  # noqa: E402

pytestmark = pytest.mark.e2e


@pytest.fixture
def scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    return bpy.context.scene


def test_fractional_rate_returns_actual_native_timebase(scene):
    result = load_skill("blender-render", "set_render_settings").main(fps=24, fps_base=1.001)

    assert result["success"] is True, result
    read = load_skill("blender-render", "get_render_info").main()
    assert read["success"] is True, read
    for context in (result["context"], read["context"]):
        assert context["fps"] == scene.render.fps == 24
        assert context["fps_base"] == scene.render.fps_base
        assert context["fps_base"] == pytest.approx(1.001)
        assert context["effective_fps"] == scene.render.fps / scene.render.fps_base
        assert context["effective_fps"] == pytest.approx(24000 / 1001)


def test_omitted_base_preserves_native_fractional_setting(scene):
    scene.render.fps_base = 1.001
    base = scene.render.fps_base

    result = load_skill("blender-render", "set_render_settings").main(fps=30)

    assert result["success"] is True, result
    assert scene.render.fps_base == base
    assert result["context"]["fps_base"] == base
    assert result["context"]["effective_fps"] == 30 / base


def test_explicit_unit_base_restores_integer_rate(scene):
    scene.render.fps_base = 1.001

    result = load_skill("blender-render", "set_render_settings").main(fps_base=1)

    assert result["success"] is True, result
    assert scene.render.fps == 24
    assert scene.render.fps_base == 1.0
    assert result["context"]["effective_fps"] == 24


@pytest.mark.parametrize(
    "invalid",
    [
        {"fps": True},
        {"fps": 0},
        {"fps": 23.976},
        {"fps": float("nan")},
        {"fps": float("inf")},
        {"fps": 32768},
        {"fps_base": True},
        {"fps_base": float("nan")},
        {"fps_base": float("inf")},
        {"fps_base": 0},
        {"fps_base": -1},
        {"fps_base": 1e-6},
        {"fps_base": 1000001},
    ],
)
def test_invalid_rate_never_mutates_native_settings(scene, invalid):
    render = scene.render
    before = (render.engine, render.resolution_x, render.resolution_y, render.fps, render.fps_base, render.filepath)
    params = dict(
        engine="BLENDER_WORKBENCH", resolution_x=640, resolution_y=360, fps=30, fps_base=1.001, output_path="//changed"
    )
    params.update(invalid)

    result = load_skill("blender-render", "set_render_settings").main(**params)

    assert result["success"] is False, result
    assert (
        render.engine,
        render.resolution_x,
        render.resolution_y,
        render.fps,
        render.fps_base,
        render.filepath,
    ) == before


@pytest.mark.parametrize("bound", ["hard_min", "hard_max"])
def test_native_rna_boundary_values_are_accepted_and_reported(scene, bound):
    render = scene.render
    fps = int(getattr(render.bl_rna.properties["fps"], bound))
    base = getattr(render.bl_rna.properties["fps_base"], bound)

    result = load_skill("blender-render", "set_render_settings").main(fps=fps, fps_base=base)

    assert result["success"] is True, result
    assert result["context"]["fps"] == render.fps == fps
    assert result["context"]["fps_base"] == render.fps_base == base
    assert result["context"]["effective_fps"] == fps / base
