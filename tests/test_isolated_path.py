"""Tests for the isolated-host PYTHONPATH repair helper.

Blender 5.x boots CPython with an isolated configuration, so ``PYTHONPATH``
entries injected by a package manager never reach ``sys.path``. These tests
simulate both interpreter modes against temporary directories.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import sys

import pytest

from dcc_mcp_blender import _isolated_path as helper

TOOLS_DIR = pathlib.Path(__file__).parent.parent / "tools"


@pytest.fixture
def isolated(monkeypatch):
    """Force the helper to see an isolated interpreter."""
    monkeypatch.setattr(helper, "is_isolated_python", lambda *args, **kwargs: True)
    return True


@pytest.fixture
def not_isolated(monkeypatch):
    """Force the helper to see an interpreter that honoured PYTHONPATH."""
    monkeypatch.setattr(helper, "is_isolated_python", lambda *args, **kwargs: False)
    return False


@pytest.fixture
def clean_env(monkeypatch):
    monkeypatch.delenv(helper.ENV_REPAIR, raising=False)
    monkeypatch.delenv(helper.ENV_EXTRA_PATHS, raising=False)
    monkeypatch.setenv("PYTHONPATH", "")
    return monkeypatch


def test_pythonpath_entries_parses_and_dedupes(clean_env, tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    clean_env.setenv("PYTHONPATH", os.pathsep.join([str(first), str(second), str(first)]))

    assert helper.pythonpath_entries() == [str(first), str(second)]


def test_missing_path_entries_skips_unknown_dirs_and_present_entries(tmp_path):
    existing = tmp_path / "existing"
    fresh = tmp_path / "fresh"
    existing.mkdir()
    fresh.mkdir()
    gone = tmp_path / "gone"

    missing = helper.missing_path_entries(
        [str(existing), str(gone), str(fresh), str(fresh)], sys_path=[str(existing)]
    )
    assert missing == [str(fresh.resolve())]


def test_repair_is_noop_when_interpreter_honours_pythonpath(clean_env, not_isolated, tmp_path):
    clean_env.setenv("PYTHONPATH", str(tmp_path))
    sys_path = ["/stdlib"]

    assert helper.repair_sys_path(sys_path=sys_path) == []
    assert sys_path == ["/stdlib"]


def test_repair_inserts_pythonpath_before_site_packages(clean_env, isolated, tmp_path):
    injected = tmp_path / "injected"
    injected.mkdir()
    clean_env.setenv("PYTHONPATH", str(injected))
    sys_path = ["/stdlib", "/blender/5.1/python/lib/site-packages"]

    added = helper.repair_sys_path(sys_path=sys_path)

    assert added and added[0] == str(injected.resolve())
    assert sys_path.index(str(injected.resolve())) < sys_path.index("/blender/5.1/python/lib/site-packages")
    assert sys_path[0] == "/stdlib"


def test_repair_appends_when_no_site_packages_entry_exists(clean_env, isolated, tmp_path):
    injected = tmp_path / "injected"
    injected.mkdir()
    clean_env.setenv("PYTHONPATH", str(injected))
    sys_path = ["/stdlib"]

    helper.repair_sys_path(sys_path=sys_path)
    assert sys_path == ["/stdlib", str(injected.resolve())]


def test_repair_is_idempotent(clean_env, isolated, tmp_path):
    injected = tmp_path / "injected"
    injected.mkdir()
    clean_env.setenv("PYTHONPATH", str(injected))
    sys_path = ["/stdlib", "/site-packages"]

    assert helper.repair_sys_path(sys_path=sys_path)
    assert helper.repair_sys_path(sys_path=sys_path) == []
    assert sys_path.count(str(injected.resolve())) == 1


def test_repair_disabled_by_env(clean_env, isolated, tmp_path):
    injected = tmp_path / "injected"
    injected.mkdir()
    clean_env.setenv("PYTHONPATH", str(injected))
    clean_env.setenv(helper.ENV_REPAIR, "0")
    sys_path = ["/stdlib"]

    assert helper.repair_sys_path(sys_path=sys_path) == []
    assert sys_path == ["/stdlib"]


def test_extra_site_dirs_apply_without_isolation(clean_env, not_isolated, tmp_path):
    extra = tmp_path / "extra"
    extra.mkdir()
    clean_env.setenv(helper.ENV_EXTRA_PATHS, str(extra))
    sys_path = ["/stdlib", "/site-packages"]

    added = helper.repair_sys_path(sys_path=sys_path)
    assert added == [str(extra.resolve())]


def test_force_repairs_even_when_not_isolated(clean_env, not_isolated, tmp_path):
    injected = tmp_path / "injected"
    injected.mkdir()
    clean_env.setenv("PYTHONPATH", str(injected))
    sys_path = ["/stdlib"]

    assert helper.repair_sys_path(force=True, sys_path=sys_path) == [str(injected.resolve())]


def test_path_state_reports_visibility(clean_env, tmp_path):
    visible = tmp_path / "visible"
    hidden = tmp_path / "hidden"
    visible.mkdir()
    hidden.mkdir()
    clean_env.setenv("PYTHONPATH", os.pathsep.join([str(visible), str(hidden)]))

    state = helper.path_state(sys_path=[str(visible)])

    assert state["pythonpath_entries"] == 2
    assert state["pythonpath_visible"] == 1
    assert state["repair_enabled"] is True


def test_is_isolated_python_reads_sys_flags():
    class _Flags:
        isolated = 1
        ignore_environment = 0

    assert helper.is_isolated_python(_Flags()) is True
    assert helper.is_isolated_python(sys.flags) == bool(
        getattr(sys.flags, "isolated", 0) or getattr(sys.flags, "ignore_environment", 0)
    )


def _load_doctor():
    path = TOOLS_DIR / "blender_path_doctor.py"
    spec = importlib.util.spec_from_file_location("blender_path_doctor_for_tests", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_doctor_locate_helper_finds_module():
    doctor = _load_doctor()
    assert doctor.locate_helper() is not None


def test_doctor_probe_reports_adapter_and_core():
    doctor = _load_doctor()
    report = doctor.probe(repair=True)

    assert report["helper_loaded"] is True
    assert report["imports"]["dcc_mcp_blender"]["ok"] is True
    assert report["imports"]["dcc_mcp_core"]["ok"] is True
    assert report["tool_surface"]["submodules"] > 0
    assert report["ok"] is True
