"""Tiny, isolated real-host cache scope regressions (two quads, two frames)."""

from __future__ import annotations

import pytest

from dcc_mcp_blender._physics_ops import bake_simulation, clear_simulation_cache

bpy = pytest.importorskip("bpy")

pytestmark = pytest.mark.e2e


@pytest.fixture
def cloth_pair():
    objects = []
    meshes = []
    for index in range(2):
        mesh = bpy.data.meshes.new("ScopeTestMesh")
        mesh.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [], [(0, 1, 2, 3)])
        obj = bpy.data.objects.new("ScopeTestCloth", mesh)
        bpy.context.scene.collection.objects.link(obj)
        obj.location.x = index * 3
        modifier = obj.modifiers.new("ScopeTestCloth", "CLOTH")
        modifier.settings.quality = 1
        modifier.point_cache.frame_start = 1
        modifier.point_cache.frame_end = 2
        objects.append(obj)
        meshes.append(mesh)
    bpy.context.view_layer.objects.active = objects[1]
    try:
        yield objects
    finally:
        for obj in objects:
            bpy.data.objects.remove(obj, do_unlink=True)
        for mesh in meshes:
            bpy.data.meshes.remove(mesh)


def _state(objects):
    return {
        "scene_range": (bpy.context.scene.frame_start, bpy.context.scene.frame_end),
        "frame": bpy.context.scene.frame_current,
        "active": bpy.context.view_layer.objects.active.name,
        "selected": sorted(obj.name for obj in bpy.context.selected_objects),
        "caches": [
            (
                obj.modifiers[0].point_cache.frame_start,
                obj.modifiers[0].point_cache.frame_end,
                obj.modifiers[0].point_cache.is_baked,
            )
            for obj in objects
        ],
    }


def test_dry_run_does_not_change_host_state(cloth_pair):
    before = _state(cloth_pair)
    first = cloth_pair[0]
    result = bake_simulation(first.name, first.modifiers[0].name, frame_start=5, frame_end=6, dry_run=True)
    assert result["success"] is True, result
    assert _state(cloth_pair) == before
    result = clear_simulation_cache(first.name, first.modifiers[0].name, dry_run=True)
    assert result["success"] is True, result
    assert _state(cloth_pair) == before


def test_bake_and_free_preserve_unrelated_cache(cloth_pair):
    first, second = cloth_pair
    before = _state(cloth_pair)
    result = bake_simulation(first.name, first.modifiers[0].name, frame_start=1, frame_end=2)
    assert result["success"] is True, result
    assert first.modifiers[0].point_cache.is_baked
    assert not second.modifiers[0].point_cache.is_baked
    after = _state(cloth_pair)
    assert {key: value for key, value in after.items() if key != "caches"} == {
        key: value for key, value in before.items() if key != "caches"
    }
    result = bake_simulation(second.name, second.modifiers[0].name, frame_start=1, frame_end=2)
    assert result["success"] is True, result
    assert second.modifiers[0].point_cache.is_baked
    result = clear_simulation_cache(first.name, first.modifiers[0].name)
    assert result["success"] is True, result
    assert not first.modifiers[0].point_cache.is_baked
    assert second.modifiers[0].point_cache.is_baked
    assert result["context"]["targets"][0]["after"]["is_baked"] is False


def test_unsupported_cache_fails_without_mutating_supported_target(cloth_pair):
    first, second = cloth_pair
    second.modifiers.new("ScopeTestCollision", "COLLISION")
    before = _state(cloth_pair)
    result = bake_simulation(second.name, frame_start=5, frame_end=6)
    assert result["success"] is False
    assert result["context"]["mutation_state"] == "none"
    assert _state(cloth_pair) == before
    assert not first.modifiers[0].point_cache.is_baked
