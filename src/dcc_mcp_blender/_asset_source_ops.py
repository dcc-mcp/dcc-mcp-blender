"""Blender asset source discovery — filesystem scan and Blender asset library search.

Returns validated ``AssetDescriptor`` dicts consumable by the downstream
import pipeline (``blender-interchange`` / ``blender-asset-import``).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, TypedDict

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

# Supported 3D file extensions and their canonical type names.
_SUPPORTED_ASSET_TYPES: dict[str, str] = {
    ".blend": "blend",
    ".fbx": "fbx",
    ".obj": "obj",
    ".usd": "usd",
    ".usda": "usda",
    ".usdc": "usdc",
    ".abc": "alembic",
    ".gltf": "gltf",
    ".glb": "glb",
    ".ply": "ply",
    ".stl": "stl",
    ".dae": "collada",
    ".3ds": "autodesk_3ds",
}

_DEFAULT_MAX_RESULTS = 50


class AssetDescriptor(TypedDict, total=False):
    """Descriptor for a discovered asset.

    Every returned descriptor is validated at search time — the file must
    exist, be readable, and match the requested filters.
    """

    name: str
    """Display name (filename stem)."""

    path: str
    """Absolute filesystem path."""

    asset_type: str
    """Canonical type string (e.g. ``"blend"``, ``"fbx"``, ``"usd"``)."""

    source: str
    """Origin — ``"filesystem"`` or ``"asset_library"``."""

    size_bytes: int
    """File size in bytes (0 when unavailable)."""

    modified_at: str
    """ISO-8601 last-modified timestamp (empty when unavailable)."""

    metadata: Dict[str, Any]
    """Optional extra metadata from the asset source."""


def _build_descriptor(
    path: Path,
    asset_type: str,
    source: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> AssetDescriptor:
    stat = path.stat() if path.exists() else None
    return AssetDescriptor(
        name=path.stem,
        path=str(path.resolve()),
        asset_type=asset_type,
        source=source,
        size_bytes=stat.st_size if stat else 0,
        modified_at=(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(stat.st_mtime)) if stat else ""),
        metadata=metadata or {},
    )


def _type_from_suffix(suffix: str) -> Optional[str]:
    return _SUPPORTED_ASSET_TYPES.get(suffix.lower())


def _name_matches(name: str, query: Optional[str]) -> bool:
    if not query:
        return True
    return query.lower() in name.lower()


def _scan_filesystem(
    search_path: Path,
    query: Optional[str] = None,
    allowed_types: Optional[set[str]] = None,
    max_results: int = _DEFAULT_MAX_RESULTS,
) -> tuple[List[AssetDescriptor], Optional[dict]]:
    """Walk *search_path* and return validated ``AssetDescriptor``s."""
    if not search_path.is_dir():
        return [], skill_error(
            "Directory not found",
            f"No directory at '{search_path}'.",
        )

    results: List[AssetDescriptor] = []
    errors: List[str] = []
    try:
        for entry in search_path.iterdir():
            if len(results) >= max_results:
                break
            if not entry.is_file():
                continue
            suffix = entry.suffix.lower()
            asset_type = _type_from_suffix(suffix)
            if asset_type is None:
                continue
            if allowed_types is not None and asset_type not in allowed_types:
                continue
            if not _name_matches(entry.stem, query):
                continue
            try:
                desc = _build_descriptor(entry, asset_type, "filesystem")
                results.append(desc)
            except OSError as exc:
                errors.append(f"Cannot stat {entry.name}: {exc}")
                continue
    except PermissionError as exc:
        return results, skill_error("Permission denied", f"Cannot read directory '{search_path}': {exc}")
    except Exception as exc:
        return results, skill_exception(exc, message=f"Failed to scan '{search_path}'")

    return results, None


def _scan_asset_library(
    bpy: Any,
    query: Optional[str] = None,
    allowed_types: Optional[set[str]] = None,
    max_results: int = _DEFAULT_MAX_RESULTS,
) -> tuple[List[AssetDescriptor], Optional[dict]]:
    """Scan Blender's registered asset libraries via ``bpy.data.asset_libraries``."""
    results: List[AssetDescriptor] = []

    # Force-refresh catalogues so the search sees the latest state.
    try:
        bpy.ops.asset.library_refresh()
    except Exception:
        pass

    libraries = getattr(bpy.data, "asset_libraries", None)

    if libraries is None or not hasattr(libraries, "__iter__"):
        return results, None

    try:
        for lib in libraries:
            lib_path = getattr(lib, "path", None)
            if not lib_path:
                continue
            lib_dir = Path(lib_path)
            if not lib_dir.is_dir():
                continue
            sub_results, _ = _scan_filesystem(
                lib_dir,
                query=query,
                allowed_types=allowed_types,
                max_results=max_results - len(results),
            )
            for desc in sub_results:
                desc["source"] = "asset_library"
                desc["metadata"]["library_name"] = getattr(lib, "name", "")
            results.extend(sub_results)
            if len(results) >= max_results:
                break
    except Exception as exc:
        return results, skill_exception(exc, message="Failed to scan asset libraries")

    return results, None


