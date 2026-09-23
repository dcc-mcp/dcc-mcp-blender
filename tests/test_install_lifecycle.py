"""Install SOP v1 contract tests for the Blender adapter."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).parent.parent


def test_package_exposes_the_standard_lifecycle_console_entrypoint():
    """Agents discover one standard adapter command from installed metadata."""
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "[project.scripts]" in pyproject
    assert 'dcc-mcp-blender = "dcc_mcp_blender.install:main"' in pyproject


def test_install_runbook_covers_the_public_lifecycle_and_catalog_route():
    """The owning repository documents the exact executable SOP contract."""
    guide = (ROOT / "install.md").read_text(encoding="utf-8")

    for heading in (
        "## Requirements",
        "## Supported versions",
        "## Agent quick path",
        "## Manual path",
        "## Verify",
        "## Upgrade",
        "## Uninstall",
        "## Troubleshooting",
    ):
        assert heading in guide
    for platform in ("Windows", "macOS", "Linux"):
        assert platform in guide
    for verb in ("install", "status", "verify", "uninstall", "upgrade"):
        assert "dcc-mcp-blender %s" % verb in guide
    for flag in ("--json", "--yes", "--dry-run", "--dcc-path", "--python"):
        assert flag in guide
    for code in ("`0`", "`10`", "`20`", "`30`", "`40`", "`50`"):
        assert code in guide
    for term in (
        "directly_usable",
        "receipt",
        "rollback",
        "capture_bootstrap_errors",
        "host.ping",
        "https://raw.githubusercontent.com/dcc-mcp/dcc-mcp-blender/main/install.md",
    ):
        assert term in guide


def test_setup_skill_routes_agents_to_the_standard_lifecycle_first():
    """The discoverable setup skill must not present the legacy script as canonical."""
    skill = (ROOT / "skills" / "dcc-mcp-blender-setup" / "SKILL.md").read_text(encoding="utf-8")

    assert "dcc-mcp-blender install --json --dry-run" in skill
    assert "dcc-mcp-blender verify --json" in skill
    assert "Legacy compatibility path" in skill


def test_install_dry_run_emits_a_complete_non_mutating_plan(tmp_path, monkeypatch, capsys):
    """The public CLI must plan the exact Blender target without writing it."""
    from dcc_mcp_blender import install

    blender = tmp_path / "blender"
    blender.write_bytes(b"")
    user_scripts = tmp_path / "user-scripts"
    receipt = tmp_path / "receipts" / "blender.json"
    monkeypatch.setenv("DCC_MCP_BLENDER_VERSION", "4.2.0")
    monkeypatch.setenv("DCC_MCP_BLENDER_USER_SCRIPTS", str(user_scripts))
    monkeypatch.setenv("DCC_MCP_BLENDER_RECEIPT", str(receipt))

    exit_code = install.main(
        [
            "install",
            "--json",
            "--dry-run",
            "--dcc-path",
            str(blender),
            "--python",
            sys.executable,
        ]
    )

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert report["schema_version"] == install.report_schema_version()
    assert report["status"] == "planned"
    assert report["dcc_type"] == "blender"
    assert report["install_state"] == "fresh"
    assert report["host"]["path"] == str(blender.resolve())
    assert report["host"]["version"] == "4.2.0"
    assert report["python"]["path"] == str(Path(sys.executable).resolve())
    assert [step["id"] for step in report["steps"]] == [
        "preflight",
        "stage",
        "commit",
        "verify",
    ]
    assert "--yes" in report["next_steps"][0]["command"]
    assert not (user_scripts / "startup" / "dcc_mcp_blender_startup.py").exists()
    assert not receipt.exists()


def test_install_requires_an_explicit_target_interpreter(tmp_path, monkeypatch, capsys):
    """The agent CLI interpreter is not implicitly a Blender-owned interpreter."""
    from dcc_mcp_blender import install

    blender = tmp_path / "blender"
    blender.write_bytes(b"")
    monkeypatch.setenv("DCC_MCP_BLENDER_VERSION", "4.2.0")
    monkeypatch.delenv("DCC_MCP_INSTALL_PYTHON", raising=False)

    exit_code = install.main(["install", "--json", "--dry-run", "--dcc-path", str(blender)])

    report = json.loads(capsys.readouterr().out)
    assert exit_code == install.INSTALL_EXIT_PREFLIGHT
    assert report["verify"]["failure_stage"] == "python"
    assert report["verify"]["failure_reason"] == "python_required"
    assert report["next_steps"][0]["command"][5] == "<absolute-blender-python>"


def test_environment_selected_interpreter_reports_its_real_source(tmp_path, monkeypatch, capsys):
    """Machine-provided interpreter selection must not be mislabeled as --python."""
    from dcc_mcp_blender import install

    blender = tmp_path / "blender"
    blender.write_bytes(b"")
    monkeypatch.setenv("DCC_MCP_BLENDER_VERSION", "4.2.0")
    monkeypatch.setenv("DCC_MCP_INSTALL_PYTHON", sys.executable)
    monkeypatch.setenv("DCC_MCP_BLENDER_USER_SCRIPTS", str(tmp_path / "scripts"))
    monkeypatch.setenv("DCC_MCP_BLENDER_RECEIPT", str(tmp_path / "receipt.json"))

    exit_code = install.main(["install", "--json", "--dry-run", "--dcc-path", str(blender)])

    report = json.loads(capsys.readouterr().out)
    assert exit_code == install.INSTALL_EXIT_OK
    assert report["python"]["path"] == str(Path(sys.executable).resolve())
    assert report["python"]["selection_source"] == "DCC_MCP_INSTALL_PYTHON"


def test_receipt_round_trip_is_convergent_and_uninstall_is_idempotent(tmp_path, monkeypatch, capsys):
    """Host enablement remains installed when only live readiness is unavailable."""
    from dcc_mcp_blender import install

    blender = tmp_path / "blender"
    blender.write_bytes(b"")
    user_scripts = tmp_path / "user-scripts"
    receipt_path = tmp_path / "receipts" / "blender.json"
    registry = tmp_path / "registry"
    monkeypatch.setenv("DCC_MCP_BLENDER_VERSION", "4.2.0")
    monkeypatch.setenv("DCC_MCP_BLENDER_USER_SCRIPTS", str(user_scripts))
    monkeypatch.setenv("DCC_MCP_BLENDER_RECEIPT", str(receipt_path))
    monkeypatch.setenv("DCC_MCP_REGISTRY_DIR", str(registry))
    common = [
        "--json",
        "--dcc-path",
        str(blender),
        "--python",
        sys.executable,
    ]

    assert install.main(["install", "--yes", *common]) == install.INSTALL_EXIT_VERIFY
    first = json.loads(capsys.readouterr().out)
    startup_path = user_scripts / "startup" / install.STARTUP_SCRIPT_NAME
    assert first["status"] == "partial"
    assert first["verify"]["directly_usable"] is False
    assert first["verify"]["failure_stage"] == "readiness"
    assert startup_path.is_file()
    assert "capture_bootstrap_errors" in startup_path.read_text(encoding="utf-8")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["files"][0]["path"] == str(startup_path.resolve())
    assert receipt["files"][0]["sha256"]

    assert install.main(["install", "--yes", *common]) == install.INSTALL_EXIT_VERIFY
    second = json.loads(capsys.readouterr().out)
    assert second["install_state"] == "current"
    assert not list(user_scripts.rglob("*.backup-*"))
    assert not list(user_scripts.rglob("*.stage-*"))

    assert install.main(["status", *common]) == install.INSTALL_EXIT_OK
    assert json.loads(capsys.readouterr().out)["install_state"] == "current"

    assert install.main(["uninstall", "--yes", *common]) == install.INSTALL_EXIT_OK
    assert json.loads(capsys.readouterr().out)["status"] == "ok"
    assert not startup_path.exists()
    assert not receipt_path.exists()

    assert install.main(["uninstall", "--yes", *common]) == install.INSTALL_EXIT_OK
    assert json.loads(capsys.readouterr().out)["steps"][0]["status"] == "already_absent"


def test_install_preserves_unreceipted_marker_spoof(tmp_path, monkeypatch, capsys):
    """A comment containing the legacy marker is not proof of adapter ownership."""
    from dcc_mcp_blender import install

    blender = tmp_path / "blender"
    blender.write_bytes(b"")
    startup_path = tmp_path / "scripts" / "startup" / install.STARTUP_SCRIPT_NAME
    startup_path.parent.mkdir(parents=True)
    spoof = '# Auto-start dcc-mcp-blender\nraise RuntimeError("operator owned")\n'
    startup_path.write_text(spoof, encoding="utf-8")
    receipt_path = tmp_path / "receipt.json"
    monkeypatch.setenv("DCC_MCP_BLENDER_VERSION", "4.2.0")
    monkeypatch.setenv("DCC_MCP_BLENDER_USER_SCRIPTS", str(tmp_path / "scripts"))
    monkeypatch.setenv("DCC_MCP_BLENDER_RECEIPT", str(receipt_path))

    exit_code = install.main(
        [
            "install",
            "--yes",
            "--json",
            "--dcc-path",
            str(blender),
            "--python",
            sys.executable,
        ]
    )

    report = json.loads(capsys.readouterr().out)
    assert exit_code == install.INSTALL_EXIT_PREFLIGHT
    assert report["verify"]["failure_reason"] == "unreceipted_startup_script"
    assert startup_path.read_text(encoding="utf-8") == spoof
    assert not receipt_path.exists()


def test_install_repairs_only_exact_generated_unreceipted_startup(tmp_path, monkeypatch, capsys):
    """Losing a receipt is repairable only for exact known generated content."""
    from dcc_mcp_blender import install

    blender = tmp_path / "blender"
    blender.write_bytes(b"")
    startup_path = tmp_path / "scripts" / "startup" / install.STARTUP_SCRIPT_NAME
    receipt_path = tmp_path / "receipt.json"
    monkeypatch.setenv("DCC_MCP_BLENDER_VERSION", "4.2.0")
    monkeypatch.setenv("DCC_MCP_BLENDER_USER_SCRIPTS", str(tmp_path / "scripts"))
    monkeypatch.setenv("DCC_MCP_BLENDER_RECEIPT", str(receipt_path))
    monkeypatch.setenv("DCC_MCP_REGISTRY_DIR", str(tmp_path / "registry"))
    common = ["--json", "--dcc-path", str(blender), "--python", sys.executable]

    assert install.main(["install", "--yes", *common]) == install.INSTALL_EXIT_VERIFY
    capsys.readouterr()
    known_content = startup_path.read_text(encoding="utf-8")
    receipt_path.unlink()

    assert install.main(["install", "--yes", *common]) == install.INSTALL_EXIT_VERIFY
    report = json.loads(capsys.readouterr().out)
    assert report["install_state"] == "partial"
    assert startup_path.read_text(encoding="utf-8") == known_content
    assert receipt_path.is_file()


def test_upgrade_requires_a_receipt_and_reuses_the_install_transaction(tmp_path, monkeypatch, capsys):
    """Upgrade is distinct from fresh install but shares its safe commit path."""
    from dcc_mcp_blender import install

    blender = tmp_path / "blender"
    blender.write_bytes(b"")
    monkeypatch.setenv("DCC_MCP_BLENDER_VERSION", "4.2.0")
    monkeypatch.setenv("DCC_MCP_BLENDER_USER_SCRIPTS", str(tmp_path / "scripts"))
    monkeypatch.setenv("DCC_MCP_BLENDER_RECEIPT", str(tmp_path / "receipt.json"))
    monkeypatch.setenv("DCC_MCP_REGISTRY_DIR", str(tmp_path / "registry"))
    common = [
        "--json",
        "--dcc-path",
        str(blender),
        "--python",
        sys.executable,
    ]

    assert install.main(["upgrade", "--dry-run", *common]) == install.INSTALL_EXIT_PREFLIGHT
    assert json.loads(capsys.readouterr().out)["verify"]["failure_reason"] == "receipt_missing"

    assert install.main(["install", "--yes", *common]) == install.INSTALL_EXIT_VERIFY
    capsys.readouterr()

    assert install.main(["upgrade", "--dry-run", *common]) == install.INSTALL_EXIT_OK
    plan = json.loads(capsys.readouterr().out)
    assert plan["status"] == "planned"
    assert plan["plan_type"] == "upgrade"

    assert install.main(["upgrade", "--yes", *common]) == install.INSTALL_EXIT_VERIFY
    result = json.loads(capsys.readouterr().out)
    assert result["command"] == "upgrade"
    assert result["verify"]["failure_stage"] == "readiness"


def test_verify_refuses_interpreter_drift_from_the_receipt(tmp_path, monkeypatch, capsys):
    """Verification must stay bound to the exact interpreter selected at install time."""
    from dcc_mcp_blender import install

    blender = tmp_path / "blender"
    blender.write_bytes(b"")
    receipt_path = tmp_path / "receipt.json"
    monkeypatch.setenv("DCC_MCP_BLENDER_VERSION", "4.2.0")
    monkeypatch.setenv("DCC_MCP_BLENDER_USER_SCRIPTS", str(tmp_path / "scripts"))
    monkeypatch.setenv("DCC_MCP_BLENDER_RECEIPT", str(receipt_path))
    monkeypatch.setenv("DCC_MCP_REGISTRY_DIR", str(tmp_path / "registry"))
    common = [
        "--json",
        "--dcc-path",
        str(blender),
        "--python",
        sys.executable,
    ]

    assert install.main(["install", "--yes", *common]) == install.INSTALL_EXIT_VERIFY
    capsys.readouterr()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["python"]["path"] = str((tmp_path / "old-python").resolve())
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    assert install.main(["verify", *common]) == install.INSTALL_EXIT_PREFLIGHT
    report = json.loads(capsys.readouterr().out)
    assert report["verify"]["failure_stage"] == "python"
    assert report["verify"]["failure_reason"] == "python_mismatch"


def test_public_reports_satisfy_the_shared_install_sop_schema(tmp_path, monkeypatch, capsys):
    """Every lifecycle verb emits a report the adapter's own validator accepts.

    The check runs through ``loads_public_report`` rather than comparing the
    required key set: a structural check accepts reports Core's validator
    rejects, so it cannot prove the emitted document satisfies the contract.
    """
    from dcc_mcp_blender import install

    schema = install.load_install_sop_schema()
    # Core republishes the Install SOP schema artifact: ``-v1`` is frozen at the bytes core
    # 0.20.30-0.20.33 shipped and ``-v2`` is where content changes land from here on. The ``-vN``
    # suffix is the identity of a published artifact, not an adapter contract, so assert the
    # canonical id namespace plus the document's own pin on the report field rather than one
    # revision. Hard-coding ``-v1`` here broke main the day core served ``-v2``.
    assert schema["$id"].startswith("https://dcc-mcp.github.io/schemas/adapter-install-sop-v")
    assert schema["$id"].endswith(".schema.json")
    assert schema["properties"]["schema_version"]["const"] == install.report_schema_version()
    required = set(schema["required"])

    blender = tmp_path / "blender"
    blender.write_bytes(b"")
    monkeypatch.setenv("DCC_MCP_BLENDER_VERSION", "4.2.0")
    monkeypatch.setenv("DCC_MCP_BLENDER_USER_SCRIPTS", str(tmp_path / "scripts"))
    monkeypatch.setenv("DCC_MCP_BLENDER_RECEIPT", str(tmp_path / "receipt.json"))
    common = [
        "--json",
        "--dcc-path",
        str(blender),
        "--python",
        sys.executable,
    ]

    for verb in install.LIFECYCLE_COMMANDS:
        arguments = [verb, "--dry-run", *common] if verb != "status" else [verb, *common]
        install.main(arguments)
        report = install.loads_public_report(capsys.readouterr().out)
        assert required <= set(report), verb
        assert report["schema_version"] == install.report_schema_version()
        # The document itself stays the reference: the adapter validator may
        # degrade to a structural check when Core's native validator is absent.
        Draft202012Validator(schema).validate(report)


def _schema_document(const):
    """A minimal Core schema document enforcing one ``schema_version`` const."""
    return {"properties": {"schema_version": {"const": const, "type": "integer"}}}


def test_report_schema_version_follows_published_document(monkeypatch):
    """The report field comes from the ``const`` Core's validator enforces."""
    from dcc_mcp_blender import install

    monkeypatch.setattr(install, "_published_schema", lambda: _schema_document(7))

    assert install.report_schema_version() == 7


