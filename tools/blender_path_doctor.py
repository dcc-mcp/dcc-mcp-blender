"""Report whether the adapter is really usable inside the running Blender Python.

Blender 5.x starts its embedded interpreter with an isolated configuration that
ignores ``PYTHONPATH``. A resolve can therefore report success while the host
sees zero adapter capability — a silent failure. This probe turns that into a
loud one.

Usage inside a host::

    blender --background --python tools/blender_path_doctor.py -- --json
    blender --background --python tools/blender_path_doctor.py -- --deep

Arguments after ``--`` are forwarded to the script; unknown Blender arguments
are ignored so the probe can also be appended to an existing command line.

Exit codes: ``0`` when the adapter and core import successfully, ``1`` when the
host cannot see them (the resolve produced an unusable host).
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import pkgutil
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Optional

_HELPER_MODULE_NAME = "_dcc_mcp_blender_path_doctor_helper"
_HELPER_RELATIVE = Path("dcc_mcp_blender") / "_isolated_path.py"
_PACKAGES = ("dcc_mcp_blender", "dcc_mcp_core", "dcc_mcp_server")


def _pythonpath_entries() -> List[str]:
    raw = os.environ.get("PYTHONPATH", "")
    return [entry.strip() for entry in raw.split(os.pathsep) if entry.strip()]


def _load_helper_by_path(path: Path) -> Optional[ModuleType]:
    spec = importlib.util.spec_from_file_location(_HELPER_MODULE_NAME, path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_HELPER_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


def locate_helper() -> Optional[ModuleType]:
    """Return the path-repair helper, loading it by file path when necessary.

    The helper is deliberately dependency-free so it can be loaded from a
    ``PYTHONPATH`` directory that the isolated interpreter refuses to put on
    ``sys.path`` — the bootstrap case this probe exists to diagnose.

    The ``PYTHONPATH`` scan runs *before* any package import on purpose:
    importing ``dcc_mcp_blender`` first would cache whichever copy the host
    happens to see (a stale user-level install, for example) and the repair
    could then no longer promote the resolved one.
    """
    for entry in _pythonpath_entries():
        candidate = Path(entry) / _HELPER_RELATIVE
        if candidate.is_file():
            module = _load_helper_by_path(candidate)
            if module is not None:
                return module

    try:
        return importlib.import_module("dcc_mcp_blender._isolated_path")
    except Exception:  # noqa: BLE001 - adapter not visible yet is the normal case here
        pass

    repo_candidate = Path(__file__).resolve().parent.parent / "src" / _HELPER_RELATIVE
    if repo_candidate.is_file():
        return _load_helper_by_path(repo_candidate)
    return None


def _import_report() -> Dict[str, Dict[str, Any]]:
    report: Dict[str, Dict[str, Any]] = {}
    for name in _PACKAGES:
        try:
            module = importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001
            report[name] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            continue
        report[name] = {
            "ok": True,
            "version": str(getattr(module, "__version__", "") or ""),
            "file": str(getattr(module, "__file__", "") or ""),
        }
    return report


def _tool_surface(deep: bool = False) -> Dict[str, Any]:
    """Measure what the host can actually reach from the adapter package."""
    try:
        module = importlib.import_module("dcc_mcp_blender")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    package_dir = Path(str(getattr(module, "__file__", ""))).parent
    submodules = [name for _, name, _ in pkgutil.walk_packages([str(package_dir)], prefix="dcc_mcp_blender.")]
    skills_dir = package_dir / "skills"
    skill_dirs = (
        sorted(path.name for path in skills_dir.iterdir() if (path / "SKILL.md").is_file())
        if skills_dir.is_dir()
        else []
    )
    surface: Dict[str, Any] = {
        "ok": True,
        "package_dir": str(package_dir),
        "py_files": sum(1 for _ in package_dir.rglob("*.py")),
        "submodules": len(submodules),
        "skill_dirs": len(skill_dirs),
    }
    if not deep:
        return surface

    imported = 0
    callables = 0
    errors: List[str] = []
    for name in submodules:
        try:
            submodule = importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
            continue
        imported += 1
        callables += sum(
            1
            for attribute in vars(submodule).values()
            if callable(attribute) and getattr(attribute, "__module__", None) == name
        )
    surface["deep"] = {
        "imported_submodules": imported,
        "import_errors": len(errors),
        "error_samples": errors[:10],
        "callables": callables,
    }
    return surface


def probe(repair: bool = True, deep: bool = False) -> Dict[str, Any]:
    """Collect host evidence: flags, path visibility, imports and tool surface."""
    helper = locate_helper()
    report: Dict[str, Any] = {"helper_loaded": helper is not None}

    if helper is None:
        report["errors"] = ["could not locate dcc_mcp_blender/_isolated_path.py on PYTHONPATH"]
        report["environment"] = {
            "python_version": sys.version.split()[0],
            "isolated": bool(getattr(sys.flags, "isolated", 0) or getattr(sys.flags, "ignore_environment", 0)),
        }
    else:
        report["environment"] = helper.path_state()
        if repair:
            report["restored_entries"] = helper.repair_sys_path()

    report["imports"] = _import_report()
    report["tool_surface"] = _tool_surface(deep=deep)
    report["ok"] = bool(report["imports"]["dcc_mcp_blender"]["ok"] and report["imports"]["dcc_mcp_core"]["ok"])
    return report


def _print_human(report: Dict[str, Any]) -> None:
    environment = report.get("environment", {})
    print("dcc-mcp-blender host path doctor")
    print(f"  python          : {environment.get('python_version', 'unknown')}")
    print(f"  isolated        : {environment.get('isolated', 'unknown')} {environment.get('flags', '')}")
    if "pythonpath_entries" in environment:
        print(
            f"  PYTHONPATH      : {environment.get('pythonpath_visible')}/{environment.get('pythonpath_entries')} "
            "entries visible in sys.path"
        )
    restored = report.get("restored_entries") or []
    if restored:
        print(f"  restored        : {len(restored)} entries")
    for name, state in report.get("imports", {}).items():
        if state.get("ok"):
            version = state.get("version") or "?"
            print(f"  import {name:<16}: ok ({version}) {state.get('file', '')}")
        else:
            print(f"  import {name:<16}: FAILED {state.get('error', '')}")
    surface = report.get("tool_surface", {})
    if surface.get("ok"):
        print(
            f"  tool surface    : {surface.get('submodules')} submodules / {surface.get('py_files')} py files / "
            f"{surface.get('skill_dirs')} skill dirs"
        )
        deep = surface.get("deep")
        if deep:
            print(
                f"  deep sweep      : {deep.get('imported_submodules')} imported / {deep.get('import_errors')} errors / "
                f"{deep.get('callables')} callables"
            )
    print("RESULT: " + ("adapter visible" if report.get("ok") else "ADAPTER NOT VISIBLE"))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Verify dcc-mcp-blender visibility inside a Blender host.")
    parser.add_argument("--json", action="store_true", help="Emit the full report as JSON.")
    parser.add_argument("--no-repair", action="store_true", help="Report only; do not restore PYTHONPATH entries.")
    parser.add_argument("--deep", action="store_true", help="Import every adapter submodule and count callables.")
    args, _unknown = parser.parse_known_args(argv)

    report = probe(repair=not args.no_repair, deep=args.deep)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_human(report)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
