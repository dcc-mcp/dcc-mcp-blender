"""Declared host support window and explicit host-boundary errors.

Why this module exists
----------------------
Blender 5.x starts its bundled interpreter in isolated mode
(``sys.flags.ignore_environment == 1``), so ``PYTHONPATH`` entries injected by a
package environment never reach ``sys.path``. ``import dcc_mcp_blender`` then
fails with ``ModuleNotFoundError`` -- an error that names neither the host
boundary nor the fix, and that no adapter code can intercept because the
adapter itself is the module that failed to import.

This module owns the two boundaries the adapter *can* check for callers who do
reach it (an extension install, or a startup bridge whose adapter package is
visible while its ``dcc_mcp_core`` wheel is not):

1. the declared host Python window, and
2. visibility of the required distributions inside the running interpreter.

Both surface as :class:`HostSupportError`, carrying the host version, the
declared window, and the remediation that actually matches the detected mode.

There is deliberately **no enforced upper bound** on the host Python version.
The adapter imports cleanly on Blender 5.1.1 / Python 3.13.9 once its
dependencies are visible, and CI covers Blender 5.2.1; refusing newer
interpreters would block working hosts. ``HOST_PYTHON_MAX_TESTED`` is therefore
reported, not enforced.
"""

from __future__ import annotations

import importlib.util
import sys
from typing import Dict, List, Optional, Sequence, Tuple

# Skill scripts are syntax-checked against Python 3.7 (see tools/check_py37_syntax.py),
# so 3.7 is the floor of the declared window.
HOST_PYTHON_MIN = (3, 7)
# Highest host Python version this adapter is tested against (Blender 5.2 / 3.13).
HOST_PYTHON_MAX_TESTED = (3, 13)

REQUIRED_DISTRIBUTIONS = ("dcc_mcp_core",)

# The preflight must also be runnable by a host that cannot import the adapter at
# all ("blender --background --python <...>/_host_support.py"), so it checks the
# adapter itself as well when it runs as a script.
STANDALONE_REQUIRED_DISTRIBUTIONS = ("dcc_mcp_blender", "dcc_mcp_core")

_REMEDIATION_ISOLATED = (
    "the interpreter started with environment injection disabled "
    "(PYTHONPATH and the user site cannot reach sys.path) -- start Blender with "
    "--python-use-system-env, or install the Extension ZIP that bundles the wheel"
)
_REMEDIATION_VISIBLE = (
    "the host cannot see it -- install it into this interpreter "
    "(for Blender: '<blender python> -m pip install --user dcc-mcp-core')"
)


class HostSupportError(RuntimeError):
    """Raised when the running host cannot support this adapter."""


def host_python_version() -> Tuple[int, int, int]:
    """Return the running interpreter's ``(major, minor, micro)`` version."""
    return (sys.version_info[0], sys.version_info[1], sys.version_info[2])


def environment_injection_suppressed() -> bool:
    """Return True when the host ignores ``PYTHONPATH`` / user-site injection.

    Blender 5.x reports ``isolated=1``, ``ignore_environment=1`` and
    ``no_user_site=1``; any of them keeps package-environment paths out of
    ``sys.path``.
    """
    flags = sys.flags
    return bool(
        getattr(flags, "ignore_environment", 0) or getattr(flags, "isolated", 0) or getattr(flags, "no_user_site", 0)
    )


def missing_distributions(required: Sequence[str] = REQUIRED_DISTRIBUTIONS) -> List[str]:
    """Return the required distributions that this interpreter cannot import."""
    missing: List[str] = []
    for name in required:
        if name in sys.modules:
            continue
        try:
            spec = importlib.util.find_spec(name)
        except (ImportError, ValueError):
            # A broken parent package or an invalid __spec__ must not mask the
            # boundary error with a secondary traceback.
            spec = None
        if spec is None:
            missing.append(name)
    return missing


