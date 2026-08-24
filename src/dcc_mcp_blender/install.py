"""Agent-first Install SOP v1 lifecycle for the Blender adapter."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import dcc_mcp_core

try:
    from dcc_mcp_core.deployment import inspect_install_root, probe_sidecar_tool, query_runtime_state
except ImportError:
    # Core releases before #2320 expose the same lifecycle API from this owner.
    from dcc_mcp_core.install_lifecycle import (
        inspect_install_root,
        probe_sidecar_tool,
        query_runtime_state,
    )

from .__version__ import __version__

try:
    from dcc_mcp_core.deployment import (
        INSTALL_EXIT_ACQUIRE,
        INSTALL_EXIT_CODES,
        INSTALL_EXIT_INSTALL,
        INSTALL_EXIT_OK,
        INSTALL_EXIT_PREFLIGHT,
        INSTALL_EXIT_REQUIRES_RESTART,
        INSTALL_EXIT_VERIFY,
        INSTALL_SOP_SCHEMA_VERSION,
        load_install_sop_schema,
    )
except ImportError:
    # Remove this compatibility boundary after dcc-mcp-core#2320 is released.
    INSTALL_SOP_SCHEMA_VERSION = 1
    INSTALL_EXIT_OK = 0
    INSTALL_EXIT_PREFLIGHT = 10
    INSTALL_EXIT_ACQUIRE = 20
    INSTALL_EXIT_INSTALL = 30
    INSTALL_EXIT_VERIFY = 40
    INSTALL_EXIT_REQUIRES_RESTART = 50
    INSTALL_EXIT_CODES = {
        "ok": INSTALL_EXIT_OK,
        "preflight": INSTALL_EXIT_PREFLIGHT,
        "acquire": INSTALL_EXIT_ACQUIRE,
        "install": INSTALL_EXIT_INSTALL,
        "verify": INSTALL_EXIT_VERIFY,
        "requires_restart": INSTALL_EXIT_REQUIRES_RESTART,
    }

    def load_install_sop_schema():
        # type: () -> Dict[str, Any]
        schema_path = Path(__file__).resolve().parent / "schemas" / "adapter-install-sop-v1.schema.json"
        return json.loads(schema_path.read_text(encoding="utf-8"))


DCC_TYPE = "blender"
COMMAND = "dcc-mcp-blender"
MIN_BLENDER_VERSION = (3, 6)
MIN_CORE_VERSION = "0.20.0"
STARTUP_SCRIPT_NAME = "dcc_mcp_blender_startup.py"
DEFAULT_RECEIPT_PATH = Path.home() / ".dcc-mcp" / "receipts" / "blender.json"
LIFECYCLE_COMMANDS = ("install", "status", "verify", "uninstall", "upgrade")


class LifecycleError(RuntimeError):
    """A stable, classified Install SOP failure."""

    def __init__(self, exit_code, stage, reason, message):
        # type: (int, str, str, str) -> None
        super().__init__(message)
        self.exit_code = exit_code
        self.stage = stage
        self.reason = reason


@dataclass(frozen=True)
class InstallContext:
    host_path: Path
    host_version: str
    profile: Path
    python_path: Path
    python_selection_source: str
    python_version: str
    site_packages: Path
    core_version: str
    state: str
    state_stage: str
    state_reason: str
    receipt_path: Path
    startup_path: Path
    bootstrap_log_dir: Path


def _version_tuple(value):
    # type: (str) -> Tuple[int, ...]
    match = re.search(r"\d+(?:\.\d+)+", value)
    if match is None:
        return ()
    return tuple(int(part) for part in match.group(0).split("."))


def _resolve_host_path(explicit):
    # type: (Optional[str]) -> Path
    value = explicit or os.environ.get("DCC_MCP_BLENDER_DCC_PATH")
    if not value:
        raise LifecycleError(
            INSTALL_EXIT_PREFLIGHT,
            "host",
            "dcc_path_required",
            "Pass the exact Blender executable or application with --dcc-path.",
        )
    path = Path(value).expanduser().resolve()
    if not path.exists():
        raise LifecycleError(
            INSTALL_EXIT_PREFLIGHT,
            "host",
            "dcc_path_missing",
            "Blender path does not exist: %s" % path,
        )
    return path


def _resolve_host_version(host_path, environ):
    # type: (Path, Mapping[str, str]) -> str
    configured = environ.get("DCC_MCP_BLENDER_VERSION", "").strip()
    if configured:
        version = configured
    else:
        command_path = host_path
        if host_path.is_dir() and host_path.suffix.lower() == ".app":
            command_path = host_path / "Contents" / "MacOS" / "Blender"
        try:
            completed = subprocess.run(
                [str(command_path), "--version"],
                check=False,
                capture_output=True,
                universal_newlines=True,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise LifecycleError(
                INSTALL_EXIT_PREFLIGHT,
                "host",
                "host_version_probe_failed",
                "Could not query the Blender version: %s" % exc,
            ) from exc
        output = (completed.stdout or completed.stderr).strip()
        version_match = re.search(r"Blender\s+(\d+(?:\.\d+){1,2})", output)
        if completed.returncode != 0 or version_match is None:
            raise LifecycleError(
                INSTALL_EXIT_PREFLIGHT,
                "host",
                "host_version_unavailable",
                "Blender did not return a supported version from --version.",
            )
        version = version_match.group(1)
    if _version_tuple(version) < MIN_BLENDER_VERSION:
        raise LifecycleError(
            INSTALL_EXIT_PREFLIGHT,
            "host",
            "unsupported_blender_version",
            "Blender %s is unsupported; Blender 3.6 or newer is required." % version,
        )
    return version


def _probe_python(python_path):
    # type: (Path) -> Dict[str, str]
    if not python_path.is_file():
        raise LifecycleError(
            INSTALL_EXIT_PREFLIGHT,
            "python",
            "python_missing",
            "Target interpreter does not exist: %s" % python_path,
        )
    script = (
        "import json,sys,sysconfig; "
        "import dcc_mcp_core,dcc_mcp_blender; "
        "print(json.dumps({"
        "'python_version':'.'.join(map(str,sys.version_info[:3])),"
        "'site_packages':sysconfig.get_path('purelib'),"
        "'core_version':dcc_mcp_core.__version__,"
        "'adapter_version':dcc_mcp_blender.__version__}))"
    )
    try:
        completed = subprocess.run(
            [str(python_path), "-c", script],
            check=False,
            capture_output=True,
            universal_newlines=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LifecycleError(
            INSTALL_EXIT_PREFLIGHT,
            "python",
            "python_probe_failed",
            "Could not run the target interpreter: %s" % exc,
        ) from exc
    if completed.returncode != 0:
        diagnostic = (completed.stderr or completed.stdout).strip()[-2000:]
        raise LifecycleError(
            INSTALL_EXIT_PREFLIGHT,
            "python",
            "target_import_failed",
            "Target Python cannot import the adapter and Core: %s" % diagnostic,
        )
    try:
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError) as exc:
        raise LifecycleError(
            INSTALL_EXIT_PREFLIGHT,
            "python",
            "python_probe_invalid",
            "Target Python returned invalid version metadata.",
        ) from exc
    if payload.get("adapter_version") != __version__:
        raise LifecycleError(
            INSTALL_EXIT_PREFLIGHT,
            "python",
            "adapter_version_mismatch",
            "Target Python has adapter %r; expected %r." % (payload.get("adapter_version"), __version__),
        )
    if _version_tuple(str(payload.get("core_version", ""))) < _version_tuple(MIN_CORE_VERSION):
        raise LifecycleError(
            INSTALL_EXIT_PREFLIGHT,
            "core_version",
            "core_version_unsupported",
            "dcc-mcp-core>=%s is required in the target interpreter." % MIN_CORE_VERSION,
        )
    return {str(key): str(value) for key, value in payload.items()}


def _default_user_scripts(version):
    # type: (str) -> Path
    major_minor = ".".join(str(part) for part in _version_tuple(version)[:2])
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if not appdata:
            raise LifecycleError(
                INSTALL_EXIT_PREFLIGHT,
                "profile",
                "profile_unavailable",
                "APPDATA is unavailable; set DCC_MCP_BLENDER_USER_SCRIPTS.",
            )
        return Path(appdata) / "Blender Foundation" / "Blender" / major_minor / "scripts"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Blender" / major_minor / "scripts"
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return config_home / "blender" / major_minor / "scripts"


def _resolve_context(dcc_path, python_path, environ):
    # type: (Optional[str], Optional[str], Mapping[str, str]) -> InstallContext
    host_path = _resolve_host_path(dcc_path)
    host_version = _resolve_host_version(host_path, environ)
    if python_path:
        selected_python = python_path
        python_selection_source = "--python"
    else:
        selected_python = environ.get("DCC_MCP_INSTALL_PYTHON", "").strip()
        if not selected_python:
            raise LifecycleError(
                INSTALL_EXIT_PREFLIGHT,
                "python",
                "python_required",
                "Pass Blender's exact target interpreter with --python or DCC_MCP_INSTALL_PYTHON.",
            )
        python_selection_source = "DCC_MCP_INSTALL_PYTHON"
    interpreter = Path(selected_python).expanduser().resolve()
    python = _probe_python(interpreter)
    profile = (
        Path(environ.get("DCC_MCP_BLENDER_USER_SCRIPTS") or _default_user_scripts(host_version)).expanduser().resolve()
    )
    receipt_path = Path(environ.get("DCC_MCP_BLENDER_RECEIPT", str(DEFAULT_RECEIPT_PATH))).expanduser().resolve()
    startup_path = profile / "startup" / STARTUP_SCRIPT_NAME
    state_stage = ""
    state_reason = ""
    if receipt_path.is_file():
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = "partial"
            state_stage = "receipt"
            state_reason = "receipt_invalid"
        else:
            receipt_python = receipt.get("python") if isinstance(receipt, dict) else None
            receipt_host = receipt.get("host") if isinstance(receipt, dict) else None
            valid_receipt = (
                isinstance(receipt, dict)
                and receipt.get("receipt_version") == 1
                and receipt.get("dcc_type") == DCC_TYPE
                and isinstance(receipt_python, dict)
                and isinstance(receipt_host, dict)
            )
            if not valid_receipt:
                state = "partial"
                state_stage = "receipt"
                state_reason = "receipt_invalid"
            else:
                recorded_python = str(receipt_python.get("path", ""))
                if not recorded_python:
                    state = "partial"
                    state_stage = "receipt"
                    state_reason = "receipt_invalid"
                elif Path(recorded_python).expanduser().resolve() != interpreter:
                    raise LifecycleError(
                        INSTALL_EXIT_PREFLIGHT,
                        "python",
                        "python_mismatch",
                        "Selected interpreter does not match the Blender install receipt.",
                    )
                else:
                    recorded_host = str(receipt_host.get("path", ""))
                    recorded_profile = str(receipt_host.get("profile", ""))
                    if (
                        not recorded_host
                        or not recorded_profile
                        or Path(recorded_host).expanduser().resolve() != host_path
                        or Path(recorded_profile).expanduser().resolve() != profile
                    ):
                        raise LifecycleError(
                            INSTALL_EXIT_PREFLIGHT,
                            "receipt",
                            "receipt_target_mismatch",
                            "The receipt belongs to a different Blender host or profile.",
                        )
                    files = receipt.get("files")
                    owned_file = files[0] if isinstance(files, list) and len(files) == 1 else None
                    if not isinstance(owned_file, dict):
                        state = "partial"
                        state_stage = "receipt"
                        state_reason = "receipt_invalid"
                    else:
                        recorded_path = str(owned_file.get("path", ""))
                        recorded_digest = owned_file.get("sha256")
                        try:
                            artifact_current = (
                                bool(recorded_path)
                                and Path(recorded_path).expanduser().resolve() == startup_path.resolve()
                                and startup_path.is_file()
                                and bool(recorded_digest)
                                and _sha256(startup_path) == recorded_digest
                            )
                        except OSError:
                            artifact_current = False
                        if not artifact_current:
                            state = "partial"
                            state_stage = "artifact"
                            state_reason = (
                                "startup_script_missing"
                                if not startup_path.is_file()
                                else "startup_script_digest_mismatch"
                            )
                        else:
                            state = "current" if receipt.get("adapter_version") == __version__ else "upgrade"
    elif startup_path.exists():
        state = "partial"
        state_stage = "receipt"
        state_reason = "unreceipted_startup_script"
    else:
        state = "fresh"
    return InstallContext(
        host_path=host_path,
        host_version=host_version,
        profile=profile,
        python_path=interpreter,
        python_selection_source=python_selection_source,
        python_version=python["python_version"],
        site_packages=Path(python["site_packages"]).resolve(),
        core_version=python["core_version"],
        state=state,
        state_stage=state_stage,
        state_reason=state_reason,
        receipt_path=receipt_path,
        startup_path=startup_path,
        bootstrap_log_dir=profile / ".dcc-mcp" / "logs",
    )


def _base_report(ctx, command, status):
    # type: (InstallContext, str, str) -> Dict[str, Any]
    return {
        "schema_version": INSTALL_SOP_SCHEMA_VERSION,
        "status": status,
        "dcc_type": DCC_TYPE,
        "command": command,
        "adapter_version": __version__,
        "core_version": ctx.core_version,
        "steps": [],
        "next_steps": [],
        "receipt_path": str(ctx.receipt_path),
        "verify": {
            "directly_usable": False,
            "failure_stage": None,
            "failure_reason": None,
        },
        "host": {
            "path": str(ctx.host_path),
            "version": ctx.host_version,
            "profile": str(ctx.profile),
        },
        "python": {
            "path": str(ctx.python_path),
            "version": ctx.python_version,
            "site_packages": str(ctx.site_packages),
            "selection_source": ctx.python_selection_source,
        },
        "install_state": ctx.state,
    }


def _command_for(ctx, command, execute=False):
    # type: (InstallContext, str, bool) -> Sequence[str]
    result = [
        COMMAND,
        command,
        "--dcc-path",
        str(ctx.host_path),
        "--python",
        str(ctx.python_path),
        "--json",
    ]
    if execute:
        result.append("--yes")
    return result


def _plan(ctx, command):
    # type: (InstallContext, str) -> Dict[str, Any]
    report = _base_report(ctx, command, "planned")
    if command == "upgrade":
        plan_type = "upgrade"
    elif ctx.state == "partial":
        plan_type = "repair"
    else:
        plan_type = ctx.state
    report["plan_type"] = plan_type
    if command == "uninstall":
        report["steps"] = [
            {"id": "preflight", "status": "ok"},
            {"id": "receipt", "status": "planned"},
            {"id": "uninstall", "status": "planned"},
        ]
    else:
        report["steps"] = [
            {"id": "preflight", "status": "ok"},
            {"id": "stage", "status": "planned"},
            {"id": "commit", "status": "planned"},
            {"id": "verify", "status": "planned"},
        ]
    report["next_steps"] = [
        {
            "id": "execute_%s" % command,
            "description": "Execute the validated Blender %s plan." % command,
            "command": list(_command_for(ctx, command, execute=True)),
            "why": "Planning and dry-run modes do not modify Blender's user scripts.",
        }
    ]
    return report


def _sha256(path):
    # type: (Path) -> str
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_receipt(path, required=False):
    # type: (Path, bool) -> Optional[Dict[str, Any]]
    if not path.is_file():
        if required:
            raise LifecycleError(
                INSTALL_EXIT_PREFLIGHT,
                "receipt",
                "receipt_missing",
                "No Blender install receipt exists at %s." % path,
            )
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LifecycleError(
            INSTALL_EXIT_PREFLIGHT,
            "receipt",
            "receipt_invalid",
            "The Blender install receipt is unreadable: %s" % exc,
        ) from exc
    if not isinstance(value, dict) or value.get("receipt_version") != 1:
        raise LifecycleError(
            INSTALL_EXIT_PREFLIGHT,
            "receipt",
            "receipt_invalid",
            "The Blender install receipt has an unsupported schema.",
        )
    if value.get("dcc_type") != DCC_TYPE:
        raise LifecycleError(
            INSTALL_EXIT_PREFLIGHT,
            "receipt",
            "receipt_wrong_adapter",
            "The receipt does not belong to the Blender adapter.",
        )
    return value


def _render_startup_script(ctx):
    # type: (InstallContext) -> str
    site_packages = json.dumps(str(ctx.site_packages))
    log_dir = json.dumps(str(ctx.bootstrap_log_dir))
    adapter_version = json.dumps(__version__)
    min_core_version = json.dumps(MIN_CORE_VERSION)
    return '''"""Auto-start dcc-mcp-blender from Blender's startup registry."""

