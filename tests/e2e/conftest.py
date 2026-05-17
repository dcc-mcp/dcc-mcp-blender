"""E2E test configuration for dcc-mcp-blender.

Requires a real Blender interpreter (``blender --background --python``).
All tests in ``tests/e2e/`` are skipped automatically when ``bpy`` is not
importable, so the suite is safe to collect under normal pytest runs.

Run locally::

    blender --background --python -m pytest tests/e2e/ -- -v

Or via the installed blender Python directly::

    /path/to/blender/python/bin/python -m pytest tests/e2e/ -v

CI::

    Linux uses Blender container images. Windows and macOS download Blender
    directly. All variants run blender --background to execute tests.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def pytest_configure(config):
    """Register the ``e2e`` marker."""
    config.addinivalue_line(
        "markers",
        "e2e: end-to-end tests that require a real Blender interpreter (bpy)",
    )


def pytest_collection_modifyitems(items, config):
    """Skip all e2e tests when bpy is not available."""
    try:
        import bpy  # noqa: F401
    except Exception:
        skip_marker = pytest.mark.skip(reason="bpy not available — run inside Blender Python interpreter")
        for item in items:
            if "tests/e2e" in item.path.as_posix():
                item.add_marker(skip_marker)


# ── Shared helper for E2E test modules ────────────────────────────────────────

SKILLS_ROOT = Path(__file__).parent.parent.parent / "src" / "dcc_mcp_blender" / "skills"
_MOD_COUNTER = [0]


def load_skill(skill_dir: str, script_name: str):
    """Load a skill script module inside a real Blender Python session.

    Args:
        skill_dir: Directory name under ``skills/`` (may contain hyphens).
        script_name: Script stem (without ``.py``).

    Returns:
        The loaded module object.
    """
    _MOD_COUNTER[0] += 1
    path = SKILLS_ROOT / skill_dir / "scripts" / f"{script_name}.py"
    mod_name = f"e2e_{skill_dir.replace('-', '_')}_{script_name}_{_MOD_COUNTER[0]}"
    spec = importlib.util.spec_from_file_location(mod_name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
