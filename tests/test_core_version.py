"""Tests for the dcc-mcp-core dependency floor."""

from __future__ import annotations

import importlib.util
import pathlib
import re

ROOT = pathlib.Path(__file__).parent.parent


def _load_assemble_zip_module():
    path = ROOT / "packaging" / "assemble_zip.py"
    spec = importlib.util.spec_from_file_location("assemble_zip_for_tests", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_core_dependency_floor_is_0182():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert '"dcc-mcp-core>=0.18.2,<1.0.0"' in pyproject


def test_packaging_core_floor_matches_pyproject():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'"dcc-mcp-core>=(?P<version>[^,]+),<1\.0\.0"', pyproject)

    assert match is not None
    assert _load_assemble_zip_module().MIN_CORE_VERSION == match.group("version")
