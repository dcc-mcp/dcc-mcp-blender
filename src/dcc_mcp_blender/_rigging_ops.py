"""Shared implementations for Blender rigging operation tools."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

_MIRROR_AXES = {"x": 0, "y": 1, "z": 2}
_BIND_METHODS = {"modifier", "automatic_weights"}


def _object_by_name(bpy: Any, object_name: str) -> tuple[Any | None, dict | None]:
    obj = bpy.data.objects.get(object_name)
    if obj is None:
        return None, skill_error(f"Object not found: {object_name}", f"No object named '{object_name}'.")
    return obj, None


def _typed_object(bpy: Any, object_name: str, object_type: str) -> tuple[Any | None, dict | None]:
    obj, error = _object_by_name(bpy, object_name)
    if error:
        return None, error
    if getattr(obj, "type", None) != object_type:
        return None, skill_error(
            f"{object_name} is not a {object_type}", f"Object type is {getattr(obj, 'type', None)}."
        )
    return obj, None


def _vector(
    value: Sequence[float] | None, label: str, default: Sequence[float] | None = None
) -> tuple[list[float] | None, dict | None]:
    raw = default if value is None else value
    if raw is None:
        return None, None
    if isinstance(raw, (str, bytes)) or len(raw) != 3:
        return None, skill_error(f"Invalid {label}", f"{label} must contain exactly three numbers.")
    try:
        coords = [float(coord) for coord in raw]
    except (TypeError, ValueError):
        return None, skill_error(f"Invalid {label}", f"{label} must contain numbers.")
    return coords, None


def _set_active(bpy: Any, obj: Any) -> None:
    try:
        bpy.ops.object.mode_set(mode="OBJECT")
    except Exception:
        pass
    try:
        bpy.ops.object.select_all(action="DESELECT")
    except Exception:
        pass
    select_set = getattr(obj, "select_set", None)
    if callable(select_set):
        select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.context.active_object = obj
    except Exception:
        pass


def _object_mode(bpy: Any) -> None:
    try:
        bpy.ops.object.mode_set(mode="OBJECT")
    except Exception:
        pass


def _collection_get(collection: Any, name: str) -> Any | None:
    get = getattr(collection, "get", None)
    if callable(get):
        return get(name)
    return next((item for item in collection if getattr(item, "name", None) == name), None)


def _collection_len(collection: Any) -> int:
    try:
        return len(collection)
    except TypeError:
        return sum(1 for _ in collection)


def _constraint_by_name(obj: Any, constraint_name: str) -> Any | None:
    return _collection_get(getattr(obj, "constraints", []), constraint_name)


def _pose_bone_map(armature: Any) -> dict[str, Any]:
    pose = getattr(armature, "pose", None)
    bones = getattr(pose, "bones", []) if pose is not None else []
    return {bone.name: bone for bone in bones}


def _mirror_name(name: str) -> str:
    pairs = [
        (".L", ".R"),
        ("_L", "_R"),
        ("-L", "-R"),
        ("Left", "Right"),
        ("left", "right"),
        ("L_", "R_"),
    ]
    for left, right in pairs:
        if name.endswith(left):
            return name[: -len(left)] + right
        if name.endswith(right):
            return name[: -len(right)] + left
        if name.startswith(left):
            return right + name[len(left) :]
        if name.startswith(right):
            return left + name[len(right) :]
    return f"{name}_mirror"


def _mirror_vector(value: Sequence[float], axis: str) -> list[float]:
    coords = [float(coord) for coord in value]
    coords[_MIRROR_AXES[axis]] *= -1.0
    return coords


def create_armature(name: str, location: Sequence[float] | None = None) -> dict:
    """Create an armature object."""
    if not name or not name.strip():
        return skill_error("Invalid name", "name must be a non-empty string.")
    loc, error = _vector(location, "location", default=(0.0, 0.0, 0.0))
    if error:
        return error
    try:
        import bpy

        _object_mode(bpy)
        bpy.ops.object.armature_add(enter_editmode=False, align="WORLD", location=tuple(loc))
        armature = getattr(bpy.context, "active_object", None)
        if armature is None:
            armature = getattr(bpy.context, "object", None)
        if armature is None:
            return skill_error("Armature creation failed", "Blender did not return an active armature object.")
        armature.name = name
        if getattr(armature, "data", None) is not None:
            armature.data.name = name
        return skill_success(
            f"Created armature {armature.name}",
            armature_name=armature.name,
            data_name=getattr(getattr(armature, "data", None), "name", None),
            location=loc,
            bone_count=_collection_len(getattr(getattr(armature, "data", None), "bones", [])),
            prompt="Use create_bone to add edit bones or blender-pose-library to capture poses.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to create armature {name}")


def create_bone(
    armature_name: str,
    bone_name: str,
    head: Sequence[float],
    tail: Sequence[float],
    parent: str | None = None,
) -> dict:
    """Create an edit bone in an armature."""
    if not bone_name or not bone_name.strip():
        return skill_error("Invalid bone_name", "bone_name must be a non-empty string.")
    head_vec, error = _vector(head, "head")
    if error:
        return error
    tail_vec, error = _vector(tail, "tail")
    if error:
        return error
    if head_vec == tail_vec:
        return skill_error("Invalid bone length", "head and tail must not be identical.")
    try:
        import bpy

        armature, error = _typed_object(bpy, armature_name, "ARMATURE")
        if error:
            return error
        _set_active(bpy, armature)
        bpy.ops.object.mode_set(mode="EDIT")
        edit_bones = armature.data.edit_bones
        if _collection_get(edit_bones, bone_name) is not None:
            _object_mode(bpy)
            return skill_error(
                f"Bone already exists: {bone_name}", f"{armature_name} already has a bone named '{bone_name}'."
            )
        bone = edit_bones.new(bone_name)
        bone.head = head_vec
        bone.tail = tail_vec
        if parent:
            parent_bone = _collection_get(edit_bones, parent)
            if parent_bone is None:
                _object_mode(bpy)
                return skill_error(
                    f"Parent bone not found: {parent}", f"{armature_name} has no edit bone named '{parent}'."
                )
            bone.parent = parent_bone
        _object_mode(bpy)
        return skill_success(
            f"Created bone {bone_name}",
            armature_name=armature.name,
            bone_name=bone_name,
            parent=parent,
            head=head_vec,
            tail=tail_vec,
            bone_count=_collection_len(getattr(armature.data, "bones", [])),
            prompt="Use mirror_bones, bind_mesh_to_armature, or save_pose to continue rig setup.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        _object_mode(bpy)
        return skill_exception(exc, message=f"Failed to create bone {bone_name}")


def mirror_bones(armature_name: str, axis: str = "x", naming_rule: str = "suffix") -> dict:
    """Mirror edit bones by coordinates and left/right naming conventions."""
    axis_key = axis.lower()
    if axis_key not in _MIRROR_AXES:
        return skill_error("Invalid mirror axis", "axis must be one of: x, y, z.")
    if naming_rule not in {"suffix", "prefix", "auto"}:
        return skill_error("Invalid naming_rule", "naming_rule must be suffix, prefix, or auto.")
    try:
        import bpy

        armature, error = _typed_object(bpy, armature_name, "ARMATURE")
        if error:
            return error
        _set_active(bpy, armature)
        bpy.ops.object.mode_set(mode="EDIT")
        edit_bones = armature.data.edit_bones
        originals = list(edit_bones)
        existing = {bone.name for bone in originals}
        created = []
        skipped = []
        for source in originals:
            target_name = _mirror_name(source.name)
            if target_name in existing:
                skipped.append(target_name)
                continue
            target = edit_bones.new(target_name)
            target.head = _mirror_vector(source.head, axis_key)
            target.tail = _mirror_vector(source.tail, axis_key)
            target.roll = -float(getattr(source, "roll", 0.0))
            created.append(target_name)
            existing.add(target_name)
        _object_mode(bpy)
        return skill_success(
            f"Mirrored {len(created)} bone(s)",
            armature_name=armature.name,
            axis=axis_key,
            naming_rule=naming_rule,
            created_bones=created,
            skipped_bones=skipped,
            created_count=len(created),
            prompt="Use create_bone for manual additions or save_pose after posing the rig.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        _object_mode(bpy)
        return skill_exception(exc, message=f"Failed to mirror bones on {armature_name}")


def add_constraint(object_name: str, constraint_type: str, target: str | None = None) -> dict:
    """Add a Blender constraint to an object."""
    if not constraint_type or not constraint_type.strip():
        return skill_error("Invalid constraint_type", "constraint_type must be a non-empty Blender constraint type.")
    try:
        import bpy

        obj, error = _object_by_name(bpy, object_name)
        if error:
            return error
        target_obj = None
        if target:
            target_obj, error = _object_by_name(bpy, target)
            if error:
                return error
        constraint = obj.constraints.new(type=constraint_type.upper())
        if target_obj is not None and hasattr(constraint, "target"):
            constraint.target = target_obj
        return skill_success(
            f"Added {constraint.type} constraint to {obj.name}",
            object_name=obj.name,
            constraint_name=constraint.name,
            constraint_type=constraint.type,
            target=getattr(target_obj, "name", None),
            constraint_count=_collection_len(getattr(obj, "constraints", [])),
            prompt="Use set_constraint_properties to tune the new constraint.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to add constraint to {object_name}")


def set_constraint_properties(object_name: str, constraint_name: str, properties: Mapping[str, Any]) -> dict:
    """Set supported properties on an existing object constraint."""
    if not isinstance(properties, Mapping) or not properties:
        return skill_error("Invalid properties", "properties must be a non-empty object.")
    try:
        import bpy

        obj, error = _object_by_name(bpy, object_name)
        if error:
            return error
        constraint = _constraint_by_name(obj, constraint_name)
        if constraint is None:
            return skill_error(
                f"Constraint not found: {constraint_name}",
                f"{object_name} has no constraint named '{constraint_name}'.",
            )
        applied = {}
        ignored = []
        for key, value in properties.items():
            if hasattr(constraint, key):
                setattr(constraint, key, value)
                applied[key] = value
            else:
                ignored.append(key)
        return skill_success(
            f"Updated constraint {constraint.name}",
            object_name=obj.name,
            constraint_name=constraint.name,
            applied=applied,
            ignored=ignored,
            prompt="Use object inspection or Blender UI to verify constraint behavior.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to set constraint properties on {object_name}")


def bind_mesh_to_armature(mesh_name: str, armature_name: str, method: str = "modifier") -> dict:
    """Bind a mesh to an armature with native Blender behavior."""
    method_key = method.lower()
    if method_key not in _BIND_METHODS:
        return skill_error("Invalid bind method", f"method must be one of: {', '.join(sorted(_BIND_METHODS))}.")
    try:
        import bpy

        mesh, error = _typed_object(bpy, mesh_name, "MESH")
        if error:
            return error
        armature, error = _typed_object(bpy, armature_name, "ARMATURE")
        if error:
            return error
        modifier_name = None
        if method_key == "modifier":
            modifier = mesh.modifiers.new(name="Armature", type="ARMATURE")
            modifier.object = armature
            modifier_name = modifier.name
        else:
            _object_mode(bpy)
            bpy.ops.object.select_all(action="DESELECT")
            mesh.select_set(True)
            armature.select_set(True)
            bpy.context.view_layer.objects.active = armature
            bpy.ops.object.parent_set(type="ARMATURE_AUTO")
        return skill_success(
            f"Bound {mesh.name} to {armature.name}",
            mesh_name=mesh.name,
            armature_name=armature.name,
            method=method_key,
            modifier_name=modifier_name,
            parent=getattr(getattr(mesh, "parent", None), "name", None),
            prompt="Use pose tools or animation tools to test the resulting deformation rig.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to bind {mesh_name} to {armature_name}")


def add_shape_key(object_name: str, name: str, from_mix: bool = False) -> dict:
    """Add a shape key to a mesh object."""
    if not name or not name.strip():
        return skill_error("Invalid name", "name must be a non-empty shape key name.")
    try:
        import bpy

        obj, error = _typed_object(bpy, object_name, "MESH")
        if error:
            return error
        add = getattr(obj, "shape_key_add", None)
        if not callable(add):
            return skill_error("Shape keys unavailable", f"{object_name} does not expose shape_key_add.")
        key = add(name=name, from_mix=bool(from_mix))
        keys = getattr(getattr(getattr(obj, "data", None), "shape_keys", None), "key_blocks", [])
        return skill_success(
            f"Added shape key {key.name}",
            object_name=obj.name,
            shape_key_name=key.name,
            from_mix=bool(from_mix),
            shape_key_count=_collection_len(keys),
            prompt="Use set_driver to drive shape key values or Blender UI to sculpt the key.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to add shape key to {object_name}")


def set_driver(
    object_name: str,
    data_path: str,
    expression: str,
    variables: Sequence[Mapping[str, Any]] | None = None,
) -> dict:
    """Create or update a driver on an object data path."""
    if not data_path or not data_path.strip():
        return skill_error("Invalid data_path", "data_path must be a non-empty Blender RNA path.")
    if not expression or not expression.strip():
        return skill_error("Invalid expression", "expression must be a non-empty driver expression.")
    try:
        import bpy

        obj, error = _object_by_name(bpy, object_name)
        if error:
            return error
        fcurve = obj.driver_add(data_path)
        if isinstance(fcurve, list):
            fcurve = fcurve[0]
        driver = fcurve.driver
        driver.expression = expression
        added_variables = []
        for spec in variables or []:
            variable = driver.variables.new()
            variable.name = str(spec.get("name", "var"))
            variable.type = str(spec.get("type", "SINGLE_PROP"))
            target_spec = variable.targets[0]
            target_name = spec.get("target_object") or object_name
            target_obj, error = _object_by_name(bpy, target_name)
            if error:
                return error
            target_spec.id = target_obj
            if spec.get("target_data_path"):
                target_spec.data_path = str(spec["target_data_path"])
            if spec.get("transform_type") and hasattr(target_spec, "transform_type"):
                target_spec.transform_type = str(spec["transform_type"])
            added_variables.append(variable.name)
        return skill_success(
            f"Set driver on {object_name}.{data_path}",
            object_name=obj.name,
            data_path=data_path,
            expression=expression,
            variable_count=len(added_variables),
            variables=added_variables,
            prompt="Use get_keyframes or Blender's driver editor to inspect the driven channel.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to set driver on {object_name}.{data_path}")


def retarget_animation(
    source_armature: str,
    target_armature: str,
    mapping: Mapping[str, str] | None = None,
) -> dict:
    """Copy current pose values and action data between compatible armatures."""
    try:
        import bpy

        source, error = _typed_object(bpy, source_armature, "ARMATURE")
        if error:
            return error
        target, error = _typed_object(bpy, target_armature, "ARMATURE")
        if error:
            return error
        source_bones = _pose_bone_map(source)
        target_bones = _pose_bone_map(target)
        pairs = dict(mapping or {name: name for name in source_bones if name in target_bones})
        if not pairs:
            return skill_error("No retarget mapping", "Provide mapping or matching pose-bone names between armatures.")
        applied = []
        missing = []
        for source_name, target_name in pairs.items():
            src = source_bones.get(source_name)
            dst = target_bones.get(target_name)
            if src is None or dst is None:
                missing.append({"source": source_name, "target": target_name})
                continue
            for attr in ("matrix_basis", "location", "rotation_quaternion", "rotation_euler", "scale"):
                if hasattr(src, attr) and hasattr(dst, attr):
                    try:
                        setattr(dst, attr, getattr(src, attr).copy())
                    except Exception:
                        try:
                            setattr(dst, attr, getattr(src, attr))
                        except Exception:
                            pass
            applied.append({"source": source_name, "target": target_name})

        action_copied = False
        source_action = getattr(getattr(source, "animation_data", None), "action", None)
        if source_action is not None:
            action = source_action.copy()
            if hasattr(action, "name"):
                action.name = f"{source_action.name}_retarget_{target.name}"
            animation_data_create = getattr(target, "animation_data_create", None)
            target_anim = (
                animation_data_create() if callable(animation_data_create) else getattr(target, "animation_data", None)
            )
            if target_anim is not None:
                target_anim.action = action
                action_copied = True
        return skill_success(
            f"Retargeted {len(applied)} bone mapping(s)",
            source_armature=source.name,
            target_armature=target.name,
            applied_mappings=applied,
            missing_mappings=missing,
            action_copied=action_copied,
            prompt="Use bake_animation to bake the target armature after retargeting if needed.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to retarget {source_armature} to {target_armature}")
