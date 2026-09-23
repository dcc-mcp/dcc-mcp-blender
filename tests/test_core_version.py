"""Tests for the dcc-mcp-core dependency floor and its anti-regression gates."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import re

import pytest
import yaml

ROOT = pathlib.Path(__file__).parent.parent
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def _load_assemble_zip_module():
    path = ROOT / "packaging" / "assemble_zip.py"
    spec = importlib.util.spec_from_file_location("assemble_zip_for_tests", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ci_jobs():
    # type: () -> dict
    """Return the ``jobs`` mapping of the CI workflow."""
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(workflow, dict), "ci.yml did not parse into a mapping"
    jobs = workflow.get("jobs") or {}
    assert isinstance(jobs, dict), "ci.yml has no jobs mapping"
    return jobs


def _core_latest_job():
    # type: () -> dict
    """Return the ``core-latest`` job, failing with a readable reason if it is gone."""
    job = _ci_jobs().get("core-latest")
    assert job is not None, (
        "ci.yml has no `core-latest` job. It is the early-warning gate that runs the Install "
        "SOP contract against the newest published Core; without it a Core minor that breaks "
        "the contract is invisible until the upper bound is bumped."
    )
    return job


def _core_latest_job_text():
    # type: () -> str
    """Return the whole ``core-latest`` job serialised, for substring assertions."""
    return json.dumps(_core_latest_job(), default=str)


# The Core upper bound, read from the single source of truth so tightening it does not require
# touching every dependency assertion.
def _core_upper_bound():
    # type: () -> str
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'"dcc-mcp-core>=[^,]+,<(?P<upper>[0-9][0-9A-Za-z.]*)"', pyproject)
    assert match is not None, "could not read the dcc-mcp-core upper bound from pyproject.toml"
    return match.group("upper")


def test_core_dependency_floor_is_0200():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert '"dcc-mcp-core>=0.20.0,<%s"' % _core_upper_bound() in pyproject


def test_core_dependency_upper_bound_excludes_the_next_core_minor():
    # ``<1.0.0`` admitted any future Core minor, which is how 0.20.34 changed the Install SOP
    # schema version without this adapter noticing.
    assert _core_upper_bound() == "0.21.0"


def test_ci_exposes_a_core_latest_compatibility_job():
    """The early-warning job must stay in ci.yml.

    It is the only signal that a new Core minor breaks the Install SOP contract before the
    upper bound is bumped, and it is trivially easy to drop in an unrelated workflow edit.
    """
    job = _core_latest_job()

    # Advisory, not blocking: the whole point is to report drift without reddening the PR.
    assert job.get("continue-on-error") is True, job
    text = _core_latest_job_text()
    assert "dcc-mcp-core==" in text, "the job must pin the newest Core explicitly"
    assert "test_install_lifecycle.py" in text, "the job must run the Install SOP contract"


def test_core_latest_job_fails_when_the_core_version_cannot_be_resolved():
    """``continue-on-error`` turns an empty pin into a green run, so the job must exit 1.

    A run that resolved no version would test nothing and still be reported as success, which
    is worse than having no job at all -- the gate would look healthy while being blind.
    """
    steps = _core_latest_job().get("steps") or []
    resolve_step = None
    for step in steps:
        if isinstance(step, dict) and step.get("id") == "core":
            resolve_step = step
            break

    assert resolve_step is not None, "the core-latest job has no step with `id: core`"
    run = resolve_step.get("run") or ""
    assert "exit 1" in run, run
    assert '>> "$GITHUB_OUTPUT"' in run, run
    assert "could not resolve newest dcc-mcp-core version" in run, run


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
