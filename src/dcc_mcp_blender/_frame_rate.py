"""Validate and report Blender's native render timebase without rounding it."""

from __future__ import annotations

import math
from typing import Any, Optional


def _finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _native_limits(render: Any, name: str, fallback: tuple) -> tuple:
    """Use host RNA bounds, with documented limits for minimal test hosts."""
    rna = getattr(render, "bl_rna", None)
    properties = getattr(rna, "properties", {})
    prop = properties.get(name)
    lower = getattr(prop, "hard_min", None)
    upper = getattr(prop, "hard_max", None)
    if _finite_number(lower) and _finite_number(upper) and 0 < lower <= upper:
        return lower, upper
    return fallback


def validate_frame_rate(render: Any, fps: Optional[int], fps_base: Optional[float]) -> None:
    """Reject invalid timebase input before any render settings are changed."""
    if fps is not None:
        lower, upper = _native_limits(render, "fps", (1, 32767))
        if isinstance(fps, bool) or not isinstance(fps, int) or not lower <= fps <= upper:
            raise ValueError(f"fps must be an integer between {lower:g} and {upper:g}")
    if fps_base is not None:
        # Blender stores its nominal 1e-5 lower bound as a float32.
        lower, upper = _native_limits(render, "fps_base", (9.999999747378752e-6, 1e6))
        if not _finite_number(fps_base) or not lower <= fps_base <= upper:
            raise ValueError(f"fps_base must be a finite number between {lower:g} and {upper:g}")
        if not _finite_number(getattr(render, "fps_base", None)):
            raise ValueError("fps_base is unavailable on this host")


def frame_rate_info(render: Any) -> dict:
    """Read actual host values; never invent a missing denominator."""
    fps = getattr(render, "fps", None)
    fps_base = getattr(render, "fps_base", None)
    if not _finite_number(fps):
        fps = None
    if not _finite_number(fps_base):
        fps_base = None
    effective_fps = fps / fps_base if fps is not None and fps_base is not None and fps_base > 0 else None
    return {"fps": fps, "fps_base": fps_base, "effective_fps": effective_fps}
