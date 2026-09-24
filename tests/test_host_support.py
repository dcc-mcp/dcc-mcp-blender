"""Host support boundary: declared window, dependency visibility, and error text."""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest

from dcc_mcp_blender import _host_support as host_support


def _flags(**overrides):
    base = {
        "ignore_environment": 0,
        "isolated": 0,
        "no_user_site": 0,
        "no_site": 0,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_user_site_flag_does_not_mean_pythonpath_is_suppressed(monkeypatch):
    """-s / PYTHONNOUSERSITE disables the user site; PYTHONPATH still works.

    Treating no_user_site as injection suppression made the preflight blame --
    and mis-remediate with --python-use-system-env -- hosts whose package paths
    are fully visible.
    """
    monkeypatch.setattr(sys, "flags", _flags(no_user_site=1))

    assert host_support.pythonpath_suppressed() is False
    assert host_support.user_site_suppressed() is True
    assert host_support.environment_injection_suppressed() is False


def test_isolated_flags_suppress_pythonpath_and_imply_user_site(monkeypatch):
    monkeypatch.setattr(sys, "flags", _flags(isolated=1, ignore_environment=1))

    assert host_support.pythonpath_suppressed() is True
    assert host_support.environment_injection_suppressed() is True


def test_diagnose_host_reports_both_injection_signals(monkeypatch):
    monkeypatch.setattr(sys, "flags", _flags(no_user_site=1))

    report = host_support.diagnose_host(("dcc_mcp_core",))

    assert report["pythonpath_suppressed"] is False
    assert report["user_site_suppressed"] is True
    assert report["environment_injection_suppressed"] is False


def test_user_site_only_failure_suggests_the_user_site_fix(monkeypatch):
    """A -s host gets the -s fix, not --python-use-system-env."""
    monkeypatch.setattr(sys, "flags", _flags(no_user_site=1))
    monkeypatch.setattr(host_support, "missing_distributions", lambda *args, **kwargs: ["dcc_mcp_core"])

    with pytest.raises(host_support.HostSupportError) as excinfo:
        host_support.require_supported_host()

    message = str(excinfo.value)
    assert "PYTHONNOUSERSITE" in message
    assert "--python-use-system-env" not in message


def test_missing_distributions_reports_invisible_modules(monkeypatch):
    assert host_support.missing_distributions(("dcc_mcp_core",)) == []
    assert host_support.missing_distributions(("_dcc_mcp_not_installed_xyz",)) == ["_dcc_mcp_not_installed_xyz"]


def test_missing_distributions_treats_loaded_modules_as_present(monkeypatch):
    monkeypatch.setitem(sys.modules, "_dcc_mcp_loaded_probe", object())
    assert host_support.missing_distributions(("_dcc_mcp_loaded_probe",)) == []


def test_environment_injection_suppressed_reads_interpreter_flags(monkeypatch):
    monkeypatch.setattr(sys, "flags", _flags())
    assert host_support.environment_injection_suppressed() is False

    monkeypatch.setattr(sys, "flags", _flags(isolated=1, ignore_environment=1, no_user_site=1))
    assert host_support.environment_injection_suppressed() is True


def test_diagnose_host_reports_window_and_visibility(monkeypatch):
    monkeypatch.setattr(sys, "flags", _flags())
    report = host_support.diagnose_host(("dcc_mcp_core",))

    assert report["supported"] is True
    assert report["missing_distributions"] == []
    assert report["environment_injection_suppressed"] is False
    assert report["python_min"] == "3.7"
    assert report["python_max_tested"] == "3.13"
    assert report["host_python"].startswith("%d.%d." % (sys.version_info[0], sys.version_info[1]))


def test_require_supported_host_passes_on_a_supported_host(monkeypatch):
    monkeypatch.setattr(sys, "flags", _flags())
    report = host_support.require_supported_host(("dcc_mcp_core",))

    assert report["supported"] is True


def test_require_supported_host_names_the_boundary_when_core_is_invisible(monkeypatch):
    """A host that cannot see dcc-mcp-core must not surface ModuleNotFoundError."""
    monkeypatch.setattr(sys, "flags", _flags(isolated=1, ignore_environment=1))
    monkeypatch.setattr(host_support, "missing_distributions", lambda *args, **kwargs: ["dcc_mcp_core"])

    with pytest.raises(host_support.HostSupportError) as excinfo:
        host_support.require_supported_host(adapter_version="0.2.10")

    message = str(excinfo.value)
    assert "ModuleNotFoundError" not in message
    assert "dcc-mcp-blender 0.2.10 is not usable in this host" in message
    assert "dcc_mcp_core" in message
    assert "declared window: >=3.7 (tested up to 3.13)" in message
    assert "environment injection: suppressed" in message
    # The remediation has to match the detected mode, not the install flavour.
    assert "--python-use-system-env" in message
    assert "pip install --user" not in message


def test_require_supported_host_suggests_install_when_injection_is_enabled(monkeypatch):
    monkeypatch.setattr(sys, "flags", _flags())
    monkeypatch.setattr(host_support, "missing_distributions", lambda *args, **kwargs: ["dcc_mcp_core"])

    with pytest.raises(host_support.HostSupportError) as excinfo:
        host_support.require_supported_host()

    message = str(excinfo.value)
    assert "environment injection: enabled" in message
    assert "pip install --user dcc-mcp-core" in message
    assert "--python-use-system-env" not in message


def test_require_supported_host_rejects_python_below_the_declared_minimum(monkeypatch):
    monkeypatch.setattr(sys, "flags", _flags())
    monkeypatch.setattr(host_support, "host_python_version", lambda: (3, 6, 9))

    with pytest.raises(host_support.HostSupportError) as excinfo:
        host_support.require_supported_host()

    message = str(excinfo.value)
    assert "below the declared minimum of 3.7" in message
    assert "3.6.9" in message


def test_newer_than_tested_python_is_reported_but_not_rejected(monkeypatch):
    """Python 3.13 hosts work, so a newer interpreter must not be refused outright."""
    monkeypatch.setattr(sys, "flags", _flags())
    monkeypatch.setattr(host_support, "host_python_version", lambda: (3, 14, 0))

    report = host_support.require_supported_host(("dcc_mcp_core",))

    assert report["supported"] is True
    assert report["python_beyond_tested"] is True


def test_main_exits_non_zero_and_prints_json_for_an_unsupported_host(monkeypatch, capsys):
    monkeypatch.setattr(sys, "flags", _flags(isolated=1, ignore_environment=1))
    monkeypatch.setattr(host_support, "missing_distributions", lambda *args, **kwargs: ["dcc_mcp_core"])

    assert host_support.main(["--json", "--require", "dcc_mcp_core"]) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["supported"] is False
    assert payload["missing_distributions"] == ["dcc_mcp_core"]
    assert payload["environment_injection_suppressed"] is True


def test_main_exits_zero_for_a_supported_host(monkeypatch, capsys):
    monkeypatch.setattr(sys, "flags", _flags())
    monkeypatch.setattr(host_support, "missing_distributions", lambda *args, **kwargs: [])

    assert host_support.main([]) == 0

    output = capsys.readouterr().out
    assert "dcc-mcp-blender host support: supported" in output
    assert "declared window: >=3.7" in output


def test_main_require_extends_the_default_set_instead_of_replacing_it(monkeypatch, capsys):
    """--require must never drop dcc_mcp_blender / dcc_mcp_core from the check.

    Replacing the defaults lets an invisible adapter report 'supported' -- the
    exact silent failure the preflight exists to catch.
    """
    seen = []

    def _record(required=(), *_args, **_kwargs):
        seen.append(tuple(required))
        return []

    monkeypatch.setattr(sys, "flags", _flags())
    monkeypatch.setattr(host_support, "missing_distributions", _record)

    assert host_support.main(["--require", "json"]) == 0

    assert seen == [("dcc_mcp_blender", "dcc_mcp_core", "json")]


def test_main_requires_adapter_even_when_another_distribution_is_requested(monkeypatch, capsys):
    """A host missing only the adapter must still fail the standalone preflight."""

    def _missing(required=(), *_args, **_kwargs):
        return [name for name in required if name == "dcc_mcp_blender"]

    monkeypatch.setattr(sys, "flags", _flags())
    monkeypatch.setattr(host_support, "missing_distributions", _missing)

    assert host_support.main(["--require", "json"]) == 1
    assert "missing distributions: dcc_mcp_blender" in capsys.readouterr().out


def test_main_ignores_host_arguments_passed_by_blender(monkeypatch, capsys):
    """'blender --python <script> -- --json' leaks Blender's own argv into the script."""
    monkeypatch.setattr(sys, "flags", _flags())
    monkeypatch.setattr(host_support, "missing_distributions", lambda *args, **kwargs: [])

    exit_code = host_support.main(["--background", "--factory-startup", "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["supported"] is True


def test_module_is_stdlib_only():
    """The preflight must stay importable by a host that cannot import the adapter."""
    source = host_support.__file__ or ""
    with open(source, encoding="utf-8") as handle:
        text = handle.read()

    for forbidden in ("import bpy", "import dcc_mcp_core", "from dcc_mcp_blender", "from ."):
        assert forbidden not in text, forbidden
