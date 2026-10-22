"""Validate Blender render CPU thread settings without assuming host RNA bounds."""

from __future__ import annotations

from typing import Any, Optional


def render_thread_info(render: Any) -> dict:
    """Read RNA values, which reflect AUTO/host overrides, not raw saved state."""
    values = {}
    for name in ("threads_mode", "threads"):
        try:
            values[name] = getattr(render, name, None)
        except Exception:
            # Preserve partial-change diagnostics even if native readback fails.
            values[name] = None
    mode, count = values["threads_mode"], values["threads"]
    return {
        "threads_mode": mode if isinstance(mode, str) and mode in {"AUTO", "FIXED"} else None,
        "threads": count if isinstance(count, int) and not isinstance(count, bool) else None,
    }


def validate_render_threads(render: Any, threads_mode: Optional[str], threads: Optional[int]) -> dict:
    """Return a validated update, or fail before any render setting changes."""
    if threads_mode is None and threads is None:
        return {}
    if threads_mode is not None and (not isinstance(threads_mode, str) or threads_mode not in {"AUTO", "FIXED"}):
        raise ValueError("threads_mode must be AUTO or FIXED")
    if threads is not None and (isinstance(threads, bool) or not isinstance(threads, int)):
        raise ValueError("threads must be an integer, not a boolean or coerced number")
    if threads_mode == "AUTO" and threads is not None:
        raise ValueError("AUTO selects host-managed render threads; omit threads")
    if threads_mode == "FIXED" and threads is None:
        raise ValueError("FIXED requires an explicit threads count")

    mode = "FIXED" if threads is not None else threads_mode
    rna = getattr(render, "bl_rna", None)
    properties = getattr(rna, "properties", None)
    if properties is None:
        raise ValueError("Render thread RNA metadata is unavailable on this host")
    mode_prop = properties.get("threads_mode")
    if (
        mode_prop is None
        or getattr(mode_prop, "type", None) != "ENUM"
        or getattr(mode_prop, "is_readonly", None) is not False
    ):
        raise ValueError("threads_mode is unavailable or not writable on this host")
    is_readonly = getattr(render, "is_property_readonly", None)
    if callable(is_readonly) and is_readonly("threads_mode"):
        raise ValueError("threads_mode is read-only on this render settings instance")
    supported = {item.identifier for item in mode_prop.enum_items}
    if mode not in supported:
        raise ValueError("threads_mode {} is unsupported by this host RNA".format(mode))
    current = render_thread_info(render)
    if current["threads_mode"] is None or current["threads"] is None:
        raise ValueError("Native render thread settings are unavailable on this host")
    update = {"threads_mode": mode}
    if threads is not None:
        prop = properties.get("threads")
        if prop is None or getattr(prop, "type", None) != "INT" or getattr(prop, "is_readonly", None) is not False:
            raise ValueError("threads is unavailable or not writable on this host")
        if callable(is_readonly) and is_readonly("threads"):
            raise ValueError("threads is read-only on this render settings instance")
        lower, upper = getattr(prop, "hard_min", None), getattr(prop, "hard_max", None)
        if (
            isinstance(lower, bool)
            or isinstance(upper, bool)
            or not isinstance(lower, int)
            or not isinstance(upper, int)
            or not 1 <= lower <= upper
        ):
            raise ValueError("threads RNA bounds are unavailable on this host")
        if not lower <= threads <= upper:
            raise ValueError("threads must be an integer between {} and {} on this host".format(lower, upper))
        update["threads"] = threads
    return update


def apply_render_threads(render: Any, update: dict) -> None:
    """Apply validated inputs and check the native effective settings.

    RNA getters can hide the stored scene settings in AUTO or under a process
    thread override. They are not a sound rollback snapshot; never write their
    observed values back as though they were the original stored settings.
    """
    if not update:
        return
    if "threads" in update:
        render.threads = update["threads"]
    render.threads_mode = update["threads_mode"]
    actual = render_thread_info(render)
    if any(actual[key] != value for key, value in update.items()):
        raise ValueError("Native render thread readback differs from the request; a host thread override may be active")
