"""Tests for the dcc-mcp-core dependency floor."""

from __future__ import annotations

import importlib.util
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).parent.parent


def _load_assemble_zip_module():
    path = ROOT / "packaging" / "assemble_zip.py"
    spec = importlib.util.spec_from_file_location("assemble_zip_for_tests", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _core_upper_bound():
    """The Core upper bound, read from pyproject so tightening it does not touch every assert."""
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'"dcc-mcp-core>=[^,]+,<(?P<upper>[0-9][0-9A-Za-z.]*)"', pyproject)

    assert match is not None, "pyproject.toml must pin a dcc-mcp-core upper bound"
    return match.group("upper")


def test_core_dependency_floor_is_0200():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert '"dcc-mcp-core>=0.20.0,<%s"' % _core_upper_bound() in pyproject


def test_core_dependency_upper_bound_excludes_the_next_core_minor():
    # ``<1.0.0`` admitted any future Core minor, which is how 0.20.34 changed the Install SOP
    # schema version without this adapter noticing until main went red.
    #
    # This is the one place the bound is spelled out: widening it is a deliberate, reviewed act,
    # not a side effect of a dependency refresh.
    assert _core_upper_bound() == "0.21.0"


def test_packaging_core_floor_matches_pyproject():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'"dcc-mcp-core>=(?P<version>[^,]+),<%s"' % re.escape(_core_upper_bound()), pyproject)

    assert match is not None
    assert _load_assemble_zip_module().MIN_CORE_VERSION == match.group("version")


def test_preloaded_core_below_floor_is_rejected():
    from dcc_mcp_blender._core_compat import require_compatible_core

    with pytest.raises(RuntimeError, match="preloaded dcc-mcp-core 0.19.94"):
        require_compatible_core("0.19.94", module_path="/host/site-packages/dcc_mcp_core")


def test_preloaded_core_at_floor_is_accepted():
    from dcc_mcp_blender._core_compat import require_compatible_core

    require_compatible_core("0.20.0", module_path="/extension/site-packages/dcc_mcp_core")
