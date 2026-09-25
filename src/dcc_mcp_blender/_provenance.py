"""Locate the dcc-mcp runtime the host actually imported.

A host can resolve ``dcc_mcp_blender`` or ``dcc_mcp_core`` from a stale copy --
usually a user-level extension directory (``bl_ext.<repository>.dcc_mcp_blender``)
left behind by an earlier install -- while a package manager resolved a
different copy for the same session. The stale copy satisfies its own, older
compatibility gate, starts an MCP server, and answers every probe with an old
version number, so capability evidence captured from that host is silently
wrong: no import error, no version error, just a working server on the wrong
code.

This module compares where the runtime really came from against where the
session says it must come from:

* an operator or package manager declares the authoritative package root in
  :data:`ENV_EXPECTED_ROOT`;
* every monitored module must resolve inside that root, otherwise the host
  fails closed with :class:`PackageProvenanceError`;
* with no root declared the check is advisory. A user-level copy that shadows a
  copy importable from ``sys.path`` / ``PYTHONPATH`` is reported as a loud
  warning, because which one Blender picked depends on host start-up order.

Both paths feed a :class:`ProvenanceReport` so status output and skill results
can carry the origin of the runtime they were produced by.
"""

from __future__ import annotations

import importlib
import logging
import os
import sys
from dataclasses import dataclass, replace
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

#: Authoritative package root for this session. A package manager (rez, conda, a
#: studio launcher) exports it; every monitored module must resolve inside it.
ENV_EXPECTED_ROOT = "DCC_MCP_BLENDER_PACKAGE_ROOT"
#: Shared fallback for environments that resolve every dcc-mcp package together.
ENV_EXPECTED_ROOT_FALLBACK = "DCC_MCP_PACKAGE_ROOT"
#: Set to ``0`` / ``false`` / ``no`` / ``off`` to downgrade a provenance
#: violation from an exception to a warning.
ENV_STRICT = "DCC_MCP_BLENDER_STRICT_ORIGIN"

#: Packages whose origin decides which runtime the host is really running.
MONITORED_PACKAGES: Tuple[str, ...] = ("dcc_mcp_blender", "dcc_mcp_core")
#: Path segments that mark a user-level, per-Blender-version install location.
USER_LEVEL_MARKERS: Tuple[str, ...] = ("bl_ext", "user_default", "extensions", "addons")

_FALSEY = ("0", "false", "no", "off")
_ECHO_PREFIX = "[DCC MCP Blender]"


class PackageProvenanceError(RuntimeError):
    """The adapter or core resolved from outside the expected package root."""


@dataclass(frozen=True)
class ModuleProvenance:
    """Where one imported package came from."""

    name: str
    version: str
    origin: str
    root: str
    expected: Optional[bool] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "origin": self.origin,
            "root": self.root,
            "expected": self.expected,
        }


@dataclass(frozen=True)
class ProvenanceReport:
    """Origin of every monitored package, plus the conflicts found."""

    expected_root: Optional[str]
    strict: bool
    modules: Tuple[ModuleProvenance, ...] = ()
    shadowed: Tuple[ModuleProvenance, ...] = ()
    warnings: Tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        """``True`` when no monitored module resolved outside the expected roots."""
        return not self.shadowed

    @property
    def message(self) -> str:
        """Actionable description of a provenance violation."""
        lines = ["dcc-mcp-blender resolved outside the expected package root."]
        roots = expected_roots(self.expected_root)
        if roots:
            lines.append("Expected every monitored import below one of: " + os.pathsep.join(roots))
        for module in self.shadowed:
            lines.append(f"  {module.name} {module.version or 'unknown'} came from {module.origin or 'unknown'}")
        lines.append(
            f"Remove the stale copy, or export {ENV_EXPECTED_ROOT}=<the sys.path entry that holds the package> "
            f"before starting Blender."
        )
        lines.append(f"Set {ENV_STRICT}=0 to downgrade this error to a warning.")
        return "\n".join(lines)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "expected_root": self.expected_root,
            "strict": self.strict,
            "ok": self.ok,
            "modules": [module.as_dict() for module in self.modules],
            "shadowed": [module.name for module in self.shadowed],
            "warnings": list(self.warnings),
        }


def _normalize(path: str) -> str:
    return os.path.normcase(os.path.realpath(str(path)))


def is_within(path: str, root: Optional[str]) -> bool:
    """Return ``True`` when ``path`` sits inside ``root``."""
    if not path or not root:
        return False
    candidate = _normalize(path)
    container = _normalize(root)
    try:
        return os.path.commonpath([candidate, container]) == container
    except ValueError:
        # Different Windows drives: neither can contain the other.
        return False


def is_user_level(path: str) -> bool:
    """Return ``True`` for a per-user extension or add-on directory."""
    segments = [segment for segment in _normalize(path).replace("\\", "/").split("/") if segment]
    return any(segment in USER_LEVEL_MARKERS for segment in segments)


def _env_flag(name: str, default: bool, environ: Mapping[str, str]) -> bool:
    raw = environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in _FALSEY


