"""E2E tests for the NLA tools, running inside a real Blender interpreter.

These exist because the mocked suite cannot tell a property name Blender
rejects from one it accepts: it is the same lesson the fluid tools taught.
Every assertion here reads state back off the Blender object, not off the
tool response, so a call that reports success without doing anything fails.
"""

from __future__ import annotations

import pytest

bpy = pytest.importorskip("bpy", reason="bpy not available - run inside Blender Python interpreter")

pytestmark = pytest.mark.e2e

from tests.e2e.conftest import load_skill  # noqa: E402


def _new_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def _cube(name="E2E Cube"):
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.active_object
    obj.name = name
    return obj


class TestNlaE2E:
    def setup_method(self):
        _new_scene()

    def _skill(self, name):
        return load_skill("blender-animation", name)

    def test_track_and_strip_round_trip(self):
        """add track -> add strip -> set strip -> remove strip."""
        obj = _cube()

        # An action has to exist before a strip can reference it.
        action = bpy.data.actions.new("E2E Action")

        add_track = self._skill("add_nla_track")
        result = add_track.add_nla_track(object_name=obj.name, track_name="Base")
        assert result["success"] is True, result.get("error")
        assert obj.animation_data is not None
        assert obj.animation_data.nla_tracks["Base"].name == "Base"

        add_strip = self._skill("add_nla_strip")
        result = add_strip.add_nla_strip(
            object_name=obj.name, action_name="E2E Action", track_name="Base", frame_start=12
        )
        assert result["success"] is True, result.get("error")

        track = obj.animation_data.nla_tracks["Base"]
        assert len(track.strips) == 1
        # Read the strip back off the object, not off the response.
        assert track.strips[0].frame_start == pytest.approx(12.0)
        assert track.strips[0].action is action

        set_strip = self._skill("set_nla_strip")
        result = set_strip.set_nla_strip(
            object_name=obj.name,
            strip_name="E2E Action",
            track_name="Base",
            frame_start=40,
            blend_type="ADD",
            influence=0.5,
            scale=2.0,
            muted=True,
        )
        assert result["success"] is True, result.get("error")
        strip = track.strips[0]
        assert strip.frame_start == pytest.approx(40.0)
        assert strip.blend_type == "ADD"
        assert strip.influence == pytest.approx(0.5)
        assert strip.scale == pytest.approx(2.0)
        assert strip.mute is True

        remove_strip = self._skill("remove_nla_strip")
        result = remove_strip.remove_nla_strip(object_name=obj.name, strip_name="E2E Action", track_name="Base")
        assert result["success"] is True, result.get("error")
        assert len(track.strips) == 0

    def test_missing_action_leaves_the_object_untouched(self):
        """A rejected add_nla_strip must not create animation data."""
        obj = _cube()
        assert obj.animation_data is None

        result = self._skill("add_nla_strip").add_nla_strip(
            object_name=obj.name, action_name="NoSuchAction", track_name="Base"
        )
        assert result["success"] is False
        assert obj.animation_data is None, "a rejected call must not create animation_data"

    def test_missing_track_leaves_the_object_untouched(self):
        obj = _cube()
        assert obj.animation_data is None
        bpy.data.actions.new("E2E Action")

        result = self._skill("add_nla_strip").add_nla_strip(
            object_name=obj.name, action_name="E2E Action", track_name="Ghost"
        )
        assert result["success"] is False
        assert obj.animation_data is None, "a rejected call must not create animation_data"

    def test_remove_track_drops_its_strips(self):
        obj = _cube()
        bpy.data.actions.new("E2E Action")
        self._skill("add_nla_track").add_nla_track(object_name=obj.name, track_name="Base")
        self._skill("add_nla_strip").add_nla_strip(
            object_name=obj.name, action_name="E2E Action", track_name="Base", frame_start=1
        )
        assert len(obj.animation_data.nla_tracks["Base"].strips) == 1

        result = self._skill("remove_nla_track").remove_nla_track(object_name=obj.name, track_name="Base")
        assert result["success"] is True, result.get("error")
        assert obj.animation_data.nla_tracks.get("Base") is None

    def test_list_tracks_reports_the_strip(self):
        obj = _cube()
        bpy.data.actions.new("E2E Action")
        self._skill("add_nla_track").add_nla_track(object_name=obj.name, track_name="Base")
        self._skill("add_nla_strip").add_nla_strip(
            object_name=obj.name, action_name="E2E Action", track_name="Base", frame_start=5
        )

        result = self._skill("list_nla_tracks").list_nla_tracks(object_name=obj.name)
        assert result["success"] is True
        assert result["context"]["count"] == 1
        strip = result["context"]["tracks"][0]["strips"][0]
        assert strip["action"] == "E2E Action"
        assert strip["frame_start"] == pytest.approx(5.0)


