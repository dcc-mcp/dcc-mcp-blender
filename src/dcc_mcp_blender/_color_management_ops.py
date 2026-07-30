"""Shared Blender scene color-management helpers."""

from __future__ import annotations

from typing import Any, Optional


def color_management_info(scene: Any) -> dict:
    view = getattr(scene, "view_settings", None)
    display = getattr(scene, "display_settings", None)
    return {
        "display_device": getattr(display, "display_device", None),
        "view_transform": getattr(view, "view_transform", None),
        "look": getattr(view, "look", None),
        "exposure": getattr(view, "exposure", None),
        "gamma": getattr(view, "gamma", None),
    }


def apply_color_management(
    scene: Any,
    *,
    display_device: Optional[str] = None,
    view_transform: Optional[str] = None,
    look: Optional[str] = None,
    exposure: Optional[float] = None,
    gamma: Optional[float] = None,
) -> dict:
    view = getattr(scene, "view_settings", None)
    if view is None:
        raise AttributeError("Scene view_settings is not available")
    display = getattr(scene, "display_settings", None)
    if display_device is not None:
        if display is None:
            raise AttributeError("Scene display_settings is not available")
        display.display_device = display_device
    if view_transform is not None:
        view.view_transform = view_transform
    if look is not None:
        view.look = look
    if exposure is not None:
        view.exposure = float(exposure)
    if gamma is not None:
        view.gamma = float(gamma)
    return color_management_info(scene)
