"""Blender custom property (attribute) CRUD operations."""

from __future__ import annotations

from typing import Any

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success


def _resolve_id(bpy: Any, object_name: str) -> tuple[Any, dict | None]:
    """Resolve a Blender ID block by object name."""
    obj = bpy.data.objects.get(object_name)
    if obj is None:
        return None, skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
    return obj, None


def list_attributes(object_name: str) -> dict:
    """List all custom properties on a Blender object."""
    try:
        import bpy

        obj, error = _resolve_id(bpy, object_name)
        if error:
            return error

        props = {}
        if hasattr(obj, "keys"):
            for key in obj.keys():
                if key.startswith("_"):
                    continue
                try:
                    value = obj[key]
                    props[key] = {
                        "name": key,
                        "value": value,
                        "type": type(value).__name__,
                    }
                except Exception:
                    pass

        return skill_success(
            f"Found {len(props)} custom propert{'y' if len(props) == 1 else 'ies'} on {object_name}",
            object_name=object_name,
            attributes=props,
            count=len(props),
            prompt="Use get_attribute to inspect a specific property or set_attribute to create/update.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to list attributes on {object_name}")


def get_attribute(object_name: str, attribute_name: str) -> dict:
    """Get a custom property value by name."""
    if not attribute_name:
        return skill_error("Invalid attribute_name", "attribute_name must be a non-empty string.")
    try:
        import bpy

        obj, error = _resolve_id(bpy, object_name)
        if error:
            return error

        if attribute_name not in obj:
            return skill_error(
                f"Attribute not found: {attribute_name}",
                f"Object '{object_name}' has no custom property named '{attribute_name}'.",
            )

        value = obj[attribute_name]
        ui_data = None
        try:
            ui = obj.id_properties_ui(attribute_name)
            ui_data = ui.as_dict() if ui else None
        except Exception:
            pass

        return skill_success(
            f"Read attribute {attribute_name} on {object_name}",
            object_name=object_name,
            attribute_name=attribute_name,
            value=value,
            type=type(value).__name__,
            ui_data=ui_data,
            prompt="Use set_attribute to update the value or delete_attribute to remove it.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to get attribute {attribute_name} on {object_name}")


def set_attribute(
    object_name: str,
    attribute_name: str,
    value: Any,
    ui_min: float | None = None,
    ui_max: float | None = None,
    ui_description: str | None = None,
) -> dict:
    """Set a custom property value on an object."""
    if not attribute_name:
        return skill_error("Invalid attribute_name", "attribute_name must be a non-empty string.")
    try:
        import bpy

        obj, error = _resolve_id(bpy, object_name)
        if error:
            return error

        # Validate value type
        if isinstance(value, (list, tuple)):
            if not all(isinstance(v, (int, float)) for v in value):
                return skill_error(
                    "Invalid attribute value",
                    "Array attributes must contain only numeric values.",
                )

        obj[attribute_name] = value

        # Apply UI metadata if provided
        if any(x is not None for x in (ui_min, ui_max, ui_description)):
            try:
                ui = obj.id_properties_ui(attribute_name)
                kwargs = {}
                if ui_min is not None:
                    kwargs["min"] = ui_min
                if ui_max is not None:
                    kwargs["max"] = ui_max
                if ui_description is not None:
                    kwargs["description"] = ui_description
                if kwargs:
                    ui.update(**kwargs)
            except Exception:
                pass

        return skill_success(
            f"Set attribute {attribute_name} on {object_name}",
            object_name=object_name,
            attribute_name=attribute_name,
            value=obj.get(attribute_name),
            type=type(value).__name__,
            prompt="Use get_attribute to verify or list_attributes to see all custom properties.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to set attribute {attribute_name} on {object_name}")


def delete_attribute(object_name: str, attribute_name: str) -> dict:
    """Delete a custom property from an object."""
    if not attribute_name:
        return skill_error("Invalid attribute_name", "attribute_name must be a non-empty string.")
    try:
        import bpy

        obj, error = _resolve_id(bpy, object_name)
        if error:
            return error

        if attribute_name not in obj:
            return skill_error(
                f"Attribute not found: {attribute_name}",
                f"Object '{object_name}' has no custom property named '{attribute_name}'.",
            )

        del obj[attribute_name]
        return skill_success(
            f"Deleted attribute {attribute_name} from {object_name}",
            object_name=object_name,
            attribute_name=attribute_name,
            prompt="Use list_attributes to verify the remaining custom properties.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to delete attribute {attribute_name} on {object_name}")


def rename_attribute(object_name: str, old_name: str, new_name: str) -> dict:
    """Rename a custom property on an object."""
    if not old_name:
        return skill_error("Invalid old_name", "old_name must be a non-empty string.")
    if not new_name:
        return skill_error("Invalid new_name", "new_name must be a non-empty string.")
    try:
        import bpy

        obj, error = _resolve_id(bpy, object_name)
        if error:
            return error

        if old_name not in obj:
            return skill_error(
                f"Attribute not found: {old_name}",
                f"Object '{object_name}' has no custom property named '{old_name}'.",
            )

        if old_name == new_name:
            return skill_error("No change", "old_name and new_name are identical.")

        obj[new_name] = obj[old_name]
        del obj[old_name]

        return skill_success(
            f"Renamed attribute from {old_name} to {new_name} on {object_name}",
            object_name=object_name,
            old_name=old_name,
            new_name=new_name,
            prompt="Use list_attributes to verify or get_attribute to inspect the renamed property.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to rename attribute on {object_name}")