def test_report_schema_version_ignores_cores_artifact_revision(monkeypatch):
    """Core's exported constant is the artifact revision, not the report field.

    Core 0.20.34 exports ``INSTALL_SOP_SCHEMA_VERSION = 2`` (the ``-v2`` artifact
    revision) while the report field must stay at the document's ``const`` of 1,
    because v2 only adds an optional ``catalog`` object. These are separate
    quantities that merely agreed while both were 1, so the constant must never
    reach the report.
    """
    from dcc_mcp_blender import install

    monkeypatch.setattr(install, "_published_schema", lambda: _schema_document(1))
    monkeypatch.setattr(install, "INSTALL_SOP_SCHEMA_VERSION", 2)

    assert install.report_schema_version() == 1


def test_report_schema_version_falls_back_when_document_is_unreadable(monkeypatch):
    """A Core with no readable schema document still yields a usable report."""
    from dcc_mcp_blender import install

    monkeypatch.setattr(install, "_published_schema", lambda: None)

    assert install.report_schema_version() == install.FALLBACK_REPORT_SCHEMA_VERSION


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("Install SOP schema integrity error: schema_digest_mismatch"),
        OSError("schema file unreadable"),
        ValueError("schema document is not valid JSON"),
    ],
)
def test_report_schema_version_survives_schema_read_failure(monkeypatch, error):
    """An unhealthy Core must not stop the CLI from emitting a report.

    Core verifies its schema document with a SHA-256 digest and raises on a
    missing, tampered, or unparsable document. Broken installs are exactly the
    situation this CLI exists to report on, so the read failure has to degrade
    to the fallback value instead of propagating.
    """
    from dcc_mcp_blender import install

    def _raise():
        raise error

    monkeypatch.setattr(install, "_published_schema", _raise)

    assert install.report_schema_version() == install.FALLBACK_REPORT_SCHEMA_VERSION


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("Install SOP schema integrity error: schema_digest_mismatch"),
        OSError("schema file unreadable"),
        ValueError("schema document is not valid JSON"),
    ],
)
def test_validate_public_report_survives_schema_read_failure(monkeypatch, error):
    """Validation must degrade, not raise, when the schema document is unreadable.

    The emitter in ``main()`` prints the report without validating it, so this
    covers the consumer side: ``loads_public_report()`` and any other caller that
    validates a report, including the failure report built when an install
    is already broken. Guarding only the value lookup while leaving the
    validation-path read unguarded lets a caller compute a report it then
    crashes on.
    """
    from dcc_mcp_blender import install

    def _raise():
        raise error

    monkeypatch.setattr(install, "_published_schema", _raise)
    report = {
        "schema_version": install.report_schema_version(),
        "status": "failed",
        "dcc_type": "blender",
        "adapter_version": "0.2.8",
        "core_version": "0.20.34",
        "steps": [],
        "next_steps": [],
        "receipt_path": None,
        "verify": {
            "directly_usable": False,
            "failure_stage": "preflight",
            "failure_reason": "not_installed",
        },
    }

    install.validate_public_report(report)  # must not raise

    # Degrading must not mean accepting anything.
    broken = dict(report)
    broken["schema_version"] = install.report_schema_version() + 1
    with pytest.raises(ValueError):
        install.validate_public_report(broken)