from __future__ import annotations

import site

site.addsitedir(%s)

_server = None
_owns_server = False


def register():
    """Start the MCP server once Blender has loaded this startup script."""
    global _owns_server, _server
    if _server is not None and getattr(_server, "is_running", True):
        return _server

    from dcc_mcp_core import capture_bootstrap_errors

    with capture_bootstrap_errors(
        "blender",
        adapter_version=%s,
        min_core_version=%s,
        phase="startup",
        log_dir=%s,
    ):
        from dcc_mcp_blender import get_server, start_server

        existing = get_server()
        if existing is not None and getattr(existing, "is_running", False):
            _server = existing
            _owns_server = False
            return _server

        _server = start_server()
        _owns_server = True
        return _server


def unregister():
    """Stop only the server owned by this startup script."""
    global _owns_server, _server
    if _server is None:
        return
    try:
        if not _owns_server:
            return
        from dcc_mcp_blender import get_server, stop_server
        if get_server() is _server:
            stop_server()
    finally:
        _server = None
        _owns_server = False
''' % (site_packages, adapter_version, min_core_version, log_dir)


def _write_text(path, content):
    # type: (Path, str) -> None
    path.write_text(content, encoding="utf-8")


def _replace_path(source, destination):
    # type: (Path, Path) -> None
    os.replace(str(source), str(destination))


def _unlink_file(path):
    # type: (Path) -> None
    path.unlink()


def _is_windows_lock(exc):
    # type: (OSError) -> bool
    return os.name == "nt" and (isinstance(exc, PermissionError) or getattr(exc, "winerror", None) in {5, 32, 33})


def _receipt_payload(ctx, startup_path, installed_at, previous_version):
    # type: (InstallContext, Path, float, Optional[str]) -> Dict[str, Any]
    return {
        "receipt_version": 1,
        "schema_version": INSTALL_SOP_SCHEMA_VERSION,
        "dcc_type": DCC_TYPE,
        "adapter_version": __version__,
        "core_version": ctx.core_version,
        "host": {
            "path": str(ctx.host_path),
            "version": ctx.host_version,
            "profile": str(ctx.profile),
        },
        "python": {
            "path": str(ctx.python_path),
            "version": ctx.python_version,
            "site_packages": str(ctx.site_packages),
        },
        "files": [{"path": str(startup_path.resolve()), "sha256": _sha256(startup_path)}],
        "bootstrap_error_dir": str(ctx.bootstrap_log_dir),
        "installed_at": datetime.fromtimestamp(installed_at, timezone.utc).isoformat(),
        "installed_at_epoch": installed_at,
        "previous_adapter_version": previous_version,
    }


def _rollback_file(current, backup, existed_before):
    # type: (Path, Path, bool) -> None
    if current.exists():
        _unlink_file(current)
    if existed_before and backup.exists():
        _replace_path(backup, current)


def _install_transaction(ctx):
    # type: (InstallContext) -> None
    previous = _read_receipt(ctx.receipt_path)
    previous_version = str(previous.get("adapter_version")) if previous else None
    token = uuid.uuid4().hex
    ctx.startup_path.parent.mkdir(parents=True, exist_ok=True)
    ctx.receipt_path.parent.mkdir(parents=True, exist_ok=True)
    startup_stage = ctx.startup_path.with_name(".%s.stage-%s" % (ctx.startup_path.name, token))
    startup_backup = ctx.startup_path.with_name(".%s.backup-%s" % (ctx.startup_path.name, token))
    receipt_stage = ctx.receipt_path.with_name(".%s.stage-%s" % (ctx.receipt_path.name, token))
    receipt_backup = ctx.receipt_path.with_name(".%s.backup-%s" % (ctx.receipt_path.name, token))
    startup_existed = ctx.startup_path.exists()
    receipt_existed = ctx.receipt_path.exists()
    installed_at = time.time()
    startup_committed = False
    receipt_committed = False
    try:
        _write_text(startup_stage, _render_startup_script(ctx))
        receipt = _receipt_payload(ctx, startup_stage, installed_at, previous_version)
        receipt["files"][0]["path"] = str(ctx.startup_path.resolve())
        _write_text(receipt_stage, json.dumps(receipt, indent=2, sort_keys=True) + "\n")

        inspection = inspect_install_root(ctx.startup_path.parent)
        if inspection.get("requires_restart"):
            raise LifecycleError(
                INSTALL_EXIT_REQUIRES_RESTART,
                "install",
                "native_artifact_loaded",
                str(inspection.get("recommended_next_action") or "Blender must restart."),
            )

        if startup_existed:
            _replace_path(ctx.startup_path, startup_backup)
        _replace_path(startup_stage, ctx.startup_path)
        startup_committed = True
        if receipt_existed:
            _replace_path(ctx.receipt_path, receipt_backup)
        _replace_path(receipt_stage, ctx.receipt_path)
        receipt_committed = True
    except BaseException:
        try:
            if startup_committed or startup_backup.exists():
                _rollback_file(ctx.startup_path, startup_backup, startup_existed)
            if receipt_committed or receipt_backup.exists():
                _rollback_file(ctx.receipt_path, receipt_backup, receipt_existed)
        finally:
            for temporary in (startup_stage, receipt_stage):
                if temporary.exists():
                    _unlink_file(temporary)
        raise
    else:
        for backup in (startup_backup, receipt_backup):
            if backup.exists():
                _unlink_file(backup)


def _readiness_next_steps(ctx):
    # type: (InstallContext) -> Sequence[Dict[str, Any]]
    return [
        {
            "id": "launch_blender",
            "description": "Launch the selected Blender installation.",
            "command": [str(ctx.host_path)],
            "why": "The typed host.ping probe requires a running Blender instance.",
        },
        {
            "id": "verify_install",
            "description": "Verify the adapter after Blender finishes starting.",
            "command": list(_command_for(ctx, "verify")),
            "why": "Direct usability is not proven until the typed readiness probe succeeds.",
        },
    ]


def _verify(ctx, environ):
    # type: (InstallContext, Mapping[str, str]) -> Tuple[Dict[str, Any], Sequence[Dict[str, Any]]]
    try:
        receipt = _read_receipt(ctx.receipt_path, required=True)
    except LifecycleError as exc:
        return (
            {
                "directly_usable": False,
                "failure_stage": "receipt",
                "failure_reason": exc.reason,
            },
            (),
        )
    assert receipt is not None
    files = receipt.get("files")
    if not isinstance(files, list) or len(files) != 1 or not isinstance(files[0], dict):
        return (
            {
                "directly_usable": False,
                "failure_stage": "receipt",
                "failure_reason": "receipt_ownership_invalid",
            },
            (),
        )
    recorded_path = Path(str(files[0].get("path", ""))).expanduser().resolve()
    if recorded_path != ctx.startup_path.resolve():
        return (
            {
                "directly_usable": False,
                "failure_stage": "receipt",
                "failure_reason": "receipt_target_mismatch",
            },
            (),
        )
    if not recorded_path.is_file():
        return (
            {
                "directly_usable": False,
                "failure_stage": "artifact",
                "failure_reason": "startup_script_missing",
            },
            (),
        )
    if _sha256(recorded_path) != files[0].get("sha256"):
        return (
            {
                "directly_usable": False,
                "failure_stage": "artifact",
                "failure_reason": "startup_script_digest_mismatch",
            },
            (),
        )
    try:
        _probe_python(ctx.python_path)
    except LifecycleError as exc:
        return (
            {
                "directly_usable": False,
                "failure_stage": "import",
                "failure_reason": exc.reason,
            },
            (),
        )

    try:
        installed_at = float(receipt.get("installed_at_epoch", 0.0))
    except (TypeError, ValueError):
        return (
            {
                "directly_usable": False,
                "failure_stage": "receipt",
                "failure_reason": "receipt_invalid",
            },
            (),
        )
    recent_errors = []
    if ctx.bootstrap_log_dir.is_dir():
        recent_errors = [
            path
            for path in ctx.bootstrap_log_dir.glob("dcc-mcp-blender.*.host-errors.log")
            if path.stat().st_mtime >= installed_at
        ]
    if recent_errors:
        return (
            {
                "directly_usable": False,
                "failure_stage": "bootstrap",
                "failure_reason": "bootstrap_error_captured",
                "diagnostic_path": str(recent_errors[-1]),
            },
            (),
        )

    state = query_runtime_state(environ.get("DCC_MCP_REGISTRY_DIR"), dcc_type=DCC_TYPE, include_dead=False)
    entries = [entry for entry in state.get("entries", []) if entry.get("mcp_url")]
    if len(entries) != 1:
        reason = "no_live_blender_instance" if not entries else "multiple_live_blender_instances"
        return (
            {
                "directly_usable": False,
                "failure_stage": "readiness",
                "failure_reason": reason,
                "probe_tool": "host.ping",
            },
            _readiness_next_steps(ctx),
        )
    timeout = max(0.1, float(environ.get("DCC_MCP_INSTALL_VERIFY_TIMEOUT", "2.0")))
    probe = probe_sidecar_tool(str(entries[0]["mcp_url"]), "host.ping", timeout_secs=timeout)
    if not probe.get("success"):
        return (
            {
                "directly_usable": False,
                "failure_stage": "readiness",
                "failure_reason": str(probe.get("reason") or probe.get("status") or "host_ping_failed"),
                "probe_tool": "host.ping",
            },
            _readiness_next_steps(ctx),
        )
    return (
        {
            "directly_usable": True,
            "failure_stage": None,
            "failure_reason": None,
            "probe_tool": "host.ping",
        },
        (),
    )


def _execute_install(ctx, environ, command="install"):
    # type: (InstallContext, Mapping[str, str], str) -> Tuple[Dict[str, Any], int]
    if ctx.state == "partial" and ctx.startup_path.exists() and not ctx.receipt_path.exists():
        try:
            legacy = ctx.startup_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise LifecycleError(
                INSTALL_EXIT_PREFLIGHT,
                "partial",
                "unreceipted_startup_script",
                "The unreceipted Blender startup script cannot be inspected: %s" % exc,
            ) from exc
        if legacy != _render_startup_script(ctx):
            raise LifecycleError(
                INSTALL_EXIT_PREFLIGHT,
                "partial",
                "unreceipted_startup_script",
                "An unknown unreceipted startup script exists; refusing to overwrite it.",
            )
    try:
        _install_transaction(ctx)
    except LifecycleError:
        raise
    except OSError as exc:
        exit_code = INSTALL_EXIT_REQUIRES_RESTART if _is_windows_lock(exc) else INSTALL_EXIT_INSTALL
        reason = "windows_file_lock" if exit_code == INSTALL_EXIT_REQUIRES_RESTART else "commit_failed"
        raise LifecycleError(exit_code, "install", reason, "Install transaction failed: %s" % exc) from exc

    verify, next_steps = _verify(ctx, environ)
    usable = bool(verify["directly_usable"])
    report = _base_report(ctx, command, "ok" if usable else "partial")
    report["plan_type"] = "upgrade" if command == "upgrade" else ctx.state
    report["steps"] = [
        {"id": "preflight", "status": "ok"},
        {"id": "stage", "status": "ok"},
        {"id": "commit", "status": "ok"},
        {"id": "verify", "status": "ok" if usable else "failed"},
    ]
    report["next_steps"] = list(next_steps)
    report["verify"] = verify
    return report, INSTALL_EXIT_OK if usable else INSTALL_EXIT_VERIFY


def _status(ctx):
    # type: (InstallContext) -> Tuple[Dict[str, Any], int]
    report = _base_report(ctx, "status", "partial" if ctx.state == "partial" else "ok")
    report["steps"] = [
        {"id": "receipt", "status": "present" if ctx.receipt_path.is_file() else "absent"},
        {"id": "startup", "status": "present" if ctx.startup_path.is_file() else "absent"},
    ]
    if ctx.state == "partial":
        report["verify"] = {
            "directly_usable": False,
            "failure_stage": ctx.state_stage or "state",
            "failure_reason": ctx.state_reason or "partial_install",
        }
    exit_code = INSTALL_EXIT_PREFLIGHT if ctx.state == "partial" else INSTALL_EXIT_OK
    return report, exit_code


def _execute_uninstall(ctx):
    # type: (InstallContext) -> Tuple[Dict[str, Any], int]
    receipt = _read_receipt(ctx.receipt_path)
    if receipt is None:
        if ctx.startup_path.exists():
            raise LifecycleError(
                INSTALL_EXIT_PREFLIGHT,
                "partial",
                "unreceipted_startup_script",
                "The Blender startup script has no receipt; refusing ambiguous removal.",
            )
        report = _base_report(ctx, "uninstall", "ok")
        report["steps"] = [{"id": "uninstall", "status": "already_absent"}]
        return report, INSTALL_EXIT_OK

    files = receipt.get("files")
    expected = ctx.startup_path.resolve()
    if not isinstance(files, list) or len(files) != 1 or not isinstance(files[0], dict):
        raise LifecycleError(
            INSTALL_EXIT_INSTALL,
            "receipt",
            "receipt_ownership_invalid",
            "Receipt ownership is incomplete; refusing removal.",
        )
    recorded = Path(str(files[0].get("path", ""))).expanduser().resolve()
    if recorded != expected:
        raise LifecycleError(
            INSTALL_EXIT_INSTALL,
            "receipt",
            "receipt_target_mismatch",
            "Receipt target does not match the selected Blender profile.",
        )
    if recorded.exists() and _sha256(recorded) != files[0].get("sha256"):
        raise LifecycleError(
            INSTALL_EXIT_INSTALL,
            "receipt",
            "startup_script_modified",
            "The receipted startup script was modified; preserving it.",
        )

    inspection = inspect_install_root(ctx.startup_path.parent)
    if inspection.get("requires_restart"):
        raise LifecycleError(
            INSTALL_EXIT_REQUIRES_RESTART,
            "uninstall",
            "native_artifact_loaded",
            str(inspection.get("recommended_next_action") or "Blender must restart."),
        )

    token = uuid.uuid4().hex
    startup_tombstone = ctx.startup_path.with_name(".%s.uninstall-%s" % (ctx.startup_path.name, token))
    receipt_tombstone = ctx.receipt_path.with_name(".%s.uninstall-%s" % (ctx.receipt_path.name, token))
    receipt_bytes = ctx.receipt_path.read_bytes()
    try:
        if ctx.startup_path.exists():
            _replace_path(ctx.startup_path, startup_tombstone)
        _replace_path(ctx.receipt_path, receipt_tombstone)
        _unlink_file(receipt_tombstone)
        if startup_tombstone.exists():
            _unlink_file(startup_tombstone)
    except OSError as exc:
        if startup_tombstone.exists() and not ctx.startup_path.exists():
            _replace_path(startup_tombstone, ctx.startup_path)
        if receipt_tombstone.exists() and not ctx.receipt_path.exists():
            _replace_path(receipt_tombstone, ctx.receipt_path)
        elif not ctx.receipt_path.exists():
            _write_text(ctx.receipt_path, receipt_bytes.decode("utf-8"))
        exit_code = INSTALL_EXIT_REQUIRES_RESTART if _is_windows_lock(exc) else INSTALL_EXIT_INSTALL
        reason = "windows_file_lock" if exit_code == INSTALL_EXIT_REQUIRES_RESTART else "uninstall_failed"
        raise LifecycleError(exit_code, "uninstall", reason, "Uninstall transaction failed: %s" % exc) from exc

    report = _base_report(ctx, "uninstall", "ok")
    report["install_state"] = "fresh"
    report["steps"] = [
        {"id": "receipt", "status": "consumed"},
        {"id": "uninstall", "status": "ok"},
    ]
    return report, INSTALL_EXIT_OK


def _failure_report(command, dcc_path, python_path, environ, exc):
    # type: (str, Optional[str], Optional[str], Mapping[str, str], LifecycleError) -> Dict[str, Any]
    receipt_path = Path(environ.get("DCC_MCP_BLENDER_RECEIPT", str(DEFAULT_RECEIPT_PATH))).expanduser().resolve()
    return {
        "schema_version": INSTALL_SOP_SCHEMA_VERSION,
        "status": "requires_restart" if exc.exit_code == INSTALL_EXIT_REQUIRES_RESTART else "failed",
        "dcc_type": DCC_TYPE,
        "command": command,
        "adapter_version": __version__,
        "core_version": str(getattr(dcc_mcp_core, "__version__", "unknown")),
        "steps": [{"id": exc.stage, "status": "failed", "message": str(exc)}],
        "next_steps": [
            {
                "id": "retry_preflight",
                "description": "Repeat preflight with the exact Blender host and interpreter.",
                "command": [
                    COMMAND,
                    command,
                    "--dcc-path",
                    dcc_path or "<absolute-blender-path>",
                    "--python",
                    python_path or environ.get("DCC_MCP_INSTALL_PYTHON") or "<absolute-blender-python>",
                    "--json",
                    "--dry-run",
                ],
                "why": str(exc),
            }
        ],
        "receipt_path": str(receipt_path),
        "verify": {
            "directly_usable": False,
            "failure_stage": exc.stage,
            "failure_reason": exc.reason,
        },
        "failure_message": str(exc),
    }


def _parser():
    # type: () -> argparse.ArgumentParser
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=LIFECYCLE_COMMANDS)
    parser.add_argument("--json", action="store_true", help="Emit one SOP v1 JSON document.")
    parser.add_argument("--yes", action="store_true", help="Execute a mutating plan.")
    parser.add_argument("--dry-run", action="store_true", help="Resolve without writing files.")
    parser.add_argument("--dcc-path", help="Exact Blender executable or .app path.")
    parser.add_argument("--python", help="Exact Blender target interpreter.")
    return parser


def main(argv=None):
    # type: (Optional[Sequence[str]]) -> int
    args = _parser().parse_args(argv)
    environ = os.environ
    try:
        ctx = _resolve_context(args.dcc_path, args.python, environ)
        if args.command == "install":
            if args.dry_run or not args.yes:
                report = _plan(ctx, args.command)
                exit_code = INSTALL_EXIT_OK
            else:
                report, exit_code = _execute_install(ctx, environ)
        elif args.command == "upgrade":
            if not ctx.receipt_path.is_file():
                raise LifecycleError(
                    INSTALL_EXIT_PREFLIGHT,
                    "receipt",
                    "receipt_missing",
                    "Upgrade requires an existing Blender install receipt.",
                )
            if args.dry_run or not args.yes:
                report = _plan(ctx, args.command)
                exit_code = INSTALL_EXIT_OK
            else:
                report, exit_code = _execute_install(ctx, environ, command="upgrade")
        elif args.command == "status":
            report, exit_code = _status(ctx)
        elif args.command == "verify":
            verify, next_steps = _verify(ctx, environ)
            usable = bool(verify["directly_usable"])
            report = _base_report(ctx, args.command, "ok" if usable else "failed")
            report["steps"] = [{"id": "verify", "status": "ok" if usable else "failed"}]
            report["next_steps"] = list(next_steps)
            report["verify"] = verify
            exit_code = INSTALL_EXIT_OK if usable else INSTALL_EXIT_VERIFY
        elif args.command == "uninstall":
            if args.dry_run or not args.yes:
                report = _plan(ctx, args.command)
                exit_code = INSTALL_EXIT_OK
            else:
                report, exit_code = _execute_uninstall(ctx)
        else:
            raise LifecycleError(
                INSTALL_EXIT_PREFLIGHT,
                "command",
                "command_not_implemented",
                "The %s lifecycle path is not implemented yet." % args.command,
            )
    except LifecycleError as exc:
        report = _failure_report(args.command, args.dcc_path, args.python, environ, exc)
        exit_code = exc.exit_code
    except BaseException as exc:
        failure = LifecycleError(
            INSTALL_EXIT_INSTALL,
            "install",
            "lifecycle_failed",
            "Lifecycle operation failed: %s" % exc,
        )
        report = _failure_report(args.command, args.dcc_path, args.python, environ, failure)
        exit_code = failure.exit_code
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("%s: %s" % (args.command, report["status"]))
        if report.get("failure_message"):
            print(report["failure_message"])
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "COMMAND",
    "DCC_TYPE",
    "INSTALL_EXIT_ACQUIRE",
    "INSTALL_EXIT_CODES",
    "INSTALL_EXIT_INSTALL",
    "INSTALL_EXIT_OK",
    "INSTALL_EXIT_PREFLIGHT",
    "INSTALL_EXIT_REQUIRES_RESTART",
    "INSTALL_EXIT_VERIFY",
    "INSTALL_SOP_SCHEMA_VERSION",
    "LIFECYCLE_COMMANDS",
    "load_install_sop_schema",
    "main",
]
