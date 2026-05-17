"""Shared test fixtures and helpers for dcc-mcp-blender tests.

Provides:
- ``load_skill_script(skill_dir, script_name)`` — load a skill script by path
- ``make_mock_bpy(data_attrs, ops_attrs)`` — build a mock bpy module
- ``load_and_call(rel_path, mock_bpy_obj, func_name, **kwargs)`` — load + call with mock active
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

SKILLS_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_blender" / "skills"

_MOD_COUNTER = [0]


def load_skill_script(skill_dir: str, script_name: str):
    """Load a skill script module by path.

    Uses a unique module name per call to avoid module cache collisions
    when the same script is loaded multiple times in a test session.

    Args:
        skill_dir: Directory name under ``skills/`` (may contain hyphens).
        script_name: Script stem name (without ``.py`` extension).

    Returns:
        The loaded module object.
    """
    _MOD_COUNTER[0] += 1
    script_path = SKILLS_ROOT / skill_dir / "scripts" / f"{script_name}.py"
    module_name = f"skill_{skill_dir.replace('-', '_')}_{script_name}_{_MOD_COUNTER[0]}"
    spec = importlib.util.spec_from_file_location(module_name, str(script_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_mock_bpy(
    data_attrs: Optional[Dict] = None,
    ops_attrs: Optional[Dict] = None,
    context_attrs: Optional[Dict] = None,
    app_attrs: Optional[Dict] = None,
) -> MagicMock:
    """Build a mock ``bpy`` module with realistic sub-attributes wired up.

    Args:
        data_attrs: Overrides for ``bpy.data`` attributes.
        ops_attrs: Overrides for ``bpy.ops`` sub-mock.
        context_attrs: Overrides for ``bpy.context`` attributes.
        app_attrs: Overrides for ``bpy.app`` attributes.

    Returns:
        A :class:`~unittest.mock.MagicMock` that mimics the ``bpy`` module.
    """
    mock_bpy = MagicMock()

    # bpy.app defaults
    mock_bpy.app.version = (4, 0, 0)
    mock_bpy.app.version_string = "4.0.0"
    mock_bpy.app.binary_path = "/usr/bin/blender"
    mock_bpy.app.background = True
    mock_bpy.app.build_date = b"2024-01-01"
    if app_attrs:
        for k, v in app_attrs.items():
            setattr(mock_bpy.app, k, v)

    # bpy.context defaults
    mock_scene = MagicMock()
    mock_scene.name = "Scene"
    mock_scene.frame_current = 1
    mock_scene.frame_start = 1
    mock_scene.frame_end = 250
    mock_scene.render.fps = 24
    mock_scene.render.resolution_x = 1920
    mock_scene.render.resolution_y = 1080
    mock_scene.render.resolution_percentage = 100
    mock_scene.render.filepath = "//render"
    mock_scene.render.engine = "CYCLES"
    mock_scene.render.image_settings.file_format = "PNG"
    mock_scene.camera = None
    mock_scene.world = MagicMock()
    mock_scene.world.color = [0.0, 0.0, 0.0]
    mock_scene.world.use_nodes = False
    mock_bpy.context.scene = mock_scene
    mock_bpy.context.active_object = None
    mock_bpy.context.view_layer.objects.active = None
    if context_attrs:
        for k, v in context_attrs.items():
            setattr(mock_bpy.context, k, v)

    # bpy.data defaults — use MagicMock so tests can override .get/.new/.remove
    mock_bpy.data.filepath = ""
    mock_bpy.data.is_dirty = False
    mock_bpy.data.objects = MagicMock()
    mock_bpy.data.objects.__len__ = MagicMock(return_value=0)
    mock_bpy.data.objects.__iter__ = MagicMock(return_value=iter([]))
    mock_bpy.data.objects.__contains__ = MagicMock(return_value=False)
    mock_bpy.data.meshes = MagicMock()
    mock_bpy.data.meshes.__len__ = MagicMock(return_value=0)
    mock_bpy.data.materials = MagicMock()
    mock_bpy.data.materials.__len__ = MagicMock(return_value=0)
    mock_bpy.data.materials.__iter__ = MagicMock(return_value=iter([]))
    mock_bpy.data.collections = MagicMock()
    mock_bpy.data.lights = MagicMock()
    mock_bpy.data.cameras = MagicMock()
    mock_bpy.data.worlds = MagicMock()
    if data_attrs:
        for k, v in data_attrs.items():
            getattr(mock_bpy.data, k)
            if isinstance(v, list):
                # Replace the MagicMock with a list-like mock that has get/new/remove
                list_mock = MagicMock()
                list_mock.__iter__ = MagicMock(return_value=iter(v))
                list_mock.__len__ = MagicMock(return_value=len(v))
                list_mock.__contains__ = MagicMock(
                    side_effect=lambda x, _v=v: any(getattr(o, "name", None) == x or o == x for o in _v)
                )
                setattr(mock_bpy.data, k, list_mock)
            else:
                setattr(mock_bpy.data, k, v)

    # bpy.ops defaults
    mock_bpy.ops.mesh = MagicMock()
    mock_bpy.ops.object = MagicMock()
    mock_bpy.ops.wm = MagicMock()
    mock_bpy.ops.render = MagicMock()
    mock_bpy.ops.screen = MagicMock()
    if ops_attrs:
        for k, v in ops_attrs.items():
            setattr(mock_bpy.ops, k, v)

    return mock_bpy


_LOAD_COUNTER = [0]


def load_and_call(
    rel_path: str,
    mock_bpy_obj: Optional[MagicMock] = None,
    func_name: str = "main",
    **kwargs,
) -> Any:
    """Load a skill script and call a function with the bpy mock active.

    Args:
        rel_path: Path relative to the ``skills/`` root, e.g.
            ``"blender-scene/scripts/new_scene.py"``.
        mock_bpy_obj: The :class:`~unittest.mock.MagicMock` to use as ``bpy``.
            If None, a default mock is created via :func:`make_mock_bpy`.
        func_name: Name of the callable to invoke (default: ``"main"``).
        **kwargs: Keyword arguments forwarded to the callable.

    Returns:
        Whatever the skill function returns (typically an ActionResultModel dict).
    """
    _LOAD_COUNTER[0] += 1
    if mock_bpy_obj is None:
        mock_bpy_obj = make_mock_bpy()

    fpath = SKILLS_ROOT / rel_path
    mod_name = f"skill_lac_{fpath.stem}_{_LOAD_COUNTER[0]}"
    spec = importlib.util.spec_from_file_location(mod_name, str(fpath))
    mod = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"bpy": mock_bpy_obj, "mathutils": MagicMock()}):
        spec.loader.exec_module(mod)
        fn = getattr(mod, func_name)
        return fn(**kwargs)