def test_public_report_validation_uses_cores_native_validator(tmp_path, monkeypatch, capsys):
    """Report validation runs through Core's Rust-backed validator, not jsonschema."""
    from dcc_mcp_blender import install

    blender = tmp_path / "blender"
    blender.write_bytes(b"")
    monkeypatch.setenv("DCC_MCP_BLENDER_VERSION", "4.2.0")
    monkeypatch.setenv("DCC_MCP_BLENDER_USER_SCRIPTS", str(tmp_path / "scripts"))
    monkeypatch.setenv("DCC_MCP_BLENDER_RECEIPT", str(tmp_path / "receipt.json"))

    install.main(["status", "--json", "--dcc-path", str(blender), "--python", sys.executable])
    report = json.loads(capsys.readouterr().out)

    calls = []
    monkeypatch.setattr(install, "_native_report_validator", lambda: calls.append)

    install.validate_public_report(report)

    assert calls == [report]
    # The adapter itself must never reach for a third-party schema package:
    # Core compiles Draft 2020-12 validation into its native extension module.
    source = Path(install.__file__).read_text(encoding="utf-8")
    assert "jsonschema" not in source


def test_public_report_validation_still_rejects_invalid_reports(tmp_path, monkeypatch, capsys):
    """A report that breaks the Install SOP contract still raises ValueError."""
    from dcc_mcp_blender import install

    blender = tmp_path / "blender"
    blender.write_bytes(b"")
    monkeypatch.setenv("DCC_MCP_BLENDER_VERSION", "4.2.0")
    monkeypatch.setenv("DCC_MCP_BLENDER_USER_SCRIPTS", str(tmp_path / "scripts"))
    monkeypatch.setenv("DCC_MCP_BLENDER_RECEIPT", str(tmp_path / "receipt.json"))

    install.main(["status", "--json", "--dcc-path", str(blender), "--python", sys.executable])
    report = json.loads(capsys.readouterr().out)

    report["schema_version"] = install.report_schema_version() + 1
    with pytest.raises(ValueError):
        install.validate_public_report(report)

    report["schema_version"] = install.report_schema_version()
    del report["verify"]
    with pytest.raises(ValueError):
        install.validate_public_report(report)