def resolve_expected_root(environ: Optional[Mapping[str, str]] = None) -> Optional[str]:
    """Return the declared package root(s), or ``None`` when unset.

    The value may list several directories separated by :data:`os.pathsep`: a
    package manager that resolves every dcc-mcp package separately (rez, for
    example) gives each one its own root below a common prefix.
    """
    env = os.environ if environ is None else environ
    for name in (ENV_EXPECTED_ROOT, ENV_EXPECTED_ROOT_FALLBACK):
        raw = (env.get(name) or "").strip()
        if raw:
            return raw
    return None


def expected_roots(value: Optional[str]) -> Tuple[str, ...]:
    """Split a declared root value into individual directories."""
    if not value:
        return ()
    return tuple(entry.strip() for entry in str(value).split(os.pathsep) if entry.strip())


def is_within_any(path: str, roots: Sequence[str]) -> bool:
    """Return ``True`` when ``path`` sits inside one of ``roots``."""
    return any(is_within(path, root) for root in roots)


def matches_roots(provenance: ModuleProvenance, roots: Sequence[str]) -> bool:
    """Return ``True`` when a package resolved inside one of ``roots``.

    Both spellings of a root are accepted: the ``sys.path`` entry that holds the
    package (``.../site-packages``) and the package directory itself
    (``.../site-packages/dcc_mcp_blender``). A root only has to contain the
    package, not be its parent, so a declaration copied from either form is
    honoured instead of failing a healthy host.
    """
    candidates = [path for path in (provenance.origin, provenance.root) if path]
    return any(is_within_any(path, roots) for path in candidates)


def _module_root(module: Any) -> str:
    """Return the directory a module was imported from."""
    search_path = getattr(module, "__path__", None)
    if search_path:
        entries = [str(entry) for entry in search_path]
        if entries:
            return os.path.dirname(os.path.abspath(entries[0]))
    origin = getattr(module, "__file__", None)
    if origin:
        return os.path.dirname(os.path.abspath(str(origin)))
    return ""


def describe_module(name: str) -> Optional[ModuleProvenance]:
    """Return the origin of an importable package, or ``None`` when absent.

    The lookup goes through :func:`importlib.import_module`, so an extension
    import bridge that maps ``dcc_mcp_blender`` onto
    ``bl_ext.<repository>.dcc_mcp_blender`` reports the extension directory --
    exactly the location that has to be detected, because it is the one that
    silently wins over the resolved package.
    """
    try:
        module = importlib.import_module(name)
    except PackageProvenanceError:
        # Importing the package tripped its own provenance gate. That is the
        # verdict this module exists to produce, so it must not be reported as
        # "not importable" -- swallowing it would turn a hard failure into a
        # package that silently looks absent.
        raise
    except Exception as exc:  # noqa: BLE001 - a broken import is reported, not raised
        logger.debug("provenance: %s is not importable: %s", name, exc)
        return None
    return ModuleProvenance(
        name=name,
        version=str(getattr(module, "__version__", "") or ""),
        origin=str(getattr(module, "__file__", "") or ""),
        root=_module_root(module),
    )


def _search_path(
    environ: Optional[Mapping[str, str]] = None,
    sys_path: Optional[Sequence[str]] = None,
) -> List[str]:
    """Return every directory the interpreter and the environment import from."""
    env = os.environ if environ is None else environ
    entries: List[str] = []
    for entry in list(sys.path if sys_path is None else sys_path):
        if entry and entry not in entries:
            entries.append(str(entry))
    # An isolated Blender never puts PYTHONPATH on sys.path, yet those entries
    # still decide which copy a later repair exposes.
    for entry in str(env.get("PYTHONPATH", "") or "").split(os.pathsep):
        if entry.strip() and entry.strip() not in entries:
            entries.append(entry.strip())
    return entries


def sys_path_entry(copy_dir: str) -> str:
    """Return the ``sys.path`` entry a package copy is declared with.

    :func:`sys_path_copies` reports the package directory itself, but
    :data:`ENV_EXPECTED_ROOT` is compared against a directory that *contains*
    the package: declaring ``<entry>/dcc_mcp_blender`` as the root would put
    every import one level below it and fail a host that is already healthy.
    """
    parent = os.path.dirname(os.path.abspath(str(copy_dir)))
    return parent or str(copy_dir)


