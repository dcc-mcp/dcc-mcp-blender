"""Blender NLA (Non-Linear Animation) operations.

The animation skill covers actions, keyframes, and frame ranges. This covers
the layer above: NLA tracks and strips that arrange actions over time, plus the
fcurves inside an action.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

# Blender's NLA track blending and extrapolation modes. Used for validation and
# for the error message, not as an allowlist on the data itself.
BLEND_TYPES = ("REPLACE", "ADD", "SUBTRACT", "MULTIPLY")
EXTRAPOLATION_TYPES = ("NOTHING", "HOLD", "HOLD_FORWARD")


def _iter_items(collection: Any) -> List[Any]:
    try:
        return list(collection)
    except TypeError:
        return []


def _find_named(collection: Any, name: Optional[str], kind: str) -> Tuple[Any, Optional[dict]]:
    """Return the named item, or the first one when no name is given."""
    items = _iter_items(collection)
    if name:
        getter = getattr(collection, "get", None)
        found = getter(name) if callable(getter) else None
        if found is None:
            for item in items:
                if getattr(item, "name", None) == name:
                    found = item
                    break
        if found is None:
            return None, skill_error(f"{kind} not found: {name}", f"No {kind.lower()} named '{name}'.")
        return found, None
    if not items:
        return None, skill_error(f"No {kind.lower()} available", f"The target has no {kind.lower()}.")
    return items[0], None


def _animated_object(bpy: Any, object_name: str) -> Tuple[Any, Optional[dict]]:
    """Resolve an object that can own animation data."""
    obj = bpy.data.objects.get(object_name) if hasattr(bpy.data, "objects") else None
    if obj is None:
        return None, skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
    if not hasattr(obj, "animation_data"):
        return None, skill_error(
            f"{object_name} cannot be animated",
            "The object exposes no animation_data slot.",
        )
    return obj, None


def _animation_data(obj: Any, create: bool) -> Any:
    """Return the object's animation_data, creating it when allowed."""
    data = getattr(obj, "animation_data", None)
    if data is None and create:
        data = obj.animation_data_create()
    return data


def _strip_context(strip: Any) -> Dict[str, Any]:
    return {
        "name": getattr(strip, "name", ""),
        "action": getattr(getattr(strip, "action", None), "name", None),
        "frame_start": getattr(strip, "frame_start", None),
        "frame_end": getattr(strip, "frame_end", None),
        "action_frame_start": getattr(strip, "action_frame_start", None),
        "action_frame_end": getattr(strip, "action_frame_end", None),
        "blend_type": getattr(strip, "blend_type", None),
        "extrapolation": getattr(strip, "extrapolation", None),
        "muted": bool(getattr(strip, "mute", False)),
        "influence": getattr(strip, "influence", None),
        "repeat": getattr(strip, "repeat", None),
        "scale": getattr(strip, "scale", None),
    }


def _track_context(track: Any) -> Dict[str, Any]:
    return {
        "name": getattr(track, "name", ""),
        "muted": bool(getattr(track, "mute", False)),
        "is_solo": bool(getattr(track, "is_solo", False)),
        "strips": [_strip_context(strip) for strip in _iter_items(getattr(track, "strips", []))],
    }


