"""Run pytest E2E tests inside a real Blender background process."""

from __future__ import annotations

import json
import os
import sys
import traceback
from types import BuiltinFunctionType, ModuleType


class ExecutionEvidence:
    """Count actual pytest outcomes without changing per-test skip policy."""

    def __init__(self):
        self.counts = {"collected": 0, "passed": 0, "skipped": 0, "failed": 0, "errors": 0, "xfailed": 0, "xpassed": 0}

    def pytest_collection_finish(self, session):
        self.counts["collected"] = len(session.items)

    def pytest_collectreport(self, report):
        if report.failed:
            self.counts["errors"] += 1
        elif report.skipped:
            self.counts["skipped"] += 1

    def pytest_runtest_logreport(self, report):
        if hasattr(report, "wasxfail"):
            self.counts["xfailed" if report.skipped else "xpassed"] += 1
        elif report.failed:
            self.counts["failed" if report.when == "call" else "errors"] += 1
        elif report.skipped:
            self.counts["skipped"] += 1
        elif report.when == "call" and report.passed:
            self.counts["passed"] += 1


def host_evidence():
    """Read native RNA state, rejecting absent or mock-only Blender imports."""
    import bpy

    if not isinstance(bpy, ModuleType) or bpy.app.background is not True:
        raise RuntimeError("A Blender background process is required")
    version = bpy.app.version
    if not isinstance(version, tuple) or len(version) != 3 or any(type(part) is not int for part in version):
        raise RuntimeError("Blender version evidence is unavailable")
    scene = bpy.context.scene
    if scene.bl_rna.identifier != "Scene" or not isinstance(scene.as_pointer, BuiltinFunctionType):
        raise RuntimeError("Native Blender scene RNA is required")
    pointer = scene.as_pointer()
    if type(pointer) is not int or pointer <= 0:
        raise RuntimeError("Native Blender scene is unavailable")
    return {"blender_version": list(version), "background": True, "scene_rna": "Scene"}


def report_evidence(evidence, reason, exit_code, host):
    """Emit one compact record before the process bypasses native cleanup."""
    print(
        "BLENDER_E2E_EVIDENCE "
        + json.dumps({"counts": evidence.counts, "host": host, "reason": reason, "exit_code": exit_code}),
        flush=True,
    )


def main() -> int:
    workspace = os.environ.get("GITHUB_WORKSPACE", ".")
    dep_dir = os.environ.get("BLENDER_E2E_SITE")
    if dep_dir and os.path.isdir(dep_dir) and dep_dir not in sys.path:
        sys.path.insert(0, dep_dir)

    if workspace not in sys.path:
        sys.path.insert(0, workspace)

    src_dir = os.path.join(workspace, "src")
    if os.path.isdir(src_dir) and src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    evidence = ExecutionEvidence()
    try:
        host = host_evidence()
    except (ImportError, AttributeError, RuntimeError, TypeError, ValueError):
        report_evidence(evidence, "host_unavailable", 1, None)
        return 1

    import pytest

    exit_code = int(
        pytest.main(
            [
                os.path.join(workspace, "tests", "e2e"),
                "-v",
                "--tb=short",
                "-m",
                "e2e",
                "--override-ini=addopts=",
            ],
            plugins=[evidence],
        )
    )
    if exit_code == 5:
        reason = "no_tests_collected"
    elif exit_code:
        reason = "pytest_failed"
    elif evidence.counts["passed"] == 0:
        reason = "no_tests_passed"
        exit_code = 1
    else:
        reason = "passed"
    report_evidence(evidence, reason, exit_code, host)
    sys.stdout.flush()
    sys.stderr.flush()
    return exit_code


if __name__ == "__main__":
    # Bypass Blender C++ cleanup in Linux background mode; sys.exit() can
    # otherwise try to destroy uninitialized X11/OpenGL resources.
    try:
        status = main()
    except Exception:
        traceback.print_exc()
        status = 1
        report_evidence(ExecutionEvidence(), "runner_error", status, None)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(status)
