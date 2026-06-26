"""Shared Blender driver/expression operation helpers."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_DRIVER_TYPES = {"SCRIPTED", "AVERAGE", "SUM", "MIN", "MAX"}
_VARIABLE_TYPES = {"SINGLE_PROP", "TRANSFORMS", "ROTATION_DIFF", "LOC_DIFF"}


def _get_object(bpy, object_name: str):
    obj = bpy.data.objects.get(object_name)
    if obj is None:
        return None, skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
    return obj, None


def _ensure_animation_data(obj) -> Any:
    if obj.animation_data is None:
        obj.animation_data_create()
    return obj.animation_data


def _driver_info(fcurve: Any) -> Dict[str, Any]:
    driver = getattr(fcurve, "driver", None)
    if driver is None:
        return {}
    variables = []
    for var in getattr(driver, "variables", []):
        targets = []
        for t in getattr(var, "targets", []):
            targets.append(
                {
                    "id_type": getattr(t, "id_type", None),
                    "data_path": getattr(t, "data_path", ""),
                    "bone_target": getattr(t, "bone_target", ""),
                }
            )
        variables.append(
            {
                "name": getattr(var, "name", ""),
                "type": getattr(var, "type", None),
                "targets": targets,
            }
        )
    return {
        "data_path": getattr(fcurve, "data_path", ""),
        "array_index": getattr(fcurve, "array_index", 0),
        "driver_type": getattr(driver, "type", None),
        "expression": getattr(driver, "expression", ""),
        "use_self": bool(getattr(driver, "use_self", False)),
        "is_valid": bool(getattr(driver, "is_valid", False)),
        "variables": variables,
    }


def _find_driver(bpy, object_name: str, data_path: str, array_index: int = 0) -> tuple[Optional[Any], Optional[dict]]:
    """Return the fcurve driver on *obj[data_path][array_index]*, or an error dict."""
    obj, err = _get_object(bpy, object_name)
    if err:
        return None, err
    anim_data = getattr(obj, "animation_data", None)
    if anim_data is None:
        return None, skill_error(
            f"No animation data on {object_name}",
            "Object has no animation_data; no drivers exist.",
        )
    drivers = getattr(anim_data, "drivers", None)
    if drivers is None:
        return None, skill_error("No drivers", f"{object_name} has no driver fcurves.")
    for fc in drivers:
        if getattr(fc, "data_path", None) == data_path and getattr(fc, "array_index", 0) == array_index:
            return fc, None
    return None, skill_error(
        f"Driver not found: {data_path}[{array_index}]",
        f"No driver on {object_name} for '{data_path}' index {array_index}.",
    )


# ---------------------------------------------------------------------------
# Public operations
# ---------------------------------------------------------------------------


def add_driver(
    object_name: str,
    data_path: str,
    driver_type: str = "SCRIPTED",
    expression: str = "",
    array_index: int = 0,
    use_self: bool = False,
) -> dict:
    """Add a driver on *data_path* of *object_name*.

    Parameters
    ----------
    object_name:
        Name of the Blender object that owns the driven property.
    data_path:
        RNA data path of the property to drive (e.g. ``"location.x"``).
    driver_type:
        One of ``SCRIPTED``, ``AVERAGE``, ``SUM``, ``MIN``, ``MAX``.
    expression:
        Python expression used when *driver_type* is ``SCRIPTED``.
    array_index:
        For array properties; 0-based component index.
    use_self:
        Expose ``self`` in the driver expression namespace.
    """
    try:
        import bpy

        obj, err = _get_object(bpy, object_name)
        if err:
            return err

        normalized = driver_type.upper()
        if normalized not in _DRIVER_TYPES:
            return skill_error(
                f"Unsupported driver_type: {driver_type}",
                f"Expected one of {sorted(_DRIVER_TYPES)}.",
            )

        _ensure_animation_data(obj)
        # obj.driver_add returns an FCurve or a list; normalise to single.
        result = obj.driver_add(data_path, array_index)
        if isinstance(result, list):
            fcurve = result[0] if result else None
        else:
            fcurve = result

        if fcurve is None or getattr(fcurve, "driver", None) is None:
            return skill_error("Driver creation failed", "Blender did not attach a driver.")

        driver = fcurve.driver
        driver.type = normalized
        if normalized == "SCRIPTED":
            driver.expression = expression
        driver.use_self = use_self

        return skill_success(
            f"Added {normalized} driver on {object_name}.{data_path}[{array_index}]",
            object_name=object_name,
            driver=_driver_info(fcurve),
            prompt="Use add_driver_variable to add variables the expression can reference.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to add driver on {object_name}")


def set_driver_expression(
    object_name: str,
    data_path: str,
    expression: str,
    array_index: int = 0,
    driver_type: Optional[str] = None,
    use_self: Optional[bool] = None,
) -> dict:
    """Update the expression (and optionally type) of an existing driver."""
    try:
        import bpy

        fcurve, err = _find_driver(bpy, object_name, data_path, array_index)
        if err:
            return err

        driver = fcurve.driver
        if driver_type is not None:
            normalized = driver_type.upper()
            if normalized not in _DRIVER_TYPES:
                return skill_error(
                    f"Unsupported driver_type: {driver_type}",
                    f"Expected one of {sorted(_DRIVER_TYPES)}.",
                )
            driver.type = normalized
        if expression is not None:
            driver.expression = expression
        if use_self is not None:
            driver.use_self = bool(use_self)

        return skill_success(
            f"Updated driver expression on {object_name}.{data_path}[{array_index}]",
            object_name=object_name,
            driver=_driver_info(fcurve),
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to update driver on {object_name}")


def remove_driver(
    object_name: str,
    data_path: str,
    array_index: int = 0,
) -> dict:
    """Remove the driver on *data_path[array_index]* of *object_name*."""
    try:
        import bpy

        obj, err = _get_object(bpy, object_name)
        if err:
            return err

        # Verify the driver exists first for a clear error message.
        _, find_err = _find_driver(bpy, object_name, data_path, array_index)
        if find_err:
            return find_err

        obj.driver_remove(data_path, array_index)
        return skill_success(
            f"Removed driver from {object_name}.{data_path}[{array_index}]",
            object_name=object_name,
            data_path=data_path,
            array_index=array_index,
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to remove driver from {object_name}")


def list_drivers(object_name: Optional[str] = None) -> dict:
    """List all drivers on *object_name*, or on every object in the scene."""
    try:
        import bpy

        if object_name:
            obj, err = _get_object(bpy, object_name)
            if err:
                return err
            objects: List[Any] = [obj]
        else:
            objects = list(bpy.data.objects)

        entries = []
        for obj in objects:
            anim_data = getattr(obj, "animation_data", None)
            if anim_data is None:
                continue
            for fc in getattr(anim_data, "drivers", []):
                info = _driver_info(fc)
                info["object_name"] = getattr(obj, "name", "")
                entries.append(info)

        return skill_success(
            f"Found {len(entries)} drivers",
            count=len(entries),
            drivers=entries,
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to list drivers")


def add_driver_variable(
    object_name: str,
    data_path: str,
    variable_name: str,
    variable_type: str = "SINGLE_PROP",
    array_index: int = 0,
    target_object: Optional[str] = None,
    target_data_path: Optional[str] = None,
    target_bone: Optional[str] = None,
    transform_type: Optional[str] = None,
) -> dict:
    """Add a variable to an existing driver.

    Parameters
    ----------
    object_name:
        Object that owns the driven property.
    data_path:
        RNA data path of the driven property.
    variable_name:
        Name used to reference this variable in the driver expression.
    variable_type:
        One of ``SINGLE_PROP``, ``TRANSFORMS``, ``ROTATION_DIFF``, ``LOC_DIFF``.
    array_index:
        Component index of the driven property (0-based).
    target_object:
        Name of the object referenced by the variable (optional).
    target_data_path:
        RNA data path on *target_object* (required for ``SINGLE_PROP``).
    target_bone:
        Bone name on *target_object* (for ``TRANSFORMS`` variables).
    transform_type:
        Transform channel, e.g. ``LOC_X``, ``ROT_Y`` (for ``TRANSFORMS``).
    """
    try:
        import bpy

        fcurve, err = _find_driver(bpy, object_name, data_path, array_index)
        if err:
            return err

        normalized_vtype = variable_type.upper()
        if normalized_vtype not in _VARIABLE_TYPES:
            return skill_error(
                f"Unsupported variable_type: {variable_type}",
                f"Expected one of {sorted(_VARIABLE_TYPES)}.",
            )

        driver = fcurve.driver
        var = driver.variables.new()
        var.name = variable_name
        var.type = normalized_vtype

        if target_object or target_data_path:
            target = var.targets[0]
            if target_object:
                tgt_obj = bpy.data.objects.get(target_object)
                if tgt_obj is not None:
                    target.id = tgt_obj
            if target_data_path:
                target.data_path = target_data_path
            if target_bone:
                target.bone_target = target_bone
            if transform_type:
                target.transform_type = transform_type.upper()

        return skill_success(
            f"Added variable '{variable_name}' to driver on {object_name}.{data_path}[{array_index}]",
            object_name=object_name,
            variable_name=variable_name,
            driver=_driver_info(fcurve),
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to add driver variable on {object_name}")


def remove_driver_variable(
    object_name: str,
    data_path: str,
    variable_name: str,
    array_index: int = 0,
) -> dict:
    """Remove a variable from an existing driver by name."""
    try:
        import bpy

        fcurve, err = _find_driver(bpy, object_name, data_path, array_index)
        if err:
            return err

        driver = fcurve.driver
        var = driver.variables.get(variable_name)
        if var is None:
            return skill_error(
                f"Variable not found: {variable_name}",
                f"Driver on {object_name}.{data_path}[{array_index}] has no variable named '{variable_name}'.",
            )
        driver.variables.remove(var)
        return skill_success(
            f"Removed variable '{variable_name}' from driver on {object_name}.{data_path}[{array_index}]",
            object_name=object_name,
            variable_name=variable_name,
            driver=_driver_info(fcurve),
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to remove driver variable on {object_name}")


def evaluate_driver_expression(
    object_name: str,
    data_path: str,
    array_index: int = 0,
) -> dict:
    """Return the current evaluated value of a driver fcurve at the scene frame.

    This performs a lightweight read — it does not force a dependency graph
    update; the value reflects the last evaluated state.
    """
    try:
        import bpy

        fcurve, err = _find_driver(bpy, object_name, data_path, array_index)
        if err:
            return err

        current_frame = float(bpy.context.scene.frame_current)
        try:
            value = fcurve.evaluate(current_frame)
        except Exception:
            value = None

        driver = getattr(fcurve, "driver", None)
        is_valid = bool(getattr(driver, "is_valid", False)) if driver else False

        return skill_success(
            f"Evaluated driver on {object_name}.{data_path}[{array_index}]",
            object_name=object_name,
            data_path=data_path,
            array_index=array_index,
            frame=current_frame,
            value=value,
            is_valid=is_valid,
            expression=getattr(driver, "expression", "") if driver else "",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to evaluate driver on {object_name}")
