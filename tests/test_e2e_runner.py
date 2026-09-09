"""Subprocess contracts for the CI runner; host doubles are not Blender acceptance."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import textwrap

import pytest

RUNNER = pathlib.Path(__file__).parents[1] / ".github" / "scripts" / "run_blender_e2e.py"
HOST_DOUBLE = """
from types import ModuleType, SimpleNamespace
host = ModuleType("bpy")
host.app = SimpleNamespace(version=(4, 4, 3), background=True)
host.context = SimpleNamespace(scene=SimpleNamespace(
    bl_rna=SimpleNamespace(identifier="Scene"), as_pointer={}.__sizeof__,
))
sys.modules["bpy"] = host
"""


def run_e2e_runner(tmp_path, test_source="", *, host=True, host_adjustment=""):
    """Run real pytest in a subprocess against a small, isolated test suite."""
    suite = tmp_path / "tests" / "e2e"
    suite.mkdir(parents=True)
    (suite / "test_contract.py").write_text(textwrap.dedent(test_source), encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest]\nmarkers = e2e: runner contract\n", encoding="utf-8")
    env = os.environ.copy()
    env.pop("BLENDER_E2E_SITE", None)
    env.pop("PYTHONPATH", None)
    env.pop("PYTEST_ADDOPTS", None)
    env["GITHUB_WORKSPACE"] = str(tmp_path)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    bootstrap = "import runpy, sys\n"
    bootstrap += HOST_DOUBLE if host else 'sys.modules["bpy"] = None\n'
    bootstrap += host_adjustment + "\n"
    bootstrap += "runpy.run_path(sys.argv[1], run_name='__main__')\n"
    return subprocess.run(
        [sys.executable, "-c", bootstrap, str(RUNNER)],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_runner_fails_when_no_tests_are_collected(tmp_path):
    result = run_e2e_runner(tmp_path)

    assert result.returncode != 0, result.stdout + result.stderr
    assert read_evidence(result)["reason"] == "no_tests_collected"


def read_evidence(result):
    """Read the runner's public evidence line from captured terminal output."""
    return json.loads(result.stdout.split("BLENDER_E2E_EVIDENCE ", 1)[1].splitlines()[0])


def test_runner_fails_when_every_test_is_skipped(tmp_path):
    result = run_e2e_runner(
        tmp_path,
        """
        import pytest
        pytestmark = pytest.mark.e2e

        def test_unavailable_feature():
            pytest.skip("Feature unavailable in this Blender version")
        """,
    )

    assert result.returncode != 0, result.stdout + result.stderr
    evidence = read_evidence(result)
    assert evidence["counts"]["passed"] == 0
    assert evidence["counts"]["skipped"] == 1
    assert evidence["reason"] == "no_tests_passed"


def test_runner_rejects_missing_blender_before_running_tests(tmp_path):
    result = run_e2e_runner(
        tmp_path,
        """
        import pytest
        pytestmark = pytest.mark.e2e

        def test_would_otherwise_pass():
            assert True
        """,
        host=False,
    )

    assert result.returncode != 0, result.stdout + result.stderr
    evidence = read_evidence(result)
    assert evidence["reason"] == "host_unavailable"
    assert evidence["counts"]["collected"] == 0


def test_runner_reports_startup_failure_when_pytest_is_missing(tmp_path):
    result = run_e2e_runner(tmp_path, host_adjustment="sys.modules['pytest'] = None")
    assert result.returncode == 1
    assert read_evidence(result)["reason"] == "runner_error"


def test_runner_allows_individual_skips_when_tests_pass_and_flushes_output(tmp_path):
    result = run_e2e_runner(
        tmp_path,
        """
        import sys
        import pytest
        pytestmark = pytest.mark.e2e

        def test_supported_feature():
            sys.__stdout__.write("stdout evidence marker")
            sys.__stderr__.write("stderr evidence marker")
            assert True

        def test_version_specific_feature():
            pytest.skip("Not supported by this Blender version")
        """,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    evidence = read_evidence(result)
    assert evidence["reason"] == "passed"
    assert evidence["counts"] == {
        "collected": 2,
        "passed": 1,
        "skipped": 1,
        "failed": 0,
        "errors": 0,
        "xfailed": 0,
        "xpassed": 0,
    }
    assert evidence["host"] == {"blender_version": [4, 4, 3], "background": True, "scene_rna": "Scene"}
    assert "stdout evidence marker" in result.stdout
    assert "stderr evidence marker" in result.stderr


@pytest.mark.parametrize(
    "host_adjustment",
    [
        "host.app.background = False",
        "host.app.version = '4.4.3'",
        "host.context.scene = None",
        "host.context.scene.as_pointer = lambda: 123",
        "from unittest.mock import MagicMock\nsys.modules['bpy'] = MagicMock()",
    ],
)
def test_runner_rejects_unavailable_or_mock_host_evidence(tmp_path, host_adjustment):
    result = run_e2e_runner(tmp_path, host_adjustment=host_adjustment)

    assert result.returncode != 0, result.stdout + result.stderr
    evidence = read_evidence(result)
    assert evidence["reason"] == "host_unavailable"
    assert evidence["host"] is None
    assert evidence["counts"]["collected"] == 0


@pytest.mark.parametrize(
    ("test_source", "pytest_exit_code", "counter"),
    [
        (
            "import pytest\npytestmark = pytest.mark.e2e\ndef test_failure():\n    assert False\n",
            1,
            "failed",
        ),
        ("raise RuntimeError('Collection failed')\n", 2, "errors"),
        (
            """
            import pytest
            pytestmark = pytest.mark.e2e
            @pytest.fixture(autouse=True)
            def broken_teardown():
                yield
                raise RuntimeError("Teardown failed")
            def test_body_passes():
                assert True
            """,
            1,
            "errors",
        ),
    ],
)
def test_runner_preserves_pytest_failures(tmp_path, test_source, pytest_exit_code, counter):
    result = run_e2e_runner(tmp_path, test_source)

    assert result.returncode == pytest_exit_code, result.stdout + result.stderr
    evidence = read_evidence(result)
    assert evidence["reason"] == "pytest_failed"
    assert evidence["counts"][counter] == 1


def test_runner_does_not_count_expected_failures_as_passing_host_tests(tmp_path):
    result = run_e2e_runner(
        tmp_path,
        """
        import pytest
        pytestmark = pytest.mark.e2e
        @pytest.mark.xfail(reason="Feature unavailable")
        def test_expected_failure():
            assert False
        """,
    )

    assert result.returncode != 0, result.stdout + result.stderr
    evidence = read_evidence(result)
    assert evidence["reason"] == "no_tests_passed"
    assert evidence["counts"]["passed"] == 0
    assert evidence["counts"]["xfailed"] == 1