def test_structural_fallback_rejects_non_integer_schema_version(tmp_path, monkeypatch, capsys):
    """The degraded structural check must not accept ``schema_version: true``.

    ``bool`` is an ``int`` subclass and ``True == 1``, so a plain equality test
    lets a boolean through whenever the expected value is 1. The degraded path
    runs whenever Core's native validator or schema document is unavailable,
    which is exactly when a malformed external document is most likely to be
    read -- and Core's own schema requires the field to be an integer.
    """
    from dcc_mcp_blender import install

    blender = tmp_path / "blender"
    blender.write_bytes(b"")
    monkeypatch.setenv("DCC_MCP_BLENDER_VERSION", "4.2.0")
    monkeypatch.setenv("DCC_MCP_BLENDER_USER_SCRIPTS", str(tmp_path / "scripts"))
    monkeypatch.setenv("DCC_MCP_BLENDER_RECEIPT", str(tmp_path / "receipt.json"))
    monkeypatch.setattr(install, "_native_report_validator", lambda: None)

    install.main(["status", "--json", "--dcc-path", str(blender), "--python", sys.executable])
    report = json.loads(capsys.readouterr().out)

    expected = install.report_schema_version()
    for bogus in (True, False, float(expected), str(expected), None):
        candidate = dict(report)
        candidate["schema_version"] = bogus
        with pytest.raises(ValueError):
            install.validate_public_report(candidate)


