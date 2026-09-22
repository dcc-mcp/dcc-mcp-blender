"""Unit tests for the NLA tools (bpy mocked)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import yaml

from tests.conftest import load_and_call, make_mock_bpy

ANIMATION_PATH = "src/dcc_mcp_blender/skills/blender-animation/tools.yaml"
SKILL = "blender-animation"


# ---------------------------------------------------------------------------
# Fake NLA graph
# ---------------------------------------------------------------------------


class _KeyframePoint:
    def __init__(self, frame: float, value: float = 0.0):
        self.co = SimpleNamespace(x=frame, y=value)


class _Fcurve:
    def __init__(self, data_path: str, index: int = 0, frames=()):
        self.data_path = data_path
        self.array_index = index
        self.keyframe_points = list([_KeyframePoint(frame) for frame in frames])
        self.extrapolation = "LINEAR"


class _Action:
    def __init__(self, name: str, fcurves=()):
        self.name = name
        self.fcurves = list(fcurves)
        self.frame_range = (1.0, 10.0)


class _Strip:
    def __init__(self, name: str, action: _Action, frame_start: float):
        self.name = name
        self.action = action
        self.frame_start = frame_start
        self.frame_end = frame_start + 10.0
        self.action_frame_start = 1.0
        self.action_frame_end = 10.0
        self.blend_type = "REPLACE"
        self.extrapolation = "HOLD"
        self.mute = False
        self.influence = 1.0
        self.repeat = 1.0
        self.scale = 1.0


class _StripCollection(list):
    def new(self, name, frame_start, action):
        strip = _Strip(name, action, frame_start)
        self.append(strip)
        return strip

    def remove(self, strip):
        self.remove_item(strip)

    def remove_item(self, strip):
        list.remove(self, strip)


class _Track:
    def __init__(self, name: str = "NlaTrack"):
        self.name = name
        self.mute = False
        self.is_solo = False
        self.strips = _StripCollection()


class _TrackCollection(list):
    _counter = [0]

    def new(self):
        self._counter[0] += 1
        track = _Track(f"NlaTrack.{self._counter[0]:03d}")
        self.append(track)
        return track

    def remove(self, track):
        list.remove(self, track)

    def get(self, name):
        for track in self:
            if track.name == name:
                return track
        return None


class _ActionCollection(list):
    def get(self, name):
        for action in self:
            if action.name == name:
                return action
        return None


def _make_object(name="Cube", animation_data=None):
    obj = MagicMock()
    obj.name = name
    obj.type = "MESH"
    obj.animation_data = animation_data
    return obj


class _ObjectCollection(list):
    """Mimics bpy.data.objects: list-like with a .get() lookup."""

    def get(self, name):
        for obj in self:
            if getattr(obj, "name", None) == name:
                return obj
        return None


def _bpy_with_objects(*objects, actions=()):
    bpy = make_mock_bpy()
    bpy.data.objects = _ObjectCollection(objects)
    bpy.data.actions = _ActionCollection(actions)
    bpy.context.scene.frame_current = 1
    return bpy


def _call(script, bpy, **kwargs):
    return load_and_call(f"{SKILL}/scripts/{script}.py", bpy, **kwargs)


def _object_with_tracks(name="Cube"):
    data = SimpleNamespace(
        action=None,
        nla_tracks=_TrackCollection(),
        animation_data_create=lambda: None,
    )
    return _make_object(name, data)


# ---------------------------------------------------------------------------
# Tracks
# ---------------------------------------------------------------------------


def test_add_nla_track_creates_a_track():
    obj = _object_with_tracks()
    result = _call("add_nla_track", _bpy_with_objects(obj), object_name="Cube", track_name="Base")

    assert result["success"] is True
    assert obj.animation_data.nla_tracks.get("Base") is not None
    assert result["context"]["track"]["name"] == "Base"


def test_add_nla_track_reports_a_missing_object():
    result = _call("add_nla_track", _bpy_with_objects(), object_name="Ghost")
    assert result["success"] is False
    assert "object not found" in result["message"].lower()


def test_list_nla_tracks_reports_strips():
    obj = _object_with_tracks()
    _call("add_nla_track", _bpy_with_objects(obj), object_name="Cube", track_name="Base")
    track = obj.animation_data.nla_tracks.get("Base")
    action = _Action("Walk")
    track.strips.new("Walk Strip", 1, action)

    result = _call("list_nla_tracks", _bpy_with_objects(obj), object_name="Cube")
    assert result["success"] is True
    assert result["context"]["count"] == 1
    track_ctx = result["context"]["tracks"][0]
    assert track_ctx["name"] == "Base"
    assert track_ctx["strips"][0]["name"] == "Walk Strip"
    assert track_ctx["strips"][0]["action"] == "Walk"


def test_remove_nla_track_removes_it():
    obj = _object_with_tracks()
    _call("add_nla_track", _bpy_with_objects(obj), object_name="Cube", track_name="Base")

    result = _call("remove_nla_track", _bpy_with_objects(obj), object_name="Cube", track_name="Base")
    assert result["success"] is True
    assert obj.animation_data.nla_tracks.get("Base") is None


def test_remove_nla_track_reports_a_missing_track():
    obj = _object_with_tracks()
    result = _call("remove_nla_track", _bpy_with_objects(obj), object_name="Cube", track_name="Ghost")
    assert result["success"] is False
    assert "track not found" in result["message"].lower()


# ---------------------------------------------------------------------------
# Strips
# ---------------------------------------------------------------------------


def test_add_nla_strip_places_an_action():
    obj = _object_with_tracks()
    action = _Action("Walk")
    bpy = _bpy_with_objects(obj, actions=[action])
    _call("add_nla_track", bpy, object_name="Cube", track_name="Base")

    result = _call(
        "add_nla_strip",
        bpy,
        object_name="Cube",
        action_name="Walk",
        track_name="Base",
        frame_start=12,
    )
    assert result["success"] is True, result.get("error")
    track = obj.animation_data.nla_tracks.get("Base")
    assert len(track.strips) == 1
    assert track.strips[0].action is action
    assert track.strips[0].frame_start == 12
    assert result["context"]["strip"]["action"] == "Walk"


def test_add_nla_strip_creates_a_track_when_none_exists():
    obj = _object_with_tracks()
    action = _Action("Idle")

    result = _call(
        "add_nla_strip",
        _bpy_with_objects(obj, actions=[action]),
        object_name="Cube",
        action_name="Idle",
    )
    assert result["success"] is True, result.get("error")
    assert len(obj.animation_data.nla_tracks) == 1


def test_add_nla_strip_reports_a_missing_action():
    obj = _object_with_tracks()
    result = _call(
        "add_nla_strip",
        _bpy_with_objects(obj),
        object_name="Cube",
        action_name="Ghost",
        track_name="Base",
    )
    assert result["success"] is False
    assert "action not found" in result["message"].lower()
    assert len(obj.animation_data.nla_tracks) == 0, "no track may be created for a missing action"


def test_set_nla_strip_updates_timing_and_blending():
    obj = _object_with_tracks()
    action = _Action("Walk")
    bpy = _bpy_with_objects(obj, actions=[action])
    _call("add_nla_track", bpy, object_name="Cube", track_name="Base")
    _call("add_nla_strip", bpy, object_name="Cube", action_name="Walk", track_name="Base", frame_start=1)

    result = _call(
        "set_nla_strip",
        bpy,
        object_name="Cube",
        strip_name="Walk",
        track_name="Base",
        frame_start=20,
        blend_type="add",
        influence=0.5,
        muted=True,
        scale=2.0,
    )
    assert result["success"] is True, result.get("error")
    strip = obj.animation_data.nla_tracks.get("Base").strips[0]
    assert strip.frame_start == 20
    assert strip.blend_type == "ADD"
    assert strip.influence == 0.5
    assert strip.mute is True
    assert strip.scale == 2.0


def test_set_nla_strip_searches_every_track_when_none_named():
    obj = _object_with_tracks()
    action = _Action("Walk")
    bpy = _bpy_with_objects(obj, actions=[action])
    _call("add_nla_track", bpy, object_name="Cube", track_name="Base")
    _call("add_nla_strip", bpy, object_name="Cube", action_name="Walk", track_name="Base", frame_start=1)

    result = _call("set_nla_strip", bpy, object_name="Cube", strip_name="Walk", frame_start=33)
    assert result["success"] is True
    assert obj.animation_data.nla_tracks.get("Base").strips[0].frame_start == 33


def test_set_nla_strip_validates_ranges():
    obj = _object_with_tracks()
    action = _Action("Walk")
    bpy = _bpy_with_objects(obj, actions=[action])
    _call("add_nla_strip", bpy, object_name="Cube", action_name="Walk", track_name="Base", frame_start=1)

    for payload, needle in (
        ({"blend_type": "OVERLAY"}, "blend type"),
        ({"extrapolation": "LOOP"}, "extrapolation"),
        ({"influence": 1.5}, "influence"),
        ({"scale": 0.0}, "scale"),
        ({"repeat": 0.0}, "repeat"),
    ):
        result = _call("set_nla_strip", bpy, object_name="Cube", strip_name="Walk", **payload)
        assert result["success"] is False, payload
        assert needle in result["message"].lower(), payload


def test_set_nla_strip_requires_a_change():
    obj = _object_with_tracks()
    result = _call("set_nla_strip", _bpy_with_objects(obj), object_name="Cube", strip_name="Walk")
    assert result["success"] is False
    assert "no strip changes" in result["message"].lower()


def test_remove_nla_strip_removes_it():
    obj = _object_with_tracks()
    action = _Action("Walk")
    bpy = _bpy_with_objects(obj, actions=[action])
    _call("add_nla_track", bpy, object_name="Cube", track_name="Base")
    _call("add_nla_strip", bpy, object_name="Cube", action_name="Walk", track_name="Base", frame_start=1)

    result = _call("remove_nla_strip", bpy, object_name="Cube", strip_name="Walk", track_name="Base")
    assert result["success"] is True
    assert len(obj.animation_data.nla_tracks.get("Base").strips) == 0


def test_remove_nla_strip_reports_a_missing_strip():
    obj = _object_with_tracks()
    result = _call("remove_nla_strip", _bpy_with_objects(obj), object_name="Cube", strip_name="Ghost")
    assert result["success"] is False
    assert "strip not found" in result["message"].lower()


# ---------------------------------------------------------------------------
# Actions and fcurves
# ---------------------------------------------------------------------------


def test_list_animation_actions_lists_the_file():
    actions = [_Action("Walk"), _Action("Idle")]
    result = _call("list_animation_actions", _bpy_with_objects(actions=actions))
    assert result["success"] is True
    assert sorted(a["name"] for a in result["context"]["actions"]) == ["Idle", "Walk"]


def test_list_animation_actions_filters_by_name():
    actions = [_Action("Walk"), _Action("Idle")]
    result = _call("list_animation_actions", _bpy_with_objects(actions=actions), filter="wal")
    assert result["success"] is True
    assert [a["name"] for a in result["context"]["actions"]] == ["Walk"]


def test_list_animation_actions_for_one_object_includes_nla_actions():
    obj = _object_with_tracks()
    active = _Action("Active")
    nla_action = _Action("FromTrack")
    obj.animation_data.action = active
    track = _Track("Base")
    track.strips.new("Strip", 1, nla_action)
    obj.animation_data.nla_tracks = _TrackCollection([track])

    result = _call("list_animation_actions", _bpy_with_objects(obj), object_name="Cube")
    assert result["success"] is True
    sources = {a["name"]: a["source"] for a in result["context"]["actions"]}
    assert sources == {"Active": "active", "FromTrack": "nla:Base"}


def test_list_action_fcurves_reports_ranges():
    action = _Action("Walk", [_Fcurve("location", 0, frames=[1, 5, 9])])
    result = _call("list_action_fcurves", _bpy_with_objects(actions=[action]), action_name="Walk")

    assert result["success"] is True
    fcurve = result["context"]["fcurves"][0]
    assert fcurve["data_path"] == "location"
    assert fcurve["keyframe_count"] == 3
    assert fcurve["range"] == [1.0, 9.0]


def test_list_action_fcurves_reports_a_missing_action():
    result = _call("list_action_fcurves", _bpy_with_objects(), action_name="Ghost")
    assert result["success"] is False
    assert "action not found" in result["message"].lower()


def test_set_action_fcurve_extrapolation_updates_matching_curves():
    action = _Action(
        "Walk",
        [
            _Fcurve("location", 0, frames=[1, 5]),
            _Fcurve("location", 1, frames=[1, 5]),
            _Fcurve("rotation_euler", 0, frames=[1]),
        ],
    )
    result = _call(
        "set_action_fcurve_extrapolation",
        _bpy_with_objects(actions=[action]),
        action_name="Walk",
        extrapolation="constant",
        data_path="location",
        array_index=1,
    )
    assert result["success"] is True
    assert result["context"]["count"] == 1
    assert action.fcurves[1].extrapolation == "CONSTANT"
    assert action.fcurves[0].extrapolation == "LINEAR", "non-matching curves keep their mode"


def test_set_action_fcurve_extrapolation_rejects_bad_values():
    action = _Action("Walk", [_Fcurve("location", 0, frames=[1])])
    result = _call(
        "set_action_fcurve_extrapolation",
        _bpy_with_objects(actions=[action]),
        action_name="Walk",
        extrapolation="LOOP",
    )
    assert result["success"] is False
    assert "unsupported extrapolation" in result["message"].lower()


# ---------------------------------------------------------------------------
# Tool contract
# ---------------------------------------------------------------------------


def test_tools_yaml_declares_the_new_tools():
    doc = yaml.safe_load(Path(ANIMATION_PATH).read_text(encoding="utf-8"))
    tools = {tool["name"]: tool for tool in doc["tools"]}
    assert {
        "list_animation_actions",
        "list_nla_tracks",
        "add_nla_track",
        "remove_nla_track",
        "add_nla_strip",
        "set_nla_strip",
        "remove_nla_strip",
        "list_action_fcurves",
        "set_action_fcurve_extrapolation",
    }.issubset(tools)


def test_new_nla_tools_declare_required_contract_fields():
    doc = yaml.safe_load(Path(ANIMATION_PATH).read_text(encoding="utf-8"))
    tools = {tool["name"]: tool for tool in doc["tools"]}
    for name in (
        "list_animation_actions",
        "list_nla_tracks",
        "add_nla_track",
        "remove_nla_track",
        "add_nla_strip",
        "set_nla_strip",
        "remove_nla_strip",
        "list_action_fcurves",
        "set_action_fcurve_extrapolation",
    ):
        tool = tools[name]
        assert tool["execution"] == "sync", name
        assert tool["affinity"] == "main", name
        source = Path("src/dcc_mcp_blender/skills") / SKILL / tool["source_file"]
        assert source.is_file(), f"missing source script: {source}"


def test_destructive_flags_match_actual_side_effects():
    doc = yaml.safe_load(Path(ANIMATION_PATH).read_text(encoding="utf-8"))
    tools = {tool["name"]: tool for tool in doc["tools"]}
    destructive = {"remove_nla_track", "remove_nla_strip"}
    for name in (
        "list_animation_actions",
        "list_nla_tracks",
        "add_nla_track",
        "remove_nla_track",
        "add_nla_strip",
        "set_nla_strip",
        "remove_nla_strip",
        "list_action_fcurves",
        "set_action_fcurve_extrapolation",
    ):
        assert tools[name]["destructive"] is (name in destructive), name
        assert tools[name]["annotations"]["destructive_hint"] is (name in destructive), name
        assert tools[name]["read_only"] is tools[name]["annotations"]["read_only_hint"], name
