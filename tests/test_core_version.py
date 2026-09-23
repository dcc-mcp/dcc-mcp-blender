"""Tests for the dcc-mcp-core dependency range and the CI gates that protect it."""

from __future__ import annotations

import importlib.util
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


def _core_latest_step_runs():
    # type: () -> list
    """Return the ``run`` script of every ``core-latest`` step, unserialised.

    Asserting against the step scripts rather than one JSON blob of the whole job
    keeps each check bound to the command that has to carry it -- a substring
    found anywhere in the job is not evidence that the command doing the work
    still has it.
    """
    steps = _core_latest_job().get("steps") or []
    return [(step.get("run") or "") for step in steps if isinstance(step, dict)]


def _core_latest_pytest_statements():
    # type: () -> list
    """Return every pytest invocation of the ``core-latest`` job, one per shell statement.

    Splitting the ``run`` scripts on statement separators keeps the check honest:
    ``pytest a; pytest b`` still reports success when the first suite fails,
    because only the last exit code decides the step.
    """
    statements = []
    for run in _core_latest_step_runs():
        for statement in re.split(r";|\n", run):
            statement = statement.strip()
            if "pytest" in statement:
                statements.append(statement)
    return statements


def test_core_dependency_range_is_pinned_to_the_020x_series():
    """A future Core minor must fail at install time, not inside the matrix."""
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert '"dcc-mcp-core>=0.20.0,<0.21.0"' in pyproject


def _core_constraint():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'"dcc-mcp-core>=(?P<min>[^,]+),<(?P<max>[^"]+)"', pyproject)

    assert match is not None
    return match.group("min"), match.group("max")


def test_packaging_core_floor_matches_pyproject():
    min_version, _ = _core_constraint()

    assert _load_assemble_zip_module().MIN_CORE_VERSION == min_version


def test_packaging_core_ceiling_matches_pyproject():
    """The addon ZIP must never bundle a Core the dependency spec rejects."""
    _, max_version = _core_constraint()

    assert _load_assemble_zip_module().MAX_CORE_VERSION == max_version


def test_packaging_resolver_ignores_releases_above_the_ceiling(monkeypatch):
    """The resolver must filter on the ceiling, not merely declare it.

    Asserting that ``MAX_CORE_VERSION`` equals the pyproject bound only pins a
    constant. Filtering on ``< 1.0.0`` while leaving the constant untouched
    keeps that test green and ships an addon ZIP bundling a Core the adapter's
    own dependency spec refuses to install next to.
    """
    module = _load_assemble_zip_module()
    releases = ["0.20.32", "0.20.34", "0.21.0", "0.21.3", "1.0.0"]
    monkeypatch.setattr(module, "_fetch_json", lambda url: {"releases": {name: [] for name in releases}})

    assert module.resolve_core_version() == "0.20.34"


def test_preloaded_core_below_floor_is_rejected():
    from dcc_mcp_blender._core_compat import require_compatible_core

    with pytest.raises(RuntimeError, match="preloaded dcc-mcp-core 0.19.94"):
        require_compatible_core("0.19.94", module_path="/host/site-packages/dcc_mcp_core")


def test_preloaded_core_at_floor_is_accepted():
    from dcc_mcp_blender._core_compat import require_compatible_core

    require_compatible_core("0.20.0", module_path="/extension/site-packages/dcc_mcp_core")


def test_ci_exposes_a_core_latest_compatibility_job():
    """The early-warning job must stay in ci.yml.

    It is the only signal that a new Core minor breaks the Install SOP contract before the
    upper bound is bumped, and it is trivially easy to drop in an unrelated workflow edit.
    """
    job = _core_latest_job()
    runs = _core_latest_step_runs()

    # Advisory, not blocking: the whole point is to report drift without reddening the PR.
    assert job.get("continue-on-error") is True, job
    # The resolved version must reach the install command itself. Asserting only
    # the `dcc-mcp-core==` prefix would accept a hard-coded version, which
    # freezes the job on one Core forever and disables the early warning
    # silently -- the exact failure this job exists to surface.
    assert any("dcc-mcp-core==${{ steps.core.outputs.version }}" in run for run in runs), (
        "the job must install the resolved Core version, not a hard-coded one"
    )
    # Both suites must be exercised by one invocation, so a failure in the
    # first cannot hide the second behind a shared exit code.
    pytest_cmds = _core_latest_pytest_statements()
    assert pytest_cmds, "the core-latest job must run pytest"
    assert any("test_install_lifecycle.py" in cmd and "test_core_version.py" in cmd for cmd in pytest_cmds), (
        "the job must run both suites in a single pytest invocation"
    )
    # The suites have to run against the Core the job just resolved. Moved above
    # the install step they would test whatever `pip install -e ".[dev]"`
    # pulled in -- the pinned version -- and the gate would report on a Core it
    # never upgraded to, with every assertion above still satisfied.
    install_index = next(
        (index for index, run in enumerate(runs) if "dcc-mcp-core==${{ steps.core.outputs.version }}" in run),
        None,
    )
    pytest_index = next((index for index, run in enumerate(runs) if "pytest" in run), None)
    assert install_index is not None and pytest_index is not None, (install_index, pytest_index)
    assert install_index < pytest_index, (
        "the resolved Core must be installed before pytest runs, or the suites "
        "test the pinned version instead of the newest one"
    )


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
    # `exit 1` anywhere in the script is not enough: it has to sit inside the
    # branch that detects an empty version. Left outside -- or kept elsewhere in
    # the script while this branch loses it -- the step would report success on
    # a run that resolved nothing.
    empty_version_block = _empty_version_branch(run)
    assert empty_version_block is not None, run
    assert "exit 1" in empty_version_block, run
    assert '>> "$GITHUB_OUTPUT"' in run, run
    assert "could not resolve newest dcc-mcp-core version" in empty_version_block, run


def _empty_version_branch(script):
    # type: (str) -> Optional[str]
    """Return the body of the ``if [ -z "${version}" ]`` branch, or None.

    The branch is delimited by indentation, so this is a textual scope rather
    than a shell parse: it is enough to tell an ``exit 1`` inside the branch
    from one that merely exists elsewhere in the script.
    """
    lines = script.splitlines()
    for index, line in enumerate(lines):
        if not re.search(r'if\s*\[\s*-z\s*"\$\{version\}"\s*\]', line):
            continue
        body = []
        indent = len(line) - len(line.lstrip())
        for follower in lines[index + 1 :]:
            if not follower.strip():
                continue
            follower_indent = len(follower) - len(follower.lstrip())
            if follower_indent <= indent:
                break
            body.append(follower)
        return "\n".join(body)
    return None