def test_runtime_dependencies_exclude_jsonschema():
    """The adapter validates at runtime through Core, not a third-party package."""
    from dcc_mcp_blender import install

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    runtime = pyproject.split("[project.optional-dependencies]")[0]

    assert "jsonschema" not in runtime
    if install._native_report_validator() is None:
        # Core renamed or dropped the symbol. That drift belongs to the
        # core-latest early-warning job; failing here would redden the main
        # matrix on a Core change, which is the opposite of what the pin is for.
        pytest.skip(
            "Core does not export `validate_install_sop_report`; the core-latest "
            "job reports this drift instead of the main matrix."
        )


def test_emitted_report_satisfies_cores_published_schema():
    """The report field agrees with the const in the document Core serves.

    Guards the real dependency rather than a stub: if Core ever republishes the
    artifact with a different document version, this pins the adapter to follow
    the document instead of the ``-vN`` revision constant.
    """
    from dcc_mcp_blender import install

    schema = install.load_install_sop_schema()
    const = schema["properties"]["schema_version"]["const"]

    assert install.report_schema_version() == const


def test_missing_receipted_startup_is_reported_as_partial(tmp_path, monkeypatch, capsys):
    """Status must diagnose stale receipts instead of claiming a current install."""
    from dcc_mcp_blender import install

    blender = tmp_path / "blender"
    blender.write_bytes(b"")
    user_scripts = tmp_path / "scripts"
    monkeypatch.setenv("DCC_MCP_BLENDER_VERSION", "4.2.0")
    monkeypatch.setenv("DCC_MCP_BLENDER_USER_SCRIPTS", str(user_scripts))
    monkeypatch.setenv("DCC_MCP_BLENDER_RECEIPT", str(tmp_path / "receipt.json"))
    monkeypatch.setenv("DCC_MCP_REGISTRY_DIR", str(tmp_path / "registry"))
    common = [
        "--json",
        "--dcc-path",
        str(blender),
        "--python",
        sys.executable,
    ]

    assert install.main(["install", "--yes", *common]) == install.INSTALL_EXIT_VERIFY
    capsys.readouterr()
    (user_scripts / "startup" / install.STARTUP_SCRIPT_NAME).unlink()

    assert install.main(["status", *common]) == install.INSTALL_EXIT_PREFLIGHT
    report = json.loads(capsys.readouterr().out)
    assert report["install_state"] == "partial"
    assert report["steps"] == [
        {"id": "receipt", "status": "present"},
        {"id": "startup", "status": "absent"},
    ]


