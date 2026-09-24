"""Resolve public adapter imports inside Blender's extension namespace.

Blender 4.2+ loads extensions below ``bl_ext.<repository>.<extension>`` and
does not put the extension root on ``sys.path``.  DCC-MCP skill scripts keep
using the distribution's public ``dcc_mcp_blender`` import contract, so an
extension needs a namespace bridge without importing a second copy of the
adapter or mutating ``sys.path``.

The bridge deliberately outlives ``register()`` / ``unregister()`` cycles.
``bpy.ops.wm.read_factory_settings(use_empty=True)`` — the standard "open a
clean scene" prologue in headless batch pipelines — makes Blender disable every
add-on and can drop ``bl_ext.*`` from ``sys.modules``.  A bridge that is torn
down in ``unregister()`` therefore turns the very next ``import dcc_mcp_blender``
into ``ModuleNotFoundError``, and no ``sys.path`` edit can repair it because in
the extension layout the public package exists only as this finder.  Callers
that really want the bridge gone (a failed enable) use
:meth:`ExtensionImportAliases.uninstall`; an ordinary disable uses
:meth:`ExtensionImportAliases.detach`.
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import logging
import sys
from importlib.machinery import PathFinder
from pathlib import Path
from types import ModuleType
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


class _AliasModule(ModuleType):
    """Module facade delegating reads to one canonical extension module."""

    def __init__(self, alias: str, target: ModuleType, owner: "ExtensionImportAliases") -> None:
        super().__init__(alias, getattr(target, "__doc__", None))
        self.__dict__["_dcc_mcp_alias_target"] = target
        self.__dict__["_dcc_mcp_alias_owner"] = owner
        if hasattr(target, "__path__"):
            self.__path__ = target.__path__  # type: ignore[attr-defined]

    def __getattr__(self, name: str) -> Any:
        return getattr(self.__dict__["_dcc_mcp_alias_target"], name)

    def __dir__(self) -> List[str]:
        return sorted(set(super().__dir__()) | set(dir(self.__dict__["_dcc_mcp_alias_target"])))


class _AliasLoader(importlib.abc.Loader):
    def __init__(self, target: ModuleType, owner: "ExtensionImportAliases") -> None:
        self._target = target
        self._owner = owner

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> ModuleType:
        return _AliasModule(spec.name, self._target, self._owner)

    def exec_module(self, module: ModuleType) -> None:
        return None


class ExtensionImportAliases(importlib.abc.MetaPathFinder):
    """Map one public package prefix to the already-loaded extension package."""

    def __init__(self, canonical_package: str, public_package: str) -> None:
        self.canonical_package = canonical_package
        self.public_package = public_package
        self._installed = False
        # On-disk directory of the canonical package. Used only to rebuild the
        # public package when Blender drops ``bl_ext.*`` from ``sys.modules``;
        # never reported in user-facing text.
        self._fallback_root: Optional[Path] = None

    # -- installation -------------------------------------------------------

    def install(self, *, strict: bool = True) -> "ExtensionImportAliases":
        """Install the bridge.

        Args:
            strict: Raise when a conflicting ``public_package`` module already
                occupies ``sys.modules``.  Pass ``False`` for best-effort
                installation while Blender is merely scanning add-ons.
        """
        if self._installed:
            return self
        canonical = importlib.import_module(self.canonical_package)
        existing = sys.modules.get(self.public_package)
        if existing is not None and existing is not canonical and not self.owns(existing):
            if strict:
                raise RuntimeError(f"Cannot expose {self.public_package!r}: a different module is already loaded")
            return self
        self._capture_fallback_root(canonical)
        sys.meta_path.insert(0, self)
        self._installed = True
        return self

    def uninstall(self) -> None:
        """Remove the finder and every facade it created."""
        self._drop_alias_modules()
        if self in sys.meta_path:
            sys.meta_path.remove(self)
        self._installed = False

    def detach(self) -> "ExtensionImportAliases":
        """Drop cached facades but keep the public import contract resolvable.

        Used when Blender disables the add-on (preference reset, add-on toggle,
        script reload).  The stale facades must go so a later enable re-points
        the public name at the freshly imported extension module, but the finder
        itself has to stay: headless batch scripts import ``dcc_mcp_blender``
        right after such a reset and must not see ``ModuleNotFoundError``.
        """
        self._drop_alias_modules()
        return self

    @property
    def installed(self) -> bool:
        return self._installed

    def owns(self, module: object) -> bool:
        return isinstance(module, ModuleType) and getattr(module, "_dcc_mcp_alias_owner", None) is self

    # -- resolution ---------------------------------------------------------

    def find_spec(
        self,
        fullname: str,
        path: Optional[object],
        target: Optional[ModuleType] = None,
    ) -> Optional[importlib.machinery.ModuleSpec]:
        del path, target
        if fullname == self.public_package:
            suffix = ""
        elif fullname.startswith(f"{self.public_package}."):
            suffix = fullname[len(self.public_package) :]
        else:
            return None

        canonical = self._resolve_canonical(suffix)
        return importlib.util.spec_from_loader(
            fullname,
            _AliasLoader(canonical, self),
            is_package=hasattr(canonical, "__path__"),
        )

    def _resolve_canonical(self, suffix: str) -> ModuleType:
        """Return the canonical module, rebuilding it from disk when needed."""
        name = f"{self.canonical_package}{suffix}"
        module = sys.modules.get(name)
        if module is not None:
            return module
        try:
            return importlib.import_module(name)
        except ImportError:
            module = self._rebuild_from_disk(name, fullname=f"{self.public_package}{suffix}")
            if module is None:
                raise
            return module

    def _capture_fallback_root(self, canonical: ModuleType) -> None:
        """Record where the adapter modules live for a later disk rebuild.

        ``__path__`` is what the import system actually searches, so prefer it
        over ``__file__``: the Blender add-on entrypoint and the adapter modules
        share one directory, but a caller may legitimately stage them apart.
        """
        search_path = getattr(canonical, "__path__", None)
        candidates: list[Path] = []
        if search_path:
            candidates.extend(Path(entry) for entry in search_path)
        module_file = getattr(canonical, "__file__", None)
        if module_file:
            candidates.append(Path(module_file).parent)
        self._fallback_root = next((path for path in candidates if path.is_dir()), None)

    def _fallback_spec(self, fullname: str) -> Optional[importlib.machinery.ModuleSpec]:
        """Build a spec for ``public_package[.sub…]`` from the extension dir.

        The canonical package directory holds exactly the public package's
        modules: in the extension layout the add-on root *is* the
        ``dcc_mcp_blender`` package, so ``dcc_mcp_blender.host`` maps to
        ``<extension dir>/host.py`` regardless of the ``bl_ext`` namespace.
        """
        root = self._fallback_root
        if root is None:
            return None
        prefix_length = len(self.public_package.split("."))
        parts = fullname.split(".")[prefix_length:]
        target = root.joinpath(*parts)
        init_file = target / "__init__.py"
        if init_file.is_file():
            return importlib.util.spec_from_file_location(fullname, init_file, submodule_search_locations=[str(target)])
        module_file = target.with_suffix(".py")
        if module_file.is_file():
            return importlib.util.spec_from_file_location(fullname, module_file)
        return None

    def _rebuild_from_disk(self, canonical_name: str, *, fullname: str) -> Optional[ModuleType]:
        """Re-import a dropped extension module straight from the extension dir.

        ``read_factory_settings`` can purge ``bl_ext.*`` from ``sys.modules``.
        When that happens the canonical import machinery can no longer find the
        package at all, so fall back to the recorded extension directory and
        register the rebuilt module under its canonical name — that keeps
        relative imports inside the adapter working.
        """
        spec = self._fallback_spec(fullname)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        # Point the rebuilt package back at the extension directory: the
        # spec origin alone would leave submodules unresolvable. The real
        # Blender layout puts the add-on entry and the adapter modules in
        # the same directory, so this is a no-op there and a repair here.
        if hasattr(module, "__path__") and self._fallback_root is not None:
            module.__path__ = [str(self._fallback_root)]  # type: ignore[attr-defined]
        sys.modules[canonical_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(canonical_name, None)
            raise
        return module

    def _drop_alias_modules(self) -> None:
        for name, module in tuple(sys.modules.items()):
            if (name == self.public_package or name.startswith(f"{self.public_package}.")) and self.owns(module):
                sys.modules.pop(name, None)


def public_package_origin(
    public_package: str = "dcc_mcp_blender",
    meta_path: Optional[List[Any]] = None,
) -> Optional[str]:
    """Return the path-based origin of ``public_package``, ignoring alias bridges.

    Resolving through :data:`sys.meta_path` as it stands would report the
    extension's own facade: the bridge sits at the front of the chain so skill
    scripts keep working, and ``find_spec`` short-circuits on
    :data:`sys.modules` before it ever looks at ``sys.path``. Every other finder
    is consulted in order, so a caller can inject its own chain through
    ``meta_path``; alias bridges in that chain are skipped because they only
    ever report the extension namespace.

    Returns ``None`` when only the extension namespace provides the package.
    """
    # An injected chain is authoritative: a caller that passes one is asking
    # what *that* chain resolves, so the default path finder is not consulted.
    finders = list(sys.meta_path if meta_path is None else meta_path)
    if meta_path is None and PathFinder not in finders:
        finders.append(PathFinder)
    for finder in finders:
        if isinstance(finder, ExtensionImportAliases):
            continue
        find_spec = getattr(finder, "find_spec", None)
        if find_spec is None:
            continue
        try:
            spec = find_spec(public_package, None)
        except (ImportError, ValueError, AttributeError, TypeError) as exc:
            logger.debug("finder %r could not resolve %s: %s", finder, public_package, exc)
            continue
        origin = _spec_origin(spec)
        if origin:
            return origin
    return None


def _spec_origin(spec: Optional[importlib.machinery.ModuleSpec]) -> Optional[str]:
    """Return the file or directory a resolved spec points at."""
    if spec is None:
        return None
    if spec.origin and str(spec.origin) not in ("built-in", "frozen"):
        return str(spec.origin)
    locations = [str(entry) for entry in (spec.submodule_search_locations or ())]
    return locations[0] if locations else None


def install_extension_import_aliases(
    canonical_package: str,
    public_package: str = "dcc_mcp_blender",
    *,
    strict: bool = True,
) -> ExtensionImportAliases:
    """Install an idempotent, removable public-import bridge."""
    if not canonical_package or canonical_package == public_package:
        raise ValueError("canonical_package must be a distinct extension namespace")
    for finder in sys.meta_path:
        if (
            isinstance(finder, ExtensionImportAliases)
            and finder.canonical_package == canonical_package
            and finder.public_package == public_package
        ):
            return finder.install(strict=strict)
    return ExtensionImportAliases(canonical_package, public_package).install(strict=strict)


__all__ = [
    "ExtensionImportAliases",
    "install_extension_import_aliases",
    "public_package_origin",
]