def list_animation_actions(object_name: Optional[str] = None, filter: Optional[str] = None) -> dict:
    """List the actions available to animate with.

    Args:
        object_name: Restrict to this object's active action and NLA actions.
            Omit to list every action in the file.
        filter: Case-insensitive substring match on the action name.
    """
    try:
        import bpy

        query = (filter or "").lower()
        actions: List[Dict[str, Any]] = []
        seen: set = set()

        def _add(action: Any, source: str) -> None:
            if action is None:
                return
            name = getattr(action, "name", "")
            if not name or name in seen:
                return
            if query and query not in name.lower():
                return
            seen.add(name)
            actions.append(
                {
                    "name": name,
                    "frame_range": list(getattr(action, "frame_range", ()) or ()),
                    "fcurve_count": len(_iter_items(getattr(action, "fcurves", []))),
                    "source": source,
                }
            )

        if object_name:
            obj, error = _animated_object(bpy, object_name)
            if error:
                return error
            data = getattr(obj, "animation_data", None)
            if data is not None:
                _add(getattr(data, "action", None), "active")
                for track in _iter_items(getattr(data, "nla_tracks", [])):
                    for strip in _iter_items(getattr(track, "strips", [])):
                        _add(getattr(strip, "action", None), f"nla:{getattr(track, 'name', '')}")
        else:
            for action in _iter_items(getattr(bpy.data, "actions", [])):
                _add(action, "file")

        return skill_success(
            f"Found {len(actions)} action(s)",
            count=len(actions),
            actions=actions,
            filter=filter,
            prompt="Use add_nla_strip to place an action on a track.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to list animation actions")


def list_nla_tracks(object_name: str) -> dict:
    """List the NLA tracks on an object and the strips each one holds.

    Args:
        object_name: Object whose NLA tracks are listed.
    """
    try:
        import bpy

        obj, error = _animated_object(bpy, object_name)
        if error:
            return error
        data = getattr(obj, "animation_data", None)
        tracks = _iter_items(getattr(data, "nla_tracks", [])) if data is not None else []
        return skill_success(
            f"Found {len(tracks)} NLA track(s) on {object_name}",
            object_name=object_name,
            count=len(tracks),
            tracks=[_track_context(track) for track in tracks],
            prompt="Use add_nla_track or add_nla_strip to extend the stack.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to list NLA tracks on {object_name}")


def add_nla_track(object_name: str, track_name: Optional[str] = None) -> dict:
    """Create an NLA track on an object.

    Args:
        object_name: Object that receives the track.
        track_name: Track name; defaults to Blender's generated name.
    """
    try:
        import bpy

        obj, error = _animated_object(bpy, object_name)
        if error:
            return error
        data = _animation_data(obj, create=True)
        if data is None:
            return skill_error(
                "Animation data unavailable", f"Blender would not create animation_data on {object_name}."
            )

        tracks = data.nla_tracks
        track = tracks.new()
        created = True
        if track_name:
            track.name = track_name
        return skill_success(
            f"Added NLA track on {object_name}",
            object_name=object_name,
            track=_track_context(track),
            created=created,
            prompt="Use add_nla_strip to place an action on this track.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to add NLA track on {object_name}")


def remove_nla_track(object_name: str, track_name: str) -> dict:
    """Remove an NLA track and the strips it holds.

    Args:
        object_name: Object that owns the track.
        track_name: Track to remove.
    """
    try:
        import bpy

        obj, error = _animated_object(bpy, object_name)
        if error:
            return error
        data = getattr(obj, "animation_data", None)
        track, error = _find_named(getattr(data, "nla_tracks", []) if data is not None else [], track_name, "Track")
        if error:
            return error

        removed = _track_context(track)
        data.nla_tracks.remove(track)
        return skill_success(
            f"Removed NLA track {track_name} from {object_name}",
            object_name=object_name,
            track=removed,
            prompt="Use list_nla_tracks to review the remaining stack.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to remove NLA track {track_name} from {object_name}")