def test_malformed_receipt_status_is_typed_partial_not_internal_failure(tmp_path, monkeypatch, capsys):
    """Corrupt ownership metadata remains a repairable, classified preflight state."""
    from dcc_mcp_blender import install

    blender = tmp_path / "blender"
    blender.write_bytes(b"")
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text("[]", encoding="utf-8")
    monkeypatch.setenv("DCC_MCP_BLENDER_VERSION", "4.2.0")
    monkeypatch.setenv("DCC_MCP_BLENDER_USER_SCRIPTS", str(tmp_path / "scripts"))
    monkeypatch.setenv("DCC_MCP_BLENDER_RECEIPT", str(receipt_path))

    assert (
        install.main(
            [
                "status",
                "--json",
                "--dcc-path",
                str(blender),
                "--python",
                sys.executable,
            ]
        )
        == install.INSTALL_EXIT_PREFLIGHT
    )
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "partial"
    assert report["install_state"] == "partial"
    assert report["verify"]["failure_stage"] == "receipt"
    assert report["verify"]["failure_reason"] == "receipt_invalid"


def test_verify_rejects_malformed_receipt_ownership_as_a_typed_failure(tmp_path, monkeypatch, capsys):
    """Malformed file ownership cannot escape the verify exit-code boundary."""
    from dcc_mcp_blender import install

    blender = tmp_path / "blender"
    blender.write_bytes(b"")
    receipt_path = tmp_path / "receipt.json"
    monkeypatch.setenv("DCC_MCP_BLENDER_VERSION", "4.2.0")
    monkeypatch.setenv("DCC_MCP_BLENDER_USER_SCRIPTS", str(tmp_path / "scripts"))
    monkeypatch.setenv("DCC_MCP_BLENDER_RECEIPT", str(receipt_path))
    monkeypatch.setenv("DCC_MCP_REGISTRY_DIR", str(tmp_path / "registry"))
    common = [
        "--json",
        "--dcc-path",
        str(blender),
        "--python",
        sys.executable,
    ]

    assert install.main(["install", "--yes", *common]) == install.INSTALL_EXIT_VERIFY
    capsys.readouterr()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["files"] = [42]
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    assert install.main(["verify", *common]) == install.INSTALL_EXIT_VERIFY
    report = json.loads(capsys.readouterr().out)
    assert report["verify"]["failure_stage"] == "receipt"
    assert report["verify"]["failure_reason"] == "receipt_ownership_invalid"


