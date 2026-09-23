"""Tests for the dcc-mcp-core dependency floor."""

from __future__ import annotations

import importlib.util
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).parent.parent


def _core_spec():
    """The ``dcc-mcp-core`` constraint declared in ``pyproject.toml``."""
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'"dcc-mcp-core>=(?P<floor>[^,]+),<(?P<ceiling>[^"]+)"', pyproject)
    assert match is not None, "pyproject.toml no longer declares a dcc-mcp-core constraint"
    return match.group("floor"), match.group("ceiling")


def _load_assemble_zip_module():
    path = ROOT / "packaging" / "assemble_zip.py"
    spec = importlib.util.spec_from_file_location("assemble_zip_for_tests", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_core_dependency_floor_is_0200():
    floor, _ceiling = _core_spec()

    assert floor == "0.20.0"


def test_core_dependency_ceiling_pins_the_current_core_series():
    """The upper bound must exclude the next Core minor.

    ``<1.0.0`` admitted every future minor, so a Core release could silently
    break this adapter's CI (0.20.34 changed the Install SOP schema revision).
    Pinning to the next minor makes that incompatibility fail at dependency
    resolution instead of across the whole test matrix.
    """
    floor, ceiling = _core_spec()

    assert ceiling == "0.21.0"
    assert ceiling.split(".")[0] == floor.split(".")[0]


def test_packaging_core_floor_matches_pyproject():
    floor, _ceiling = _core_spec()

    assert _load_assemble_zip_module().MIN_CORE_VERSION == floor


def test_preloaded_core_below_floor_is_rejected():
    from dcc_mcp_blender._core_compat import require_compatible_core

    with pytest.raises(RuntimeError, match="preloaded dcc-mcp-core 0.19.94"):
        require_compatible_core("0.19.94", module_path="/host/site-packages/dcc_mcp_core")


def test_preloaded_core_at_floor_is_accepted():
    from dcc_mcp_blender._core_compat import require_compatible_core

    require_compatible_core("0.20.0", module_path="/extension/site-packages/dcc_mcp_core")
