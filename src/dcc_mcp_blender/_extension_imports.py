"""Resolve public adapter imports inside Blender's extension namespace.

Blender 4.2+ loads extensions below ``bl_ext.<repository>.<extension>`` and
does not put the extension root on ``sys.path``.  DCC-MCP skill scripts keep
using the distribution's public ``dcc_mcp_blender`` import contract, so an
extension needs a namespace bridge without importing a second copy of the
adapter or mutating ``sys.path``.
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.util
import sys
from types import ModuleType
from typing import Any, List, Optional


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

        canonical = importlib.import_module(f"{self.canonical_package}{suffix}")
        return importlib.util.spec_from_loader(
            fullname,
            _AliasLoader(canonical, self),
            is_package=hasattr(canonical, "__path__"),
        )

    def install(self) -> "ExtensionImportAliases":
        if self._installed:
            return self
        canonical = importlib.import_module(self.canonical_package)
        existing = sys.modules.get(self.public_package)
        if existing is not None and existing is not canonical and not self.owns(existing):
            raise RuntimeError(f"Cannot expose {self.public_package!r}: a different module is already loaded")
        sys.meta_path.insert(0, self)
        self._installed = True
        return self

    def uninstall(self) -> None:
        if self in sys.meta_path:
            sys.meta_path.remove(self)
        for name, module in tuple(sys.modules.items()):
            if (name == self.public_package or name.startswith(f"{self.public_package}.")) and self.owns(module):
                sys.modules.pop(name, None)
        self._installed = False

    def owns(self, module: object) -> bool:
        return isinstance(module, ModuleType) and getattr(module, "_dcc_mcp_alias_owner", None) is self


def install_extension_import_aliases(
    canonical_package: str,
    public_package: str = "dcc_mcp_blender",
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
            return finder
    return ExtensionImportAliases(canonical_package, public_package).install()


__all__ = ["ExtensionImportAliases", "install_extension_import_aliases"]