def test_typed_host_ping_is_required_for_direct_usability(tmp_path, monkeypatch, capsys):
    """A successful typed probe is the only path to directly_usable=true."""
    from dcc_mcp_blender import install

    blender = tmp_path / "blender"
    blender.write_bytes(b"")
    monkeypatch.setenv("DCC_MCP_BLENDER_VERSION", "4.2.0")
    monkeypatch.setenv("DCC_MCP_BLENDER_USER_SCRIPTS", str(tmp_path / "scripts"))
    monkeypatch.setenv("DCC_MCP_BLENDER_RECEIPT", str(tmp_path / "receipt.json"))
    monkeypatch.setattr(
        install,
        "query_runtime_state",
        lambda *_args, **_kwargs: {"entries": [{"mcp_url": "http://127.0.0.1:49152/mcp"}]},
    )
    probes = []

    def probe(url, tool_name, timeout_secs):
        probes.append((url, tool_name, timeout_secs))
        return {"success": True, "status": "probe_ok"}

    monkeypatch.setattr(install, "probe_sidecar_tool", probe)

    assert (
        install.main(
            [
                "install",
                "--yes",
                "--json",
                "--dcc-path",
                str(blender),
                "--python",
                sys.executable,
            ]
        )
        == install.INSTALL_EXIT_OK
    )
    report = json.loads(capsys.readouterr().out)
    assert report["verify"]["directly_usable"] is True
    assert probes == [("http://127.0.0.1:49152/mcp", "host.ping", 2.0)]


