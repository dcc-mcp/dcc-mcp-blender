"""Scoped physics-cache operations must not touch unrelated objects or dry runs."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.conftest import load_and_call


class Objects(list):
    def get(self, name):
        return next((item for item in self if item.name == name), None)


def host():
    objects = Objects()
    for name in ("Target", "Unrelated"):
        cache = SimpleNamespace(frame_start=1, frame_end=250, is_baked=False, use_disk_cache=False)
        modifier = SimpleNamespace(name="Cloth", type="CLOTH", point_cache=cache)
        obj = SimpleNamespace(name=name, modifiers=Objects([modifier]), select_set=Mock())
        objects.append(obj)
    scene = SimpleNamespace(frame_start=1, frame_end=250, frame_current=7, objects=objects)
    current = {}

    @contextmanager
    def override(**kwargs):
        assert "point_cache" in kwargs
        assert kwargs["object"] is kwargs["active_object"]
        current.update(kwargs)
        try:
            yield
        finally:
            current.clear()

    def bake(**kwargs):
        assert kwargs == {"bake": True}
        current["point_cache"].is_baked = True
        return {"FINISHED"}

    def clear():
        current["point_cache"].is_baked = False
        return {"FINISHED"}

    bake_op = Mock(side_effect=bake)
    bake_op.poll.return_value = True
    clear_op = Mock(side_effect=clear)
    clear_op.poll.return_value = True

    def global_bake(**kwargs):
        for obj in objects:
            obj.modifiers[0].point_cache.is_baked = True
        return {"FINISHED"}

    def global_clear():
        for obj in objects:
            obj.modifiers[0].point_cache.is_baked = False
        return {"FINISHED"}

    return SimpleNamespace(
        data=SimpleNamespace(objects=objects),
        context=SimpleNamespace(
            scene=scene,
            temp_override=Mock(side_effect=override),
            view_layer=SimpleNamespace(objects=SimpleNamespace(active=objects[1])),
        ),
        ops=SimpleNamespace(
            object=SimpleNamespace(select_all=Mock()),
            ptcache=SimpleNamespace(
                bake=bake_op,
                free_bake=clear_op,
                bake_all=Mock(side_effect=global_bake),
                free_bake_all=Mock(side_effect=global_clear),
            ),
        ),
    )


def call(tool, bpy, **kwargs):
    return load_and_call("blender-physics/scripts/{}.py".format(tool), bpy, **kwargs)


def cache(bpy, name="Target"):
    return bpy.data.objects.get(name).modifiers[0].point_cache


def test_bake_dry_run_leaves_cache_and_scene_frames_untouched():
    bpy = host()
    before = vars(cache(bpy)).copy(), vars(cache(bpy, "Unrelated")).copy(), vars(bpy.context.scene).copy()
    result = call(
        "bake_simulation", bpy, object_name="Target", modifier_name="Cloth", frame_start=5, frame_end=10, dry_run=True
    )
    assert result["success"] is True
    assert (vars(cache(bpy)), vars(cache(bpy, "Unrelated")), vars(bpy.context.scene)) == before
    assert result["context"]["targets"][0]["planned"] == {"frame_start": 5, "frame_end": 10}
    bpy.ops.ptcache.bake.assert_not_called()
    bpy.ops.ptcache.bake_all.assert_not_called()
    bpy.context.temp_override.assert_not_called()


def test_bake_only_updates_requested_cache_and_preserves_scene_range():
    bpy = host()
    result = call("bake_simulation", bpy, object_name="Target", modifier_name="Cloth", frame_start=1, frame_end=2)
    assert result["success"] is True, result
    assert cache(bpy).is_baked is True
    assert cache(bpy).frame_end == 2
    assert vars(cache(bpy, "Unrelated")) == dict(frame_start=1, frame_end=250, is_baked=False, use_disk_cache=False)
    assert (bpy.context.scene.frame_start, bpy.context.scene.frame_end, bpy.context.scene.frame_current) == (1, 250, 7)
    bpy.ops.ptcache.bake.assert_called_once_with(bake=True)
    bpy.ops.ptcache.bake_all.assert_not_called()
    assert result["context"]["targets"][0]["after"]["is_baked"] is True


def test_clear_only_frees_requested_cache():
    bpy = host()
    cache(bpy).is_baked = cache(bpy, "Unrelated").is_baked = True
    result = call("clear_simulation_cache", bpy, object_name="Target", modifier_name="Cloth")
    assert result["success"] is True, result
    assert cache(bpy).is_baked is False
    assert cache(bpy, "Unrelated").is_baked is True
    bpy.ops.ptcache.free_bake.assert_called_once_with()
    bpy.ops.ptcache.free_bake_all.assert_not_called()


def test_clear_dry_run_does_not_change_bake_state():
    bpy = host()
    cache(bpy).is_baked = True
    result = call("clear_simulation_cache", bpy, object_name="Target", dry_run=True)
    assert result["success"] is True
    assert cache(bpy).is_baked is True
    bpy.ops.ptcache.free_bake.assert_not_called()
    bpy.ops.ptcache.free_bake_all.assert_not_called()
    bpy.context.temp_override.assert_not_called()


@pytest.mark.parametrize("tool", ["bake_simulation", "clear_simulation_cache"])
def test_unsupported_cache_preflight_stops_all_targets_before_mutation(tool):
    bpy = host()
    bpy.data.objects.get("Unrelated").modifiers[0].type = "FLUID"
    result = call(tool, bpy)
    assert result["success"] is False
    assert cache(bpy).is_baked is False
    bpy.ops.ptcache.bake.assert_not_called()
    bpy.ops.ptcache.free_bake.assert_not_called()
    bpy.ops.ptcache.bake_all.assert_not_called()
    bpy.ops.ptcache.free_bake_all.assert_not_called()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"frame_start": 10, "frame_end": 2},
        {"frame_start": True},
        {"frame_end": 0},
        {"frame_end": 1048575},
        {"dry_run": "false"},
        {"object_name": ""},
        {"modifier_name": ""},
    ],
)
def test_invalid_requests_fail_before_mutation(kwargs):
    bpy = host()
    result = call("bake_simulation", bpy, **kwargs)
    assert result["success"] is False
    assert cache(bpy).frame_end == 250
    bpy.ops.ptcache.bake.assert_not_called()
    bpy.ops.ptcache.bake_all.assert_not_called()


def test_missing_scoped_context_support_fails_closed():
    bpy = host()
    bpy.context.temp_override = None
    result = call("bake_simulation", bpy, object_name="Target", frame_end=2)
    assert result["success"] is False
    assert cache(bpy).frame_end == 250
    bpy.ops.ptcache.bake_all.assert_not_called()


def test_operator_cancelled_or_unverified_does_not_report_success():
    for returned in ({"CANCELLED"}, {"FINISHED"}):
        bpy = host()
        bpy.ops.ptcache.bake.side_effect = None
        bpy.ops.ptcache.bake.return_value = returned
        result = call("bake_simulation", bpy, object_name="Target", frame_end=2)
        assert result["success"] is False
        assert result["context"]["targets"][0]["after"]["is_baked"] is False
        bpy.ops.ptcache.bake_all.assert_not_called()


def test_second_target_poll_failure_does_not_modify_first():
    bpy = host()
    bpy.ops.ptcache.bake.poll.side_effect = [True, False]
    result = call("bake_simulation", bpy, frame_end=2)
    assert result["success"] is False
    assert cache(bpy).frame_end == 250
    bpy.ops.ptcache.bake.assert_not_called()


def test_scene_wide_selection_excludes_objects_in_other_scenes():
    bpy = host()
    bpy.context.scene.objects = Objects([bpy.data.objects.get("Target")])
    result = call("bake_simulation", bpy, frame_end=2)
    assert result["success"] is True, result
    assert result["context"]["count"] == 1
    assert cache(bpy, "Unrelated").is_baked is False
    assert call("bake_simulation", bpy, object_name="Unrelated")["success"] is False


def test_modifier_name_also_limits_scope_within_one_object():
    bpy = host()
    extra = SimpleNamespace(
        name="OtherCloth",
        type="CLOTH",
        point_cache=SimpleNamespace(frame_start=1, frame_end=250, is_baked=False, use_disk_cache=False),
    )
    bpy.data.objects.get("Target").modifiers.append(extra)
    result = call("bake_simulation", bpy, object_name="Target", modifier_name="Cloth", frame_end=2)
    assert result["success"] is True
    assert extra.point_cache.is_baked is False
    assert extra.point_cache.frame_end == 250


def test_partial_failure_reports_completed_target_without_retrying():
    bpy = host()
    real_bake = bpy.ops.ptcache.bake.side_effect
    calls = []

    def fails_second(**kwargs):
        calls.append(kwargs)
        if len(calls) == 2:
            raise RuntimeError("Native bake failed")
        return real_bake(**kwargs)

    bpy.ops.ptcache.bake.side_effect = fails_second
    result = call("bake_simulation", bpy, frame_end=2)
    assert result["success"] is False
    assert result["context"]["completed_count"] == 1
    assert result["context"]["mutation_state"] == "partial_or_unknown"
    assert result["context"]["targets"][0]["status"] == "completed"
    assert result["context"]["targets"][1]["after"]["is_baked"] is False
    assert len(calls) == 2


def test_baked_cache_requires_explicit_clear_before_frame_changes():
    bpy = host()
    cache(bpy).is_baked = True
    result = call("bake_simulation", bpy, object_name="Target", frame_end=2)
    assert result["success"] is False
    assert cache(bpy).frame_end == 250
    bpy.ops.ptcache.bake.assert_not_called()


def test_clear_finished_without_clearing_baked_flag_is_failure():
    bpy = host()
    cache(bpy).is_baked = True
    bpy.ops.ptcache.free_bake.side_effect = None
    bpy.ops.ptcache.free_bake.return_value = {"FINISHED"}
    result = call("clear_simulation_cache", bpy, object_name="Target")
    assert result["success"] is False
    assert result["context"]["targets"][0]["after"]["is_baked"] is True