def add_nla_strip(
    object_name: str,
    action_name: str,
    track_name: Optional[str] = None,
    frame_start: Optional[float] = None,
    strip_name: Optional[str] = None,
) -> dict:
    """Place an action on an NLA track as a new strip.

    Args:
        object_name: Object that receives the strip.
        action_name: Action to place; must already exist in the file.
        track_name: Target track; defaults to the first track, created if the
            object has none.
        frame_start: Frame where the strip starts; defaults to the current frame.
        strip_name: Strip name; defaults to the action name.
    """
    try:
        import bpy

        obj, error = _animated_object(bpy, object_name)
        if error:
            return error

        action = bpy.data.actions.get(action_name) if hasattr(bpy.data, "actions") else None
        if action is None:
            return skill_error(f"Action not found: {action_name}", f"No action named '{action_name}'.")

        data = _animation_data(obj, create=True)
        if data is None:
            return skill_error(
                "Animation data unavailable", f"Blender would not create animation_data on {object_name}."
            )

        tracks = data.nla_tracks
        if track_name:
            track, error = _find_named(tracks, track_name, "Track")
            if error:
                return error
        else:
            if not _iter_items(tracks):
                track = tracks.new()
            else:
                track, error = _find_named(tracks, None, "Track")
                if error:
                    return error

        start = float(frame_start) if frame_start is not None else float(getattr(bpy.context.scene, "frame_current", 1))
        strip = track.strips.new(strip_name or action_name, int(start), action)
        return skill_success(
            f"Added NLA strip on {object_name}",
            object_name=object_name,
            track_name=getattr(track, "name", None),
            strip=_strip_context(strip),
            prompt="Use set_nla_strip to move, scale, or blend it.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to add NLA strip on {object_name}")


def set_nla_strip(
    object_name: str,
    strip_name: str,
    track_name: Optional[str] = None,
    frame_start: Optional[float] = None,
    action_frame_start: Optional[float] = None,
    action_frame_end: Optional[float] = None,
    scale: Optional[float] = None,
    repeat: Optional[float] = None,
    influence: Optional[float] = None,
    blend_type: Optional[str] = None,
    extrapolation: Optional[str] = None,
    muted: Optional[bool] = None,
) -> dict:
    """Update one NLA strip in place.

    Args:
        object_name: Object that owns the strip.
        strip_name: Strip to update.
        track_name: Track holding the strip; defaults to searching every track.
        frame_start: Move the strip to this frame.
        action_frame_start: Trim the action's start inside the strip.
        action_frame_end: Trim the action's end inside the strip.
        scale: Time scaling of the strip; Blender clamps this to 0.0001..1000.
        repeat: How many times the action repeats; Blender clamps to 0.01..1000.
        influence: Blend influence, 0..1.
        blend_type: ``REPLACE``, ``ADD``, ``SUBTRACT``, or ``MULTIPLY``.
        extrapolation: ``NOTHING``, ``HOLD``, or ``HOLD_FORWARD``.
        muted: Mute or unmute the strip.
    """
    if blend_type is not None and str(blend_type).upper() not in BLEND_TYPES:
        return skill_error(
            f"Unsupported blend type: {blend_type}",
            f"Supported blend types: {', '.join(BLEND_TYPES)}.",
        )
    if extrapolation is not None and str(extrapolation).upper() not in EXTRAPOLATION_TYPES:
        return skill_error(
            f"Unsupported extrapolation: {extrapolation}",
            f"Supported values: {', '.join(EXTRAPOLATION_TYPES)}.",
        )
    if influence is not None and not 0.0 <= float(influence) <= 1.0:
        return skill_error("Invalid influence", "influence must be between 0.0 and 1.0.")
    if scale is not None and not 0.0001 <= float(scale) <= 1000.0:
        return skill_error("Invalid scale", "scale must be between 0.0001 and 1000.")
    if repeat is not None and not 0.01 <= float(repeat) <= 1000.0:
        return skill_error("Invalid repeat", "repeat must be between 0.01 and 1000.")

    updates = {
        "frame_start": frame_start,
        "action_frame_start": action_frame_start,
        "action_frame_end": action_frame_end,
        "scale": scale,
        "repeat": repeat,
        "influence": influence,
        "blend_type": str(blend_type).upper() if blend_type is not None else None,
        "extrapolation": str(extrapolation).upper() if extrapolation is not None else None,
        "muted": muted,
    }
    if all(value is None for value in updates.values()):
        return skill_error(
            "No strip changes supplied",
            "Provide at least one of frame_start, action_frame_start, action_frame_end, "
            "scale, repeat, influence, blend_type, extrapolation, muted.",
        )

    try:
        import bpy

        obj, error = _animated_object(bpy, object_name)
        if error:
            return error
        data = getattr(obj, "animation_data", None)
        if data is None:
            return skill_error(
                "No animation data",
                f"{object_name} has no animation_data, so it has no NLA strips.",
            )

        strip = None
        if track_name:
            track, error = _find_named(getattr(data, "nla_tracks", []), track_name, "Track")
            if error:
                return error
            strip, _ = _find_named(getattr(track, "strips", []), strip_name, "Strip")
        else:
            for track in _iter_items(getattr(data, "nla_tracks", [])):
                strip, _ = _find_named(getattr(track, "strips", []), strip_name, "Strip")
                if strip is not None:
                    break
        if strip is None:
            return skill_error(
                f"Strip not found: {strip_name}", f"{object_name} has no NLA strip named '{strip_name}'."
            )

        applied: Dict[str, Any] = {}
        if frame_start is not None:
            strip.frame_start = float(frame_start)
            applied["frame_start"] = float(frame_start)
        if action_frame_start is not None:
            strip.action_frame_start = float(action_frame_start)
            applied["action_frame_start"] = float(action_frame_start)
        if action_frame_end is not None:
            strip.action_frame_end = float(action_frame_end)
            applied["action_frame_end"] = float(action_frame_end)
        if scale is not None:
            strip.scale = float(scale)
            applied["scale"] = float(scale)
        if repeat is not None:
            strip.repeat = float(repeat)
            applied["repeat"] = float(repeat)
        if influence is not None:
            strip.influence = float(influence)
            applied["influence"] = float(influence)
        if blend_type is not None:
            strip.blend_type = str(blend_type).upper()
            applied["blend_type"] = strip.blend_type
        if extrapolation is not None:
            strip.extrapolation = str(extrapolation).upper()
            applied["extrapolation"] = strip.extrapolation
        if muted is not None:
            strip.mute = bool(muted)
            applied["muted"] = bool(muted)

        return skill_success(
            f"Updated NLA strip {strip_name}",
            object_name=object_name,
            applied=applied,
            strip=_strip_context(strip),
            prompt="Use list_nla_tracks to review the stack.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to update NLA strip {strip_name}")