def sys_path_copies(
    name: str,
    sys_path: Optional[Sequence[str]] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> Tuple[str, ...]:
    """Return every directory that offers an importable copy of ``name``."""
    found: List[str] = []
    seen = set()
    for entry in _search_path(environ=environ, sys_path=sys_path):
        candidate = os.path.join(entry, name)
        init_file = os.path.join(candidate, "__init__.py")
        module_file = candidate + ".py"
        target = init_file if os.path.isfile(init_file) else (module_file if os.path.isfile(module_file) else "")
        if not target:
            continue
        key = _normalize(candidate)
        if key in seen:
            continue
        seen.add(key)
        found.append(candidate)
    return tuple(found)


def _advisory_warnings(
    modules: Sequence[ModuleProvenance],
    expected_root: Optional[str],
    sys_path: Optional[Sequence[str]],
    environ: Optional[Mapping[str, str]],
) -> Tuple[str, ...]:
    """Describe a user-level copy that shadows an importable distribution."""
    if expected_roots(expected_root):
        # A declared root already turns the same situation into a hard finding.
        return ()
    warnings: List[str] = []
    for module in modules:
        if not is_user_level(module.root):
            continue
        copies = [
            copy
            for copy in sys_path_copies(module.name, sys_path=sys_path, environ=environ)
            if not is_within(copy, module.root)
        ]
        if not copies:
            continue
        warnings.append(
            f"{module.name} {module.version or 'unknown'} was imported from the user-level copy at "
            f"{module.root}, which the host loads ahead of the distribution at {copies[0]}. "
            f"Evidence produced by this host describes the user-level copy. Remove it, or export "
            f"{ENV_EXPECTED_ROOT}={sys_path_entry(copies[0])} to fail closed on this conflict."
        )
    return tuple(warnings)


def collect_report(
    names: Sequence[str] = MONITORED_PACKAGES,
    expected_root: Optional[str] = None,
    strict: Optional[bool] = None,
    environ: Optional[Mapping[str, str]] = None,
    sys_path: Optional[Sequence[str]] = None,
) -> ProvenanceReport:
    """Inspect where every monitored package came from, without logging."""
    env = os.environ if environ is None else environ
    root = expected_root or resolve_expected_root(env)
    roots = expected_roots(root)
    modules: List[ModuleProvenance] = []
    for name in names:
        provenance = describe_module(name)
        if provenance is None:
            continue
        modules.append(replace(provenance, expected=matches_roots(provenance, roots) if roots else None))
    return ProvenanceReport(
        expected_root=root,
        strict=_env_flag(ENV_STRICT, True, env) if strict is None else bool(strict),
        modules=tuple(modules),
        shadowed=tuple(module for module in modules if module.expected is False),
        warnings=_advisory_warnings(modules, root, sys_path, env),
    )


def check_provenance(
    names: Sequence[str] = MONITORED_PACKAGES,
    expected_root: Optional[str] = None,
    strict: Optional[bool] = None,
    environ: Optional[Mapping[str, str]] = None,
    sys_path: Optional[Sequence[str]] = None,
    log: bool = True,
    echo: bool = False,
    raise_on_violation: Optional[bool] = None,
) -> ProvenanceReport:
    """Report the runtime origin; fail closed when a declared root is violated.

    The check raises :class:`PackageProvenanceError` only when the session
    declared an expected root and a monitored package resolved outside it. Set
    :data:`ENV_STRICT` to ``0`` (or pass ``strict=False``) to downgrade that to a
    warning. With no root declared nothing can be proven wrong, so conflicting
    copies are reported as warnings instead.
    """
    report = collect_report(
        names=names,
        expected_root=expected_root,
        strict=strict,
        environ=environ,
        sys_path=sys_path,
    )
    if log:
        for warning in report.warnings:
            logger.warning("%s", warning)
            if echo:
                print(f"{_ECHO_PREFIX} {warning}")
    if report.shadowed and report.expected_root:
        should_raise = report.strict if raise_on_violation is None else bool(raise_on_violation)
        if should_raise:
            if echo:
                print(f"{_ECHO_PREFIX} {report.message}")
            raise PackageProvenanceError(report.message)
    return report


def require_expected_origin(
    names: Sequence[str] = MONITORED_PACKAGES,
    expected_root: Optional[str] = None,
    environ: Optional[Mapping[str, str]] = None,
    sys_path: Optional[Sequence[str]] = None,
    echo: bool = False,
) -> ProvenanceReport:
    """Fail closed on a declared-root violation, ignoring the strict override.

    Used where a wrong runtime is worse than a broken one: the add-on entry runs
    this before it starts a server.
    """
    return check_provenance(
        names=names,
        expected_root=expected_root,
        strict=True,
        environ=environ,
        sys_path=sys_path,
        log=True,
        echo=echo,
        raise_on_violation=True,
    )


def version_tuple(version: str) -> Tuple[int, int, int]:
    """Parse a ``major.minor.patch`` prefix into a comparable tuple.

    Only the leading digits of each segment count, so a pre-release or local
    suffix can never rank above the release it belongs to: ``1.0.0-rc1`` is
    ``(1, 0, 0)``, not ``(1, 0, 1)``.
    """
    parts: List[int] = []
    for chunk in str(version).split(".")[:3]:
        digits = ""
        for character in chunk:
            if not character.isdigit():
                break
            digits += character
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return (parts[0], parts[1], parts[2])


__all__ = [
    "ENV_EXPECTED_ROOT",
    "ENV_EXPECTED_ROOT_FALLBACK",
    "ENV_STRICT",
    "MONITORED_PACKAGES",
    "ModuleProvenance",
    "PackageProvenanceError",
    "ProvenanceReport",
    "USER_LEVEL_MARKERS",
    "check_provenance",
    "collect_report",
    "describe_module",
    "expected_roots",
    "is_user_level",
    "is_within",
    "is_within_any",
    "matches_roots",
    "require_expected_origin",
    "resolve_expected_root",
    "sys_path_copies",
    "sys_path_entry",
    "version_tuple",
]