def diagnose_host(required: Sequence[str] = REQUIRED_DISTRIBUTIONS) -> Dict[str, object]:
    """Describe the running host against the declared support window."""
    version = host_python_version()
    missing = missing_distributions(required)
    below_min = version[:2] < HOST_PYTHON_MIN
    beyond_tested = version[:2] > HOST_PYTHON_MAX_TESTED
    return {
        "host_python": ".".join(str(part) for part in version),
        "executable": sys.executable,
        "python_min": ".".join(str(part) for part in HOST_PYTHON_MIN),
        "python_max_tested": ".".join(str(part) for part in HOST_PYTHON_MAX_TESTED),
        "python_below_min": below_min,
        "python_beyond_tested": beyond_tested,
        "environment_injection_suppressed": environment_injection_suppressed(),
        "required_distributions": list(required),
        "missing_distributions": missing,
        "supported": not below_min and not missing,
    }


def format_host_support_report(report: Dict[str, object]) -> str:
    """Render a :func:`diagnose_host` report as the body of a boundary error."""
    lines = [
        "host python: {host} ({executable})".format(host=report["host_python"], executable=report["executable"]),
        "declared window: >={min} (tested up to {max})".format(
            min=report["python_min"], max=report["python_max_tested"]
        ),
        "environment injection: {state}".format(
            state="suppressed" if report["environment_injection_suppressed"] else "enabled"
        ),
    ]
    missing = report["missing_distributions"] or []
    if missing:
        remediation = _REMEDIATION_ISOLATED if report["environment_injection_suppressed"] else _REMEDIATION_VISIBLE
        lines.append("missing distributions: {names} -- {fix}".format(names=", ".join(missing), fix=remediation))
    if report["python_below_min"]:
        lines.append("host python is below the declared minimum of {min}".format(min=report["python_min"]))
    if report["python_beyond_tested"]:
        lines.append(
            "host python is newer than the tested maximum of {max} -- continued only because no "
            "distributions are missing; report failures against this version".format(max=report["python_max_tested"])
        )
    return "\n  ".join(lines)


def require_supported_host(
    required: Sequence[str] = REQUIRED_DISTRIBUTIONS,
    *,
    adapter_version: Optional[str] = None,
) -> Dict[str, object]:
    """Reject hosts outside the declared window or missing required distributions.

    Raises :class:`HostSupportError` -- not ``ModuleNotFoundError`` -- so callers
    get the host version, the declared boundary, and the remediation that fits
    the detected interpreter mode.
    """
    report = diagnose_host(required)
    if report["supported"]:
        return report

    subject = "dcc-mcp-blender {version}".format(version=adapter_version) if adapter_version else "dcc-mcp-blender"
    reason = (
        "runs on Python {version}, below the declared minimum of {min}".format(
            version=report["host_python"], min=report["python_min"]
        )
        if report["python_below_min"]
        else "required distribution(s) are not importable"
    )
    raise HostSupportError(
        "{subject} is not usable in this host: {reason}.\n  {report}".format(
            subject=subject, reason=reason, report=format_host_support_report(report)
        )
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the preflight as a standalone script. Imports no adapter modules.

    Returns 0 when the host is supported and 1 when it is not, so a package
    environment can use it as the post-resolve self-check that turns a silent
    "resolve OK, adapter invisible" into a named boundary error.
    """
    import argparse
    import json

    parser = argparse.ArgumentParser(description="dcc-mcp-blender host support preflight")
    parser.add_argument("--json", action="store_true", help="print the diagnosis as JSON")
    parser.add_argument(
        "--require",
        action="append",
        dest="required",
        metavar="MODULE",
        help="add a required distribution (repeatable)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    required = tuple(args.required) if args.required else STANDALONE_REQUIRED_DISTRIBUTIONS
    report = diagnose_host(required)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        state = "supported" if report["supported"] else "UNSUPPORTED"
        print("dcc-mcp-blender host support: {state}".format(state=state))
        print("  " + format_host_support_report(report))
    return 0 if report["supported"] else 1


__all__ = [
    "HOST_PYTHON_MAX_TESTED",
    "HOST_PYTHON_MIN",
    "REQUIRED_DISTRIBUTIONS",
    "STANDALONE_REQUIRED_DISTRIBUTIONS",
    "HostSupportError",
    "diagnose_host",
    "environment_injection_suppressed",
    "format_host_support_report",
    "host_python_version",
    "main",
    "missing_distributions",
    "require_supported_host",
]


if __name__ == "__main__":  # pragma: no cover - exercised by the CLI, not the suite
    raise SystemExit(main())