def remove_nla_strip(object_name: str, strip_name: str, track_name: Optional[str] = None) -> dict:
    """Remove an NLA strip from a track.

    Args:
        object_name: Object that owns the strip.
        strip_name: Strip to remove.
        track_name: Track holding the strip; defaults to searching every track.
    """
    try:
        import bpy

        obj, error = _animated_object(bpy, object_name)
        if error:
            return error
        data = getattr(obj, "animation_data", None)
        if data is None:
            return skill_error(
                "No animation data",
                f"{object_name} has no animation_data, so it has no NLA strips.",
            )

        if track_name:
            track, error = _find_named(getattr(data, "nla_tracks", []), track_name, "Track")
            if error:
                return error
            strip, _ = _find_named(getattr(track, "strips", []), strip_name, "Strip")
            if strip is None:
                return skill_error(
                    f"Strip not found: {strip_name}", f"Track {track_name} has no strip named '{strip_name}'."
                )
            removed = _strip_context(strip)
            track.strips.remove(strip)
        else:
            strip = None
            owner = None
            for track in _iter_items(getattr(data, "nla_tracks", [])):
                candidate, _ = _find_named(getattr(track, "strips", []), strip_name, "Strip")
                if candidate is not None:
                    strip, owner = candidate, track
                    break
            if strip is None:
                return skill_error(
                    f"Strip not found: {strip_name}", f"{object_name} has no NLA strip named '{strip_name}'."
                )
            removed = _strip_context(strip)
            owner.strips.remove(strip)

        return skill_success(
            f"Removed NLA strip {strip_name} from {object_name}",
            object_name=object_name,
            track_name=getattr(owner, "name", None) if track_name is None else track_name,
            track=removed,
            prompt="Use list_nla_tracks to review the remaining stack.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to remove NLA strip {strip_name} from {object_name}")


