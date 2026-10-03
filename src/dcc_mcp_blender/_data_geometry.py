"""Bounded data-first native geometry creation without code evaluation or file IO."""

from __future__ import annotations

import hashlib
import json
import math
import re
import struct

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success
from dcc_mcp_core.skills_helper import check_dcc_cancelled

MAX_POINTS = 30000
MAX_FACES = 50000
MAX_INDICES = 200000
MAX_ARGUMENT_BYTES = 2_000_000


def _number(value, low=-1_000_000.0, high=1_000_000.0):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError("Expected a finite bounded number (booleans are not numbers)")
    return float(value)


def _name(value):
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,62}", value) is None:
        raise ValueError("Use 1–63 letters, digits, underscore, dot or hyphen, starting with a letter")
    return value


def _budget(value):
    try:
        encoded = json.dumps(value, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError("Geometry arguments must be finite JSON data") from exc
    if len(encoded.encode("utf-8")) > MAX_ARGUMENT_BYTES:
        raise ValueError("Geometry arguments exceed the 2 MB payload budget")


def _points(values, minimum=1):
    if not isinstance(values, list) or not minimum <= len(values) <= MAX_POINTS:
        raise ValueError("Point count is out of bounds")
    result = []
    for point in values:
        if not isinstance(point, list) or len(point) != 3:
            raise ValueError("Every point must contain exactly XYZ")
        result.append(tuple(_number(value) for value in point))
    return result


def _point_digest(points):
    return hashlib.sha256(b"".join(struct.pack("<fff", *point) for point in points)).hexdigest()


def validate_mesh_data(name, vertices, faces):
    _name(name)
    _budget([name, vertices, faces])
    points = _points(vertices, 3)
    if not isinstance(faces, list) or not 1 <= len(faces) <= MAX_FACES:
        raise ValueError("Face count is out of bounds")
    index_count = 0
    clean_faces = []
    for face in faces:
        if not isinstance(face, list) or not 3 <= len(face) <= 128:
            raise ValueError("Each face must contain 3–128 vertex indices")
        if any(type(index) is not int or not 0 <= index < len(points) for index in face):
            raise ValueError("Face indices must address the supplied vertices")
        if len(set(face)) != len(face):
            raise ValueError("A face cannot repeat a vertex index")
        index_count += len(face)
        if index_count > MAX_INDICES:
            raise ValueError("Total face-index count exceeds the bound")
        clean_faces.append(tuple(face))
    return points, clean_faces


def validate_curve_data(name, splines, closed, dimensions, extrude, bevel_depth, bevel_resolution):
    _name(name)
    _budget([name, splines, closed, dimensions, extrude, bevel_depth, bevel_resolution])
    if type(closed) is not bool or dimensions not in ("2D", "3D"):
        raise ValueError("Closed must be boolean and dimensions must be 2D or 3D")
    if not isinstance(splines, list) or not 1 <= len(splines) <= 1024:
        raise ValueError("Spline count is out of bounds")
    groups = [_points(group, 3 if closed else 2) for group in splines]
    if sum(map(len, groups)) > MAX_POINTS:
        raise ValueError("Total control-point count exceeds the bound")
    if dimensions == "2D" and any(abs(p[2]) > 1e-9 for group in groups for p in group):
        raise ValueError("2D spline input must lie in its local XY plane; position the object afterward")
    _number(extrude, 0, 1000)
    _number(bevel_depth, 0, 1000)
    if type(bevel_resolution) is not int or not 0 <= bevel_resolution <= 4:
        raise ValueError("Bevel resolution must be an integer from 0 to 4")
    return groups


def _cleanup_owned(bpy, obj, data, collection):
    if obj is not None and bpy.data.objects.get(obj.name) is obj:
        bpy.data.objects.remove(obj, do_unlink=True)
    if data is not None and data.users == 0 and collection.get(data.name) is data:
        collection.remove(data)


def create_mesh_from_data(name, vertices, faces):
    """Create one named native mesh; preserve selection and reject an existing name."""
    obj = data = None
    try:
        points, polygons = validate_mesh_data(name, vertices, faces)
        import bpy

        if bpy.data.objects.get(name) is not None or bpy.data.meshes.get(name) is not None:
            return skill_error("Name already exists", "Choose a new object/data name; nothing was changed")
        check_dcc_cancelled()
        data = bpy.data.meshes.new(name)
        data.from_pydata(points, [], polygons)
        if data.validate(verbose=False):
            raise ValueError("Blender had to repair the supplied topology; no object was retained")
        data.update()
        actual_points = [tuple(v.co) for v in data.vertices]
        actual_faces = [tuple(p.vertices) for p in data.polygons]
        if _point_digest(points) != _point_digest(actual_points) or polygons != actual_faces:
            raise RuntimeError("Native geometry readback differs from the supplied buffers")
        check_dcc_cancelled()
        obj = bpy.data.objects.new(name, data)
        bpy.context.scene.collection.objects.link(obj)
        bpy.context.view_layer.update()
        return skill_success(
            "Native mesh created and read back",
            object_name=obj.name,
            vertex_count=len(data.vertices),
            edge_count=len(data.edges),
            face_count=len(data.polygons),
            position_float32_sha256=_point_digest(actual_points),
            topology_sha256=hashlib.sha256(json.dumps(actual_faces, separators=(",", ":")).encode()).hexdigest(),
            dimensions_local=list(obj.dimensions),
            selection_preserved=True,
            not_claimed=["manifoldness", "engineering validity", "UVs", "material assignment"],
        )
    except Exception as exc:
        try:
            if data is not None:
                _cleanup_owned(bpy, obj, data, bpy.data.meshes)
        except Exception:
            return skill_exception(exc, message="Mesh creation failed; cleanup requires inspection")
        return skill_exception(exc, message="Mesh creation rejected; no existing object was changed")


def create_curve_from_points(
    name, splines, closed=True, dimensions="2D", extrude=0.0, bevel_depth=0.0, bevel_resolution=0, material_name=None
):
    """Create native editable POLY splines; extrude is Blender's per-side depth."""
    obj = data = None
    try:
        groups = validate_curve_data(name, splines, closed, dimensions, extrude, bevel_depth, bevel_resolution)
        if material_name is not None:
            _name(material_name)
        import bpy

        if bpy.data.objects.get(name) is not None or bpy.data.curves.get(name) is not None:
            return skill_error("Name already exists", "Choose a new object/data name; nothing was changed")
        check_dcc_cancelled()
        material = bpy.data.materials.get(material_name) if material_name is not None else None
        if material_name is not None and material is None:
            return skill_error("Material does not exist", "Create the material with typed tools first")
        data = bpy.data.curves.new(name, type="CURVE")
        if material is not None:
            data.materials.append(material)
        data.dimensions = dimensions
        data.fill_mode = "BOTH" if dimensions == "2D" else "FULL"
        data.resolution_u = 1
        data.extrude = float(extrude)
        data.bevel_depth = float(bevel_depth)
        data.bevel_resolution = bevel_resolution
        for group in groups:
            spline = data.splines.new("POLY")
            spline.points.add(len(group) - 1)
            for point, xyz in zip(spline.points, group):
                point.co = (*xyz, 1.0)
            spline.use_cyclic_u = closed
        actual = [[tuple(p.co[:3]) for p in spline.points] for spline in data.splines]
        if len(actual) != len(groups) or any(_point_digest(a) != _point_digest(b) for a, b in zip(groups, actual)):
            raise RuntimeError("Native spline readback differs from the supplied buffers")
        check_dcc_cancelled()
        obj = bpy.data.objects.new(name, data)
        bpy.context.scene.collection.objects.link(obj)
        bpy.context.view_layer.update()
        return skill_success(
            "Native poly curve created and read back",
            object_name=obj.name,
            spline_count=len(data.splines),
            control_point_count=sum(map(len, actual)),
            position_float32_sha256=_point_digest([p for group in actual for p in group]),
            material_name=data.materials[0].name if data.materials else None,
            closed=closed,
            dimensions=dimensions,
            extrude_per_side=float(data.extrude),
            bevel_depth=float(data.bevel_depth),
            bevel_resolution=data.bevel_resolution,
            selection_preserved=True,
            not_claimed=["nonintersecting fill", "engineering validity", "UVs"],
        )
    except Exception as exc:
        try:
            if data is not None:
                _cleanup_owned(bpy, obj, data, bpy.data.curves)
        except Exception:
            return skill_exception(exc, message="Curve creation failed; cleanup requires inspection")
        return skill_exception(exc, message="Curve creation rejected; no existing object was changed")


def inspect_data_geometry(name):
    """Read bounded native geometry fingerprints, including after file reopen."""
    try:
        _name(name)
        import bpy

        obj = bpy.data.objects.get(name)
        if obj is None or obj.type not in ("MESH", "CURVE"):
            return skill_error("Geometry not found", "Select an existing mesh or poly curve name")
        data = obj.data
        result = {
            "object_name": obj.name,
            "type": obj.type,
            "location": list(obj.location),
            "matrix_world": [[_number(float(value)) for value in row] for row in obj.matrix_world],
            "matrix_parent_inverse": [[_number(float(value)) for value in row] for row in obj.matrix_parent_inverse],
            "parent": obj.parent.name if obj.parent is not None else None,
            "dimensions_local": list(obj.dimensions),
            "materials": [m.name if m is not None else None for m in data.materials],
        }
        if obj.type == "MESH":
            if len(data.vertices) > MAX_POINTS or len(data.polygons) > MAX_FACES or len(data.loops) > MAX_INDICES:
                raise ValueError("Geometry exceeds bounded inspection limits")
            points = [tuple(v.co) for v in data.vertices]
            faces = [tuple(p.vertices) for p in data.polygons]
            result.update(
                vertex_count=len(points),
                edge_count=len(data.edges),
                face_count=len(faces),
                position_float32_sha256=_point_digest(points),
                topology_sha256=hashlib.sha256(json.dumps(faces, separators=(",", ":")).encode()).hexdigest(),
            )
        else:
            if len(data.splines) > 1024 or any(s.type != "POLY" for s in data.splines):
                raise ValueError("Inspect only bounded POLY splines")
            if sum(len(s.points) for s in data.splines) > MAX_POINTS:
                raise ValueError("Geometry exceeds bounded inspection limits")
            points = [tuple(p.co[:3]) for s in data.splines for p in s.points]
            result.update(
                spline_count=len(data.splines),
                control_point_count=len(points),
                position_float32_sha256=_point_digest(points),
                cyclic=[s.use_cyclic_u for s in data.splines],
                dimensions=data.dimensions,
                extrude_per_side=float(data.extrude),
                bevel_depth=float(data.bevel_depth),
            )
        return skill_success("Native geometry inspected", **result)
    except Exception as exc:
        return skill_exception(exc, message="Geometry inspection failed without mutation")