def search_assets(
    query: Optional[str] = None,
    source: str = "all",
    path: Optional[str] = None,
    asset_types: Optional[Sequence[str]] = None,
    max_results: int = _DEFAULT_MAX_RESULTS,
) -> dict:
    """Search for discoverable assets and return validated ``AssetDescriptor[]``.

    Parameters
    ----------
    query:
        Optional substring filter against the asset name/display name (case-insensitive).
    source:
        Which source(s) to search: ``"filesystem"``, ``"asset_library"``, or
        ``"all"`` (default).
    path:
        Directory path for filesystem search.  Required when ``source`` is
        ``"filesystem"`` or ``"all"``.
    asset_types:
        Optional list of type strings to filter by (e.g. ``["blend", "fbx"]``).
        When omitted, all supported types are searched.
    max_results:
        Maximum number of descriptors to return (default 50).

    Returns
    -------
    dict
        Skill result with ``descriptors`` list, ``count``, ``source``,
        and ``path`` in the context.
    """
    allowed: Optional[set[str]] = None
    if asset_types is not None:
        allowed = set(str(t).lower() for t in asset_types)
        unknown = allowed - set(_SUPPORTED_ASSET_TYPES.values())
        if unknown:
            return skill_error(
                "Unsupported asset type(s)",
                f"Unsupported types: {sorted(unknown)}. Supported: {sorted(set(_SUPPORTED_ASSET_TYPES.values()))}.",
            )

    start = time.perf_counter()
    all_results: List[AssetDescriptor] = []
    warnings: List[str] = []
    truncated = False

    try:
        import bpy
    except ImportError:
        bpy = None

    # Filesystem scan.
    run_fs = source in ("filesystem", "all")
    search_path: Optional[Path] = None
    if run_fs:
        if path:
            search_path = Path(path).expanduser().resolve()
        elif bpy is not None:
            blend_path = getattr(bpy.data, "filepath", "")
            if blend_path:
                search_path = Path(blend_path).parent.resolve()
        if search_path is None:
            return skill_error(
                "No search path",
                "Pass a ``path`` or open a Blender scene so the blend-file directory can be used.",
            )
        fs_results, fs_error = _scan_filesystem(
            search_path,
            query=query,
            allowed_types=allowed,
            max_results=max_results,
        )
        # Non-fatal: partial results are still useful.
        if fs_error and not fs_results:
            return fs_error
        if fs_error:
            warnings.append(fs_error.get("message", "Filesystem scan had errors"))
        all_results.extend(fs_results)
        if len(all_results) >= max_results:
            all_results = all_results[:max_results]
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            return skill_success(
                f"Found {len(all_results)} asset(s)",
                descriptors=all_results,
                count=len(all_results),
                source=source,
                path=str(search_path),
                elapsed_ms=elapsed_ms,
                truncated=True,
                warnings=warnings,
                prompt="Pass a ``path`` or ``query`` for narrower results, or use "
                "downstream search on an asset source server. "
                "Use ``import_file`` / ``import_fbx`` / ``import_obj`` / "
                "``import_usd`` to load a selected asset into the scene.",
            )

    # Asset library scan.
    if source in ("asset_library", "all") and bpy is not None:
        lib_results, lib_error = _scan_asset_library(
            bpy,
            query=query,
            allowed_types=allowed,
            max_results=max_results - len(all_results),
        )
        if lib_error:
            if not all_results:
                return lib_error
            warnings.append(lib_error.get("message", "Asset library scan had errors"))
        all_results.extend(lib_results)
        if len(all_results) >= max_results:
            all_results = all_results[:max_results]
            truncated = True

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    context: Dict[str, Any] = dict(
        descriptors=all_results,
        count=len(all_results),
        source=source,
    )
    if search_path:
        context["path"] = str(search_path)
    if warnings:
        context["warnings"] = warnings
    if truncated:
        context["truncated"] = True

    return skill_success(
        f"Found {len(all_results)} asset(s)",
        **context,
        prompt="Use ``import_file`` / ``import_fbx`` / ``import_obj`` / "
        "``import_usd`` to load a selected asset into the scene.",
    )