def list_action_fcurves(action_name: str, data_path: Optional[str] = None) -> dict:
    """List the fcurves inside an action.

    Args:
        action_name: Action to inspect.
        data_path: Restrict to fcurves with this data path, for example
            ``location``.
    """
    try:
        import bpy

        action = bpy.data.actions.get(action_name) if hasattr(bpy.data, "actions") else None
        if action is None:
            return skill_error(f"Action not found: {action_name}", f"No action named '{action_name}'.")

        fcurves = []
        for fcurve in _iter_items(getattr(action, "fcurves", [])):
            path = getattr(fcurve, "data_path", "")
            if data_path and path != data_path and not path.endswith(f".{data_path}"):
                continue
            frames = [
                float(getattr(point.co, "x", 0.0))
                for point in _iter_items(getattr(fcurve, "keyframe_points", []))
                if getattr(point, "co", None) is not None
            ]
            fcurves.append(
                {
                    "data_path": path,
                    "array_index": getattr(fcurve, "array_index", None),
                    "keyframe_count": len(frames),
                    "range": [min(frames), max(frames)] if frames else [],
                }
            )
        return skill_success(
            f"Found {len(fcurves)} fcurve(s) in {action_name}",
            action_name=action_name,
            data_path=data_path,
            count=len(fcurves),
            fcurves=fcurves,
            prompt="Use set_action_fcurve_extrapolation to change how a curve behaves outside its keys.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to list fcurves in {action_name}")


def set_action_fcurve_extrapolation(
    action_name: str,
    extrapolation: str,
    data_path: Optional[str] = None,
    array_index: Optional[int] = None,
) -> dict:
    """Set the extrapolation mode on an action's fcurves.

    Extrapolation decides what happens before the first and after the last
    keyframe: hold the end value, keep going linearly, or fall back to the
    underlying value.

    Args:
        action_name: Action holding the fcurves.
        extrapolation: ``CONSTANT``, ``LINEAR``, or ``CUSTOM``.
        data_path: Restrict to fcurves with this data path.
        array_index: Restrict to one component, for example ``0`` for X.
    """
    wanted = str(extrapolation or "").upper()
    if wanted not in {"CONSTANT", "LINEAR", "CUSTOM"}:
        return skill_error(
            f"Unsupported extrapolation: {extrapolation}",
            "Supported values: CONSTANT, LINEAR, CUSTOM.",
        )
    try:
        import bpy

        action = bpy.data.actions.get(action_name) if hasattr(bpy.data, "actions") else None
        if action is None:
            return skill_error(f"Action not found: {action_name}", f"No action named '{action_name}'.")

        updated = []
        for fcurve in _iter_items(getattr(action, "fcurves", [])):
            path = getattr(fcurve, "data_path", "")
            if data_path and path != data_path and not path.endswith(f".{data_path}"):
                continue
            if array_index is not None and getattr(fcurve, "array_index", None) != int(array_index):
                continue
            fcurve.extrapolation = wanted
            updated.append({"data_path": path, "array_index": getattr(fcurve, "array_index", None)})

        if not updated:
            return skill_error(
                "No matching fcurves",
                f"Action {action_name} has no fcurve matching the given data_path/array_index.",
            )
        return skill_success(
            f"Set extrapolation to {wanted} on {len(updated)} fcurve(s)",
            action_name=action_name,
            extrapolation=wanted,
            updated=updated,
            count=len(updated),
            prompt="Use list_action_fcurves to confirm the curve range.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to set fcurve extrapolation on {action_name}")
