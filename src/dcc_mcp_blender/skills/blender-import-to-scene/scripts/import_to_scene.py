"""Import an asset described by an AssetDescriptor into the active Blender scene.

Consumes the shared dcc_mcp_core.asset_import contract and delegates to
Blender-native import operators via the existing _interchange_ops module.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from dcc_mcp_core.asset_import import (
    AssetDescriptor,
    AssetFileVariant,
    ImportToSceneResult,
    ImportWarning,
    ImportWarningCode,
    MaterialMode,
    PlacementHint,
)
from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _pick_variant(descriptor: AssetDescriptor) -> AssetFileVariant | None:
    """Pick the best file variant from the descriptor.

    Returns the preferred variant if set, otherwise the first variant.
    """
    for variant in descriptor.variants:
        if variant.preferred:
            return variant
    if descriptor.variants:
        return descriptor.variants[0]
    return None


def _apply_placement(
    bpy: Any,
    imported_names: list[str],
    placement: PlacementHint,
) -> list[ImportWarning]:
    """Apply placement hints to imported objects.

    Returns any warnings encountered.
    """
    warnings: list[ImportWarning] = []

    for name in imported_names:
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue

        if placement.translate:
            obj.location = (
                placement.translate[0] if len(placement.translate) > 0 else 0.0,
                placement.translate[1] if len(placement.translate) > 1 else 0.0,
                placement.translate[2] if len(placement.translate) > 2 else 0.0,
            )

        if placement.rotate:
            import math

            obj.rotation_euler = (
                math.radians(placement.rotate[0] if len(placement.rotate) > 0 else 0.0),
                math.radians(placement.rotate[1] if len(placement.rotate) > 1 else 0.0),
                math.radians(placement.rotate[2] if len(placement.rotate) > 2 else 0.0),
            )

        if placement.scale:
            obj.scale = (
                placement.scale[0] if len(placement.scale) > 0 else 1.0,
                placement.scale[1] if len(placement.scale) > 1 else 1.0,
                placement.scale[2] if len(placement.scale) > 2 else 1.0,
            )

        if placement.parent_name:
            parent = bpy.data.objects.get(placement.parent_name)
            if parent:
                obj.parent = parent
            else:
                warnings.append(
                    ImportWarning(
                        code=ImportWarningCode.UNKNOWN,
                        message=f"Parent object '{placement.parent_name}' not found",
                    )
                )

    return warnings


def _import_file_to_scene(
    bpy: Any,
    filepath: str,
    target_collection: str | None = None,
    material_mode: str = MaterialMode.AS_AUTHORED,
) -> tuple[list[str], list[ImportWarning]]:
    """Import a file into the active Blender scene.

    Uses the existing interchange ops import path for Blender-native import.
    Returns (imported_names, warnings).
    """
    from dcc_mcp_blender._interchange_ops import import_file

    result = import_file(path=filepath, collection_name=target_collection)
    if not result.get("success", False):
        raise RuntimeError(result.get("message", "Import failed"))

    context = result.get("context", {})
    imported_names = context.get("imported_object_names", [])
    if isinstance(imported_names, str):
        imported_names = [n.strip() for n in imported_names.split(",") if n.strip()]

    warnings: list[ImportWarning] = []

    # Handle material mode
    if material_mode == MaterialMode.DEFAULT_GRAY:
        for name in imported_names:
            obj = bpy.data.objects.get(name)
            if obj and hasattr(obj, "material_slots"):
                for slot in obj.material_slots:
                    if slot.material:
                        # Replace with default gray material
                        mat = bpy.data.materials.get("dcc_mcp_default_gray")
                        if not mat:
                            mat = bpy.data.materials.new("dcc_mcp_default_gray")
                            mat.diffuse_color = (0.5, 0.5, 0.5, 1.0)
                        slot.material = mat
        warnings.append(
            ImportWarning(
                code=ImportWarningCode.MATERIAL_FALLBACK,
                message="Materials replaced with default gray per material_mode",
            )
        )

    elif material_mode == MaterialMode.SKIP:
        for name in imported_names:
            obj = bpy.data.objects.get(name)
            if obj and hasattr(obj, "material_slots"):
                obj.material_slots.clear()
        warnings.append(
            ImportWarning(
                code=ImportWarningCode.MATERIAL_FALLBACK,
                message="Materials removed per material_mode=skip",
            )
        )

    return imported_names, warnings


def import_to_scene(
    descriptor: Mapping[str, Any],
    material_mode: str = MaterialMode.AS_AUTHORED,
    placement: Optional[Mapping[str, Any]] = None,
    target_collection: Optional[str] = None,
    skip_existing: bool = False,
) -> dict:
    """Import an asset into the active Blender scene.

    Args:
        descriptor: AssetDescriptor dict (from dcc_mcp_core.asset_import).
        material_mode: Material handling mode (as_authored, default_gray, skip).
        placement: Optional placement hint dict.
        target_collection: Optional collection name.
        skip_existing: Skip if asset_id already present in scene.

    Returns:
        ActionResultModel dict with ImportToSceneResult in context.
    """
    try:
        import bpy
    except ImportError:
        return skill_error(
            "Blender not available",
            "bpy could not be imported — this skill must run inside Blender",
        )

    try:
        desc = AssetDescriptor.from_dict(descriptor)
        desc.validate()
    except Exception as exc:
        return skill_error(
            f"Invalid AssetDescriptor: {exc}",
            "descriptor failed validation — check asset_id and variants",
        )

    # Skip existing check
    if skip_existing:
        # Check if any object in the scene carries the asset_id in its name or custom property
        found = False
        for obj in bpy.data.objects:
            if desc.asset_id in (getattr(obj, "name", "") or ""):
                found = True
                break
            if hasattr(obj, "get") and obj.get("dcc_mcp_asset_id") == desc.asset_id:
                found = True
                break
        if found:
            return skill_success(
                f"Asset '{desc.asset_id}' already present in scene (skipped)",
                asset_id=desc.asset_id,
                skipped=True,
                prompt="Asset is already in the scene. No import needed.",
            )

    # Pick variant
    variant = _pick_variant(desc)
    if variant is None:
        return skill_error(
            f"No file variant available for '{desc.asset_id}'",
            "descriptor.variants is empty",
        )

    filepath = variant.local_path

    # Build placement hint
    placement_hint = None
    if placement:
        placement_hint = PlacementHint.from_dict(placement)

    try:
        imported_names, warnings = _import_file_to_scene(bpy, filepath, target_collection, material_mode)
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to import {filepath}")

    # Apply placement
    if placement_hint:
        placement_warnings = _apply_placement(bpy, imported_names, placement_hint)
        warnings.extend(placement_warnings)

    # Tag imported objects with asset_id for skip_existing support
    for name in imported_names:
        obj = bpy.data.objects.get(name)
        if obj:
            obj["dcc_mcp_asset_id"] = desc.asset_id

    result = ImportToSceneResult(
        success=True,
        imported_nodes=imported_names,
        warnings=warnings,
    )

    return skill_success(
        f"Imported '{desc.asset_id}' into scene ({len(imported_names)} node(s))",
        **result.to_dict(),
        prompt=f"Imported {len(imported_names)} object(s). Use list_objects or get_scene_info to inspect.",
    )


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`import_to_scene`."""
    return import_to_scene(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
