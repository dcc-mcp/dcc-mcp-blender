"""Blender context snapshot provider for gateway routing and REST ``/v1/context``.

Mirrors :mod:`dcc_mcp_maya.context_snapshot`: a small, pure, headless-safe
callable that returns a fresh context dict describing live Blender state
(open file, scene name, selection, frame range, version).  It feeds:

* core's post-tool ``append_context_snapshot`` wrapper, and
* :meth:`DccServerBase.update_gateway_metadata` (scene / version / documents /
  display_name) via :func:`collect_gateway_metadata`.

Every Blender probe is guarded so importing this module from plain Python
(tests, ``--background`` without a scene) returns
``{"dcc": "blender", "available": False}`` instead of raising.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "BlenderContextSnapshotProvider",
    "collect_gateway_metadata",
    "make_snapshot_provider",
]


class BlenderContextSnapshotProvider:
    """Callable returning a fresh Blender context snapshot.

    Parameters
    ----------
    bpy_provider:
        Optional factory returning the ``bpy`` module (or a duck-typed
        stand-in for tests).  Defaults to a lazy import of ``bpy`` with a
        headless-safe fallback to ``None``.
    """

    def __init__(self, bpy_provider: Optional[Callable[[], Any]] = None) -> None:
        self._bpy_provider = bpy_provider or _default_bpy_provider

    def __call__(self) -> Dict[str, Any]:
        return self.collect()

    def collect(self) -> Dict[str, Any]:
        """Return a fresh context snapshot dict (never raises).

        Keys (all optional, omitted when unavailable)::

            {
                "dcc":          "blender",
                "scene":        "/path/to/file.blend",
                "scene_name":   "Scene",
                "scene_modified": True | False,
                "selection":    ["Cube", ...],
                "frame":        1,
                "frame_range":  [1, 250],
                "version":      "4.0.0",
                "display_name": "Blender 4.0.0 — file.blend",
                "pid":          12345,
                "available":    True | False,
            }
        """
        snapshot: Dict[str, Any] = {
            "dcc": "blender",
            "pid": os.getpid(),
            "available": False,
        }

        bpy = self._safe_bpy()
        if bpy is None:
            return snapshot

        snapshot["available"] = True

        # Open file path -----------------------------------------------------
        filepath = _safe_getattr(getattr(bpy, "data", None), "filepath", "")
        if filepath:
            snapshot["scene"] = str(filepath)

        is_dirty = _safe_getattr(getattr(bpy, "data", None), "is_dirty", None)
        if is_dirty is not None:
            snapshot["scene_modified"] = bool(is_dirty)

        # Version ------------------------------------------------------------
        version = _safe_getattr(getattr(bpy, "app", None), "version_string", "")
        if version:
            snapshot["version"] = str(version)

        scene = _safe_getattr(getattr(bpy, "context", None), "scene", None)
        if scene is not None:
            name = _safe_getattr(scene, "name", None)
            if name:
                snapshot["scene_name"] = str(name)
            frame = _safe_getattr(scene, "frame_current", None)
            if frame is not None:
                try:
                    snapshot["frame"] = int(frame)
                except (TypeError, ValueError):
                    pass
            start = _safe_getattr(scene, "frame_start", None)
            end = _safe_getattr(scene, "frame_end", None)
            if start is not None and end is not None:
                try:
                    snapshot["frame_range"] = [int(start), int(end)]
                except (TypeError, ValueError):
                    pass

        selection = self._selection(bpy)
        if selection is not None:
            snapshot["selection"] = selection

        display = _derive_display_name(snapshot.get("scene"), snapshot.get("version"))
        if display:
            snapshot["display_name"] = display
        return snapshot

    # ── internals ───────────────────────────────────────────────────────

    def _safe_bpy(self) -> Any:
        try:
            return self._bpy_provider()
        except Exception as exc:  # noqa: BLE001
            logger.debug("BlenderContextSnapshotProvider: bpy unavailable: %s", exc)
            return None

    @staticmethod
    def _selection(bpy: Any) -> Optional[List[str]]:
        context = getattr(bpy, "context", None)
        selected = _safe_getattr(context, "selected_objects", None)
        if selected is None:
            return None
        try:
            return [str(obj.name) for obj in selected]
        except Exception as exc:  # noqa: BLE001
            logger.debug("BlenderContextSnapshotProvider: selection read failed: %s", exc)
            return None


def collect_gateway_metadata(
    provider: Optional[Callable[[], Dict[str, Any]]] = None,
) -> Dict[str, Optional[Any]]:
    """Return the subset consumed by :meth:`update_gateway_metadata`.

    Blender is a single-document host, so ``documents`` becomes ``[scene]``
    when a file is open, otherwise ``[]``.
    """
    if provider is None:
        provider = BlenderContextSnapshotProvider()
    snapshot = provider() or {}
    scene = snapshot.get("scene")
    documents: Optional[List[str]] = [scene] if scene else []
    return {
        "scene": scene if scene else None,
        "version": snapshot.get("version"),
        "documents": documents,
        "display_name": snapshot.get("display_name"),
    }


def make_snapshot_provider(
    bpy_provider: Optional[Callable[[], Any]] = None,
) -> BlenderContextSnapshotProvider:
    """Factory for a :class:`BlenderContextSnapshotProvider` (test seam)."""
    return BlenderContextSnapshotProvider(bpy_provider=bpy_provider)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _default_bpy_provider() -> Any:
    """Return ``bpy`` when available, else ``None``."""
    try:
        import bpy  # noqa: PLC0415

        return bpy
    except Exception:  # noqa: BLE001
        return None


def _safe_getattr(target: Any, name: str, default: Any = None) -> Any:
    if target is None:
        return default
    try:
        return getattr(target, name, default)
    except Exception as exc:  # noqa: BLE001
        logger.debug("BlenderContextSnapshot: getattr(%s) raised %s", name, exc)
        return default


def _derive_display_name(scene: Optional[str], version: Optional[str]) -> Optional[str]:
    """Produce a human-readable instance label for gateway disambiguation."""
    if scene:
        try:
            basename = os.path.basename(scene) or scene
        except Exception:  # noqa: BLE001
            basename = scene
        if version:
            return "Blender {} — {}".format(version, basename)
        return "Blender — {}".format(basename)
    if version:
        return "Blender {}".format(version)
    return None
