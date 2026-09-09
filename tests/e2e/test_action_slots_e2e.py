"""Verify action-slot isolation through the public animation tools."""

from __future__ import annotations

import pytest

bpy = pytest.importorskip("bpy", reason="Requires native Blender")
pytestmark = pytest.mark.e2e

from tests.e2e.conftest import load_skill  # noqa: E402


def test_shared_action_query_and_delete_preserve_other_object_slot():
    if bpy.app.version < (4, 4, 0):
        pytest.skip("Action Slots were introduced in Blender 4.4")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    first = bpy.data.objects.new("SlotOwnerA", None)
    second = bpy.data.objects.new("SlotOwnerB", None)
    for obj in (first, second):
        bpy.context.scene.collection.objects.link(obj)
    first.keyframe_insert(data_path="location", frame=1)
    action = first.animation_data.action
    second.animation_data_create()
    second.animation_data.action = action
    second.animation_data.action_slot = action.slots.new(id_type="OBJECT", name=second.name)
    second.keyframe_insert(data_path="location", frame=7)

    query = load_skill("blender-animation", "get_keyframes")
    result = query.main(object_name=first.name)
    assert result["success"], result
    assert result["context"]["keyframe_count"] == 3
    assert all(curve["frames"] == [1.0] for curve in result["context"]["fcurves"])

    delete = load_skill("blender-animation", "delete_keyframes")
    deleted = delete.main(object_name=first.name)
    assert deleted["success"], deleted
    assert deleted["context"]["deleted_count"] == 3
    assert query.main(object_name=first.name)["context"]["keyframe_count"] == 0
    untouched = query.main(object_name=second.name)
    assert untouched["context"]["keyframe_count"] == 3
    assert all(curve["frames"] == [7.0] for curve in untouched["context"]["fcurves"])
