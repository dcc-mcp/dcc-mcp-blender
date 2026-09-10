"""Validate camera requests before allocating or modifying Blender data."""

import math


def positive_number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError("{} must be a finite positive number".format(name))


def camera_location(value):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError("location must contain three finite coordinates")
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in value):
        raise ValueError("location must contain three finite coordinates")