class TestActionFcurvesE2E:
    """Blender 5.x replaced Action.fcurves with layered animation.

    These tools therefore cannot work there. The tests assert the tools say so
    explicitly on 5.x, and behave correctly everywhere else, so a host without
    the API is never reported as an action with no curves.
    """

    def setup_method(self):
        _new_scene()

    def _skill(self, name):
        return load_skill("blender-animation", name)

    def _is_layered(self) -> bool:
        return not hasattr(bpy.types.Action, "fcurves")

    def test_extrapolation_is_written_to_the_curve(self):
        """Set extrapolation and read it back off the fcurve."""
        obj = _cube()
        obj.location = (0.0, 0.0, 0.0)
        obj.keyframe_insert(data_path="location", frame=1)
        obj.keyframe_insert(data_path="location", frame=10)
        action = obj.animation_data.action
        assert action is not None

        result = self._skill("list_action_fcurves").list_action_fcurves(action_name=action.name)
        if self._is_layered():
            # No shared accessor exists; the tool must refuse rather than
            # report an empty action.
            assert result["success"] is False
            assert "layered animation" in result["error"].lower()
            return

        assert result["success"] is True, result.get("error")
        assert len(action.fcurves) >= 1

        list_curves = self._skill("list_action_fcurves")
        result = list_curves.list_action_fcurves(action_name=action.name)
        assert result["success"] is True, result.get("error")
        assert result["context"]["count"] >= 1
        curve = result["context"]["fcurves"][0]
        assert curve["data_path"] == "location"
        assert curve["keyframe_count"] == 2
        assert curve["range"] == [pytest.approx(1.0), pytest.approx(10.0)]

        set_extrap = self._skill("set_action_fcurve_extrapolation")
        result = set_extrap.set_action_fcurve_extrapolation(
            action_name=action.name, extrapolation="CONSTANT", data_path="location"
        )
        assert result["success"] is True, result.get("error")
        # Read it back off the object: the response alone would not prove it.
        written = False
        for fcurve in action.fcurves:
            if fcurve.data_path == "location":
                assert fcurve.extrapolation == "CONSTANT"
                written = True
        assert written, "at least one location fcurve must have been updated"

    def test_extrapolation_rejects_unknown_values_before_writing(self):
        obj = _cube()
        obj.keyframe_insert(data_path="location", frame=1)
        action = obj.animation_data.action
        if self._is_layered():
            pytest.skip("no Action.fcurves on this Blender; covered by the refusal assertions")
        before = [fcurve.extrapolation for fcurve in action.fcurves]

        result = self._skill("set_action_fcurve_extrapolation").set_action_fcurve_extrapolation(
            action_name=action.name, extrapolation="LOOP"
        )
        assert result["success"] is False
        assert [fcurve.extrapolation for fcurve in action.fcurves] == before

    def test_list_actions_finds_the_active_action(self):
        obj = _cube()
        obj.keyframe_insert(data_path="location", frame=1)
        action = obj.animation_data.action
        assert action is not None

        result = self._skill("list_animation_actions").list_animation_actions(object_name=obj.name)
        assert result["success"] is True
        sources = {a["name"]: a["source"] for a in result["context"]["actions"]}
        assert sources.get(action.name) == "active"

    def test_list_actions_filters(self):
        bpy.data.actions.new("E2E Walk")
        bpy.data.actions.new("E2E Idle")

        result = self._skill("list_animation_actions").list_animation_actions(filter="walk")
        assert result["success"] is True
        assert [a["name"] for a in result["context"]["actions"]] == ["E2E Walk"]
