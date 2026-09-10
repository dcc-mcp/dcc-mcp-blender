"""Validate camera requests before allocating or modifying Blender data."""

import math


def camera_number(value, name):
    minimum = {"lens": 1.0, "clip_start": 1e-6, "clip_end": 1e-6, "ortho_scale": 0.0}[name]
    # RNA stores camera properties as float32; reject values it would clamp.
    maximum = 3.4028234663852886e38
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not minimum <= value <= maximum
    ):
        raise ValueError("{} must be a finite number between {} and {}".format(name, minimum, maximum))


def camera_location(value):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError("location must contain three finite coordinates")
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in value):
        raise ValueError("location must contain three finite coordinates")
