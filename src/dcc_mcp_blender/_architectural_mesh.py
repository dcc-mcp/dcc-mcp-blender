"""Bounded, context-independent solid pointed-arch construction."""

from __future__ import annotations

import math

from dcc_mcp_core.skill import skill_error, skill_success


def pointed_arch_geometry(width, spring_height, rise, frame_width, depth, segments):
    """Return an open-bottom U frame, closed at both feet, in local X/Z.

    Each half is a scaled circular arc with a pointed crown. Frame width
    specifies the horizontal jamb thickness and vertical crown thickness;
    it is not a constant normal offset along the curved head.
    """
    for value in (width, spring_height, rise, frame_width, depth):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError("All dimensions must be finite positive numbers")
    if isinstance(segments, bool) or not isinstance(segments, int) or not 2 <= segments <= 128:
        raise ValueError("segments must be an integer from 2 to 128 per half arch")

    def profile(w, r):
        points = [(-w / 2, 0), (-w / 2, spring_height)]
        for i in range(1, segments + 1):
            theta = math.pi * i / (3 * segments)
            points.append((w / 2 - w * math.cos(theta), spring_height + r * math.sin(theta) / math.sin(math.pi / 3)))
        points[-1] = (0, spring_height + r)
        points.extend([(-x, z) for x, z in reversed(points[:-1])])
        return points

    inner = profile(width, rise)
    outer = profile(width + 2 * frame_width, rise + frame_width)
    vertices = []
    for (ix, iz), (ox, oz) in zip(inner, outer):
        vertices.extend(((ix, 0, iz), (ox, 0, oz), (ox, depth, oz), (ix, depth, iz)))
    faces = []
    for i in range(len(inner) - 1):
        for j in range(4):
            faces.append((4 * i + j, 4 * i + (j + 1) % 4, 4 * (i + 1) + (j + 1) % 4, 4 * (i + 1) + j))
    faces.extend(((3, 2, 1, 0), tuple(4 * (len(inner) - 1) + j for j in range(4))))
    return vertices, [tuple(reversed(face)) for face in faces]


def create_pointed_arch(name, width, spring_height, rise, frame_width, depth, segments=16, location=(0, 0, 0)):
    """Create a closed mesh without operators or selection changes."""
    try:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("name must be a nonempty string")
        if not isinstance(location, (list, tuple)) or len(location) != 3:
            raise ValueError("location must contain three finite numbers")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in location):
            raise ValueError("location must contain three finite numbers")
        vertices, faces = pointed_arch_geometry(width, spring_height, rise, frame_width, depth, segments)
    except (ValueError, TypeError) as exc:
        return skill_error(str(exc), "Use positive dimensions and a bounded segment count.", mutation_applied=False)

    import bpy

    if bpy.data.objects.get(name) is not None:
        return skill_error("Object name already exists", "Choose an unused object name.", mutation_applied=False)
    mesh = None
    obj = None
    try:
        mesh = bpy.data.meshes.new(name + "Mesh")
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        if len(mesh.vertices) != len(vertices) or len(mesh.polygons) != len(faces):
            raise RuntimeError("Created mesh counts do not match the requested solid")
        bounds = [[min(v.co[axis] for v in mesh.vertices), max(v.co[axis] for v in mesh.vertices)] for axis in range(3)]
        if any(not math.isfinite(value) for pair in bounds for value in pair):
            raise RuntimeError("Dimensions exceed Blender's finite coordinate range")
        edge_uses = {}
        for polygon in mesh.polygons:
            indices = list(polygon.vertices)
            for a, b in zip(indices, indices[1:] + indices[:1]):
                key = tuple(sorted((a, b)))
                edge_uses[key] = edge_uses.get(key, 0) + 1
        if any(count != 2 for count in edge_uses.values()) or any(
            not math.isfinite(p.area) or p.area <= 0 for p in mesh.polygons
        ):
            raise RuntimeError("Created mesh is degenerate or not a closed two-manifold")
        obj = bpy.data.objects.new(name, mesh)
        obj.location = location
        bpy.context.scene.collection.objects.link(obj)
        if any(not math.isfinite(value) for value in obj.location):
            raise RuntimeError("Location exceeds Blender's finite coordinate range")
        return skill_success(
            "Created solid pointed arch",
            object_name=obj.name,
            location=list(obj.location),
            vertex_count=len(mesh.vertices),
            face_count=len(mesh.polygons),
            local_dimensions=[hi - lo for lo, hi in bounds],
            local_bounds=bounds,
            world_bounds=[[lo + obj.location[i], hi + obj.location[i]] for i, (lo, hi) in enumerate(bounds)],
            closed_two_manifold=True,
            opening_dimensions=[width, spring_height + rise],
            depth_axis="+Y",
            mutation_applied=True,
        )
    except Exception as exc:
        cleanup_errors = []
        if obj is not None:
            try:
                bpy.data.objects.remove(obj, do_unlink=True)
            except Exception as cleanup_exc:
                cleanup_errors.append(str(cleanup_exc))
        if mesh is not None:
            try:
                bpy.data.meshes.remove(mesh)
            except Exception as cleanup_exc:
                cleanup_errors.append(str(cleanup_exc))
        return skill_error(
            "Arch creation failed: " + str(exc),
            "Inspect the scene before retrying if rollback failed.",
            mutation_applied=mesh is not None,
            rollback_attempted=mesh is not None,
            rollback_verified=not cleanup_errors,
            cleanup_errors=cleanup_errors,
        )
