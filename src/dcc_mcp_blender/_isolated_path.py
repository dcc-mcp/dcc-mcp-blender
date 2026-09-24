"""Restore ``PYTHONPATH`` visibility inside hosts that boot an isolated Python.

Blender 5.x initialises its embedded interpreter with an isolated CPython
configuration (``sys.flags.isolated == 1``, ``ignore_environment == 1``), so
``PYTHONPATH`` is never read: packages a package manager injected through the
environment are invisible from inside the host. The failure is silent — the
resolve reports success, Blender starts normally, and the adapter capability
inside the host is zero.

The process *environment* itself stays readable through :data:`os.environ`, so
a script that already runs can repair :data:`sys.path` without any help from
the launcher. That is what this module does.

It is deliberately dependency-free and loadable by file path, because the entry
points that need it (headless bootstrap, host doctor, studio launch scripts) run
*before* :mod:`dcc_mcp_blender` is importable.
"""

from __future__ import annotations

import os
import sys
from typing import Dict, List, Optional, Sequence

#: Set to ``0`` / ``false`` / ``no`` / ``off`` to disable the repair entirely.
ENV_REPAIR = "DCC_MCP_BLENDER_PYTHONPATH_REPAIR"
#: Extra site directories (``os.pathsep``-delimited) that should also be made
#: visible. Python never reads these itself, so they are applied on every host,
#: isolated or not.
ENV_EXTRA_PATHS = "DCC_MCP_BLENDER_EXTRA_SITE_DIRS"

#: ``sys.flags`` members that describe an interpreter which ignored the
#: environment at start-up. ``no_user_site`` / ``no_site`` are deliberately
#: excluded: they do not affect ``PYTHONPATH`` handling.
ISOLATED_FLAGS = ("isolated", "ignore_environment")

_FALSEY = ("0", "false", "no", "off")
_SITE_DIR_NAMES = ("site-packages", "dist-packages")


def is_isolated_python(flags: Optional[object] = None) -> bool:
    """Return ``True`` when the interpreter ignored ``PYTHONPATH`` at start-up."""
    source = sys.flags if flags is None else flags
    return any(bool(getattr(source, name, 0)) for name in ISOLATED_FLAGS)


def _env_flag(name: str, default: bool, environ: Optional[Dict[str, str]] = None) -> bool:
    raw = (os.environ if environ is None else environ).get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in _FALSEY


def repair_enabled(environ: Optional[Dict[str, str]] = None) -> bool:
    """Return ``True`` unless the repair was explicitly switched off."""
    return _env_flag(ENV_REPAIR, True, environ)


def _split(raw: str) -> List[str]:
    return [entry.strip() for entry in raw.split(os.pathsep) if entry.strip()]


def pythonpath_entries(environ: Optional[Dict[str, str]] = None) -> List[str]:
    """Return the de-duplicated ``PYTHONPATH`` entries of the process."""
    raw = (os.environ if environ is None else environ).get("PYTHONPATH", "")
    entries: List[str] = []
    seen = set()
    for entry in _split(raw):
        if entry not in seen:
            seen.add(entry)
            entries.append(entry)
    return entries


def extra_site_dirs(environ: Optional[Dict[str, str]] = None) -> List[str]:
    """Return the operator-supplied extra directories from :data:`ENV_EXTRA_PATHS`."""
    raw = (os.environ if environ is None else environ).get(ENV_EXTRA_PATHS, "")
    entries: List[str] = []
    seen = set()
    for entry in _split(raw):
        if entry not in seen:
            seen.add(entry)
            entries.append(entry)
    return entries


def _normalize(path: str) -> str:
    return os.path.normcase(os.path.abspath(os.path.expanduser(path)))


def missing_path_entries(
    candidates: Optional[Sequence[str]] = None,
    sys_path: Optional[List[str]] = None,
    environ: Optional[Dict[str, str]] = None,
) -> List[str]:
    """Return candidate directories that exist on disk but are absent from ``sys.path``."""
    if candidates is None:
        candidates = pythonpath_entries(environ) + extra_site_dirs(environ)
    current = list(sys.path if sys_path is None else sys_path)
    seen = {_normalize(entry) for entry in current}
    missing: List[str] = []
    for candidate in candidates:
        expanded = os.path.expanduser(candidate)
        if not os.path.isdir(expanded):
            continue
        key = _normalize(expanded)
        if key in seen:
            continue
        seen.add(key)
        missing.append(os.path.abspath(expanded))
    return missing


def _insertion_index(sys_path: Sequence[str]) -> int:
    """Return the index where ``PYTHONPATH`` entries belong.

    ``PYTHONPATH`` precedes ``site-packages`` in a normal interpreter, so the
    repair inserts there instead of appending: otherwise a stale user-level
    install of ``dcc-mcp-core`` would shadow the version the resolve supplied.
    """
    for index, entry in enumerate(sys_path):
        parts = [part for part in str(entry).replace("\\", "/").lower().split("/") if part]
        if any(part in _SITE_DIR_NAMES for part in parts):
            return index
    return len(sys_path)


def repair_sys_path(
    *,
    force: bool = False,
    environ: Optional[Dict[str, str]] = None,
    sys_path: Optional[List[str]] = None,
) -> List[str]:
    """Make the resolved dependencies visible again; return the entries added.

    The call is idempotent and a no-op on hosts that already honoured
    ``PYTHONPATH`` (unless ``force`` is set). Pass ``sys_path`` to repair a
    stand-in list instead of :data:`sys.path`.
    """
    env = os.environ if environ is None else environ
    if not repair_enabled(env):
        return []

    candidates = list(extra_site_dirs(env))
    if force or is_isolated_python():
        candidates = pythonpath_entries(env) + candidates

    added = missing_path_entries(candidates, sys_path=sys_path)
    if not added:
        return []

    target = sys.path if sys_path is None else sys_path
    index = _insertion_index(target)
    target[index:index] = added
    return added


def path_state(
    environ: Optional[Dict[str, str]] = None,
    sys_path: Optional[Sequence[str]] = None,
) -> Dict[str, object]:
    """Describe how much of ``PYTHONPATH`` the running interpreter can see."""
    env = os.environ if environ is None else environ
    entries = pythonpath_entries(env)
    current = list(sys.path if sys_path is None else sys_path)
    visible = {_normalize(entry) for entry in current}
    return {
        "python_version": sys.version.split()[0],
        "isolated": is_isolated_python(),
        "flags": {name: int(bool(getattr(sys.flags, name, 0))) for name in ISOLATED_FLAGS},
        "pythonpath_entries": len(entries),
        "pythonpath_visible": sum(1 for entry in entries if _normalize(entry) in visible),
        "extra_site_dirs": len(extra_site_dirs(env)),
        "repair_enabled": repair_enabled(env),
    }


__all__ = [
    "ENV_EXTRA_PATHS",
    "ENV_REPAIR",
    "ISOLATED_FLAGS",
    "extra_site_dirs",
    "is_isolated_python",
    "missing_path_entries",
    "path_state",
    "pythonpath_entries",
    "repair_enabled",
    "repair_sys_path",
]