def test_uninstall_dry_run_describes_receipt_owned_removal(tmp_path, monkeypatch, capsys):
    """An uninstall plan must describe removal rather than installation stages."""
    from dcc_mcp_blender import install

    blender = tmp_path / "blender"
    blender.write_bytes(b"")
    monkeypatch.setenv("DCC_MCP_BLENDER_VERSION", "4.2.0")
    monkeypatch.setenv("DCC_MCP_BLENDER_USER_SCRIPTS", str(tmp_path / "scripts"))
    monkeypatch.setenv("DCC_MCP_BLENDER_RECEIPT", str(tmp_path / "receipt.json"))
    common = [
        "--json",
        "--dcc-path",
        str(blender),
        "--python",
        sys.executable,
    ]

    assert install.main(["uninstall", "--dry-run", *common]) == install.INSTALL_EXIT_OK
    report = json.loads(capsys.readouterr().out)
    assert [step["id"] for step in report["steps"]] == [
        "preflight",
        "receipt",
        "uninstall",
    ]
    assert report["next_steps"][0]["command"][1] == "uninstall"
    assert "--yes" in report["next_steps"][0]["command"]


def test_receipt_commit_failure_rolls_back_the_previous_install(tmp_path, monkeypatch, capsys):
    """A failed receipt commit must restore both previously owned artifacts."""
    from dcc_mcp_blender import install

    blender = tmp_path / "blender"
    blender.write_bytes(b"")
    startup_path = tmp_path / "scripts" / "startup" / install.STARTUP_SCRIPT_NAME
    receipt_path = tmp_path / "receipt.json"
    monkeypatch.setenv("DCC_MCP_BLENDER_VERSION", "4.2.0")
    monkeypatch.setenv("DCC_MCP_BLENDER_USER_SCRIPTS", str(tmp_path / "scripts"))
    monkeypatch.setenv("DCC_MCP_BLENDER_RECEIPT", str(receipt_path))
    monkeypatch.setenv("DCC_MCP_REGISTRY_DIR", str(tmp_path / "registry"))
    common = [
        "--json",
        "--dcc-path",
        str(blender),
        "--python",
        sys.executable,
    ]

    assert install.main(["install", "--yes", *common]) == install.INSTALL_EXIT_VERIFY
    capsys.readouterr()
    old_startup = startup_path.read_bytes()
    old_receipt = receipt_path.read_bytes()
    real_replace = install._replace_path

    def fail_receipt_commit(source, destination):
        if destination == receipt_path and ".stage-" in source.name:
            raise OSError("simulated receipt commit failure")
        return real_replace(source, destination)

    monkeypatch.setattr(install, "_replace_path", fail_receipt_commit)

    assert install.main(["install", "--yes", *common]) == install.INSTALL_EXIT_INSTALL
    report = json.loads(capsys.readouterr().out)
    assert report["verify"]["failure_reason"] == "commit_failed"
    assert startup_path.read_bytes() == old_startup
    assert receipt_path.read_bytes() == old_receipt
    assert not list(tmp_path.rglob("*.stage-*"))
    assert not list(tmp_path.rglob("*.backup-*"))


def test_windows_lock_is_a_restart_boundary_not_a_clean_install_failure(tmp_path, monkeypatch, capsys):
    """Locked owned files produce stable exit 50 and a restart-shaped result."""
    from dcc_mcp_blender import install

    blender = tmp_path / "blender"
    blender.write_bytes(b"")
    monkeypatch.setenv("DCC_MCP_BLENDER_VERSION", "4.2.0")
    monkeypatch.setenv("DCC_MCP_BLENDER_USER_SCRIPTS", str(tmp_path / "scripts"))
    monkeypatch.setenv("DCC_MCP_BLENDER_RECEIPT", str(tmp_path / "receipt.json"))
    common = [
        "--json",
        "--dcc-path",
        str(blender),
        "--python",
        sys.executable,
    ]

    monkeypatch.setattr(install, "_install_transaction", lambda _ctx: (_ for _ in ()).throw(PermissionError("locked")))
    monkeypatch.setattr(install, "_is_windows_lock", lambda _exc: True)

    assert install.main(["install", "--yes", *common]) == install.INSTALL_EXIT_REQUIRES_RESTART
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "requires_restart"
    assert report["verify"]["failure_stage"] == "install"
    assert report["verify"]["failure_reason"] == "windows_file_lock"
