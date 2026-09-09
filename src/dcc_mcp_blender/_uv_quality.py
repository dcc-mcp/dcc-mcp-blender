"""Bounded, read-only source-mesh UV inspection and SVG delivery.

No selection, mode, active-map, or coordinate writes. Mesh tessellation only
refreshes Blender's derived triangle cache. Edit-mode data is rejected rather
than implicitly flushing it or auditing a stale object-mode copy.
"""

from __future__ import annotations

import math
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree
from xml.sax.saxutils import escape

from dcc_mcp_core.skill import skill_exception, skill_success


def _integer(value, label, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("{} must be an integer in [{}, {}]".format(label, low, high))


def _objects(object_names, uv_map, max_triangles, triangle_limit=200000):
    import bpy

    if not isinstance(object_names, list) or not 1 <= len(object_names) <= 4096:
        raise ValueError("object_names must contain 1 to 4096 unique mesh names")
    if any(not isinstance(n, str) or not n.strip() for n in object_names):
        raise ValueError("object_names must contain non-empty strings")
    if len(set(object_names)) != len(object_names):
        raise ValueError("object_names must be unique")
    if uv_map is not None and (not isinstance(uv_map, str) or not uv_map.strip()):
        raise ValueError("uv_map must be null (active per object) or a non-empty name")
    _integer(max_triangles, "max_triangles", 1, triangle_limit)
    objects = []
    for name in object_names:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            raise ValueError("Mesh object not found: {}".format(name))
        if obj.mode != "OBJECT":
            raise ValueError("Object must be in OBJECT mode: {}".format(name))
        objects.append(obj)
    return objects


def _cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _area(points):
    if len(points) < 3:
        return 0.0
    origin = points[0]
    return abs(sum(_cross(origin, points[i], points[i + 1]) for i in range(1, len(points) - 1))) * 0.5


def _intersection_area(first, second):
    """Convex clipping; positive area excludes edge/point-only contact."""
    clip = second if _cross(*second) > 0 else tuple(reversed(second))
    polygon = list(first)
    for a, b in zip(clip, clip[1:] + clip[:1]):
        if not polygon:
            return 0.0
        output = []
        previous = polygon[-1]
        previous_side = _cross(a, b, previous)
        for point in polygon:
            side = _cross(a, b, point)
            if (side >= 0) != (previous_side >= 0):
                ratio = previous_side / (previous_side - side)
                output.append(tuple(previous[i] + ratio * (point[i] - previous[i]) for i in range(2)))
            if side >= 0:
                output.append(point)
            previous, previous_side = point, side
        polygon = output
    return _area(polygon)


def _extract(obj, uv_map, remaining):
    mesh = obj.data
    layer = mesh.uv_layers.get(uv_map) if uv_map else mesh.uv_layers.active
    row = {
        "object_name": obj.name,
        "uv_map": layer.name if layer else None,
        "polygon_count": len(mesh.polygons),
        "complete": True,
        "issues": {},
    }
    if layer is None:
        row["issues"]["missing_uv_map"] = 1
        return row, [], 0
    # Conservative O(1) bound: sum(n - 2) for valid mesh polygons.
    estimate = max(0, len(mesh.loops) - 2 * len(mesh.polygons))
    if estimate > remaining:
        row.update(complete=False, incomplete_reason="triangle_budget", estimated_triangles=estimate)
        return row, [], 0
    mesh.calc_loop_triangles()
    if len(mesh.loop_triangles) > remaining:
        row.update(complete=False, incomplete_reason="triangle_budget")
        return row, [], 0
    triangles = []
    missing_faces = set()
    for tri in mesh.loop_triangles:
        if any(i >= len(layer.data) for i in tri.loops):
            missing_faces.add(tri.polygon_index)
            continue
        points = tuple(tuple(float(c) for c in layer.data[i].uv) for i in tri.loops)
        triangles.append((tri.polygon_index, points))
    if missing_faces:
        row["issues"]["uncovered_faces"] = len(missing_faces)
    if not mesh.polygons:
        row["issues"]["empty_mesh"] = 1
    return row, triangles, len(mesh.loop_triangles)


def audit_uv_layout(
    object_names,
    uv_map=None,
    tile_policy="unit",
    check_overlap=True,
    overlap_scope="per_object",
    allow_stacked=False,
    max_triangles=50000,
    max_pair_tests=200000,
    max_report_items=100,
    area_epsilon=1e-10,
):
    """Audit requested source meshes; budgets never produce a false pass.

    Overlap counts are triangle pairs (including folded triangles of one face).
    allow_stacked permits exact coincident triangles, including reversed winding,
    not arbitrary partial overlap. UDIM means U in [0,10], V >= 0; it does not
    assert that a face stays inside a single tile. Epsilon is in UV area units.
    """
    try:
        _integer(max_pair_tests, "max_pair_tests", 1, 2000000)
        _integer(max_report_items, "max_report_items", 0, 1000)
        if any(type(v) is not bool for v in (check_overlap, allow_stacked)):
            raise ValueError("check_overlap and allow_stacked must be booleans")
        if tile_policy not in ("unit", "udim", "unrestricted") or overlap_scope not in ("per_object", "selection"):
            raise ValueError("Invalid tile_policy or overlap_scope")
        if isinstance(area_epsilon, bool) or not isinstance(area_epsilon, (int, float)):
            raise ValueError("area_epsilon must be a finite positive number")
        if not math.isfinite(area_epsilon) or not 0 < area_epsilon <= 0.0001:
            raise ValueError("area_epsilon must be in (0, 0.0001]")
        objects = _objects(object_names, uv_map, max_triangles)
        rows, details, valid = [], [], []
        consumed, pair_tests, stacked = 0, 0, 0

        def issue(index, kind, face=None, other=None):
            counts = rows[index]["issues"]
            counts[kind] = counts.get(kind, 0) + 1
            if len(details) < max_report_items:
                details.append(
                    {"object_name": rows[index]["object_name"], "kind": kind, "face_index": face, "other": other}
                )

        for obj in objects:
            row, triangles, used = _extract(obj, uv_map, max_triangles - consumed)
            index = len(rows)
            rows.append(row)
            consumed += used
            row["triangles_checked"] = used
            for face, points in triangles:
                # Limit coordinates to keep all cross products finite in double precision.
                if any(not math.isfinite(c) or abs(c) > 1e12 for p in points for c in p):
                    issue(index, "invalid_coordinates", face)
                    continue
                if _area(points) <= area_epsilon:
                    issue(index, "degenerate_triangles", face)
                    continue
                if tile_policy == "unit" and any(not 0 <= c <= 1 for p in points for c in p):
                    issue(index, "out_of_tile_triangles", face)
                elif tile_policy == "udim" and any(not 0 <= p[0] <= 10 or p[1] < 0 for p in points):
                    issue(index, "out_of_tile_triangles", face)
                if check_overlap:
                    xs, ys = zip(*points)
                    valid.append((index, face, points, (min(xs), max(xs), min(ys), max(ys))))
        overlap_complete = True
        groups = {}
        for tri in valid:
            groups.setdefault(tri[0] if overlap_scope == "per_object" else 0, []).append(tri)
        for group in groups.values():
            group.sort(key=lambda t: t[3][0])
            for i, first in enumerate(group):
                for j in range(i + 1, len(group)):
                    second = group[j]
                    if second[3][0] >= first[3][1]:
                        break
                    if pair_tests >= max_pair_tests:
                        overlap_complete = False
                        break
                    pair_tests += 1
                    if second[3][2] >= first[3][3] or second[3][3] <= first[3][2]:
                        continue
                    if _intersection_area(first[2], second[2]) > area_epsilon:
                        if allow_stacked and sorted(first[2]) == sorted(second[2]):
                            stacked += 1
                        else:
                            issue(
                                first[0],
                                "overlap_pairs",
                                first[1],
                                {"object_name": rows[second[0]]["object_name"], "face_index": second[1]},
                            )
                if not overlap_complete:
                    break
            if not overlap_complete:
                break
        counts = Counter()
        if not overlap_complete:
            # Conservatively mark every overlap participant incomplete; do not
            # suggest an object passed based only on its coordinate extraction.
            for index in {tri[0] for tri in valid}:
                rows[index]["complete"] = False
                rows[index]["incomplete_reason"] = "overlap_budget"
        for row in rows:
            counts.update(row["issues"])
        complete = overlap_complete and all(row["complete"] for row in rows)
        return skill_success(
            "UV audit {}".format("incomplete" if not complete else "finished"),
            complete=complete,
            passed=complete and not counts,
            mutation_applied=False,
            topology="source_mesh",
            objects=rows,
            issue_counts=dict(counts),
            details=details,
            details_truncated=sum(counts.values()) > len(details),
            triangles_checked=consumed,
            pair_tests=pair_tests,
            overlap_complete=overlap_complete,
            allowed_stacked_pairs=stacked,
            checks={
                "coordinates": True,
                "degeneracy": True,
                "tile_policy": tile_policy,
                "overlap": check_overlap,
                "overlap_scope": overlap_scope,
                "allow_stacked": allow_stacked,
            },
            area_epsilon=area_epsilon,
        )
    except Exception as exc:
        return skill_exception(exc, message="UV audit failed")


def export_uv_layout(
    object_names, output_path, uv_map=None, resolution=2048, max_triangles=50000, layout_mode="panels"
):
    """Export polygon UV edges to a new SVG as object panels or a shared atlas."""
    try:
        _integer(resolution, "resolution", 256, 8192)
        objects = _objects(object_names, uv_map, max_triangles, triangle_limit=500000)
        if layout_mode not in ("panels", "overlay"):
            raise ValueError("layout_mode must be panels or overlay")
        if layout_mode == "panels" and len(objects) > 64:
            raise ValueError("Panel export supports at most 64 objects; use overlay for a shared atlas")
        if not isinstance(output_path, str) or not output_path:
            raise ValueError("output_path must be a non-empty absolute SVG path")
        path = Path(output_path)
        if not path.is_absolute() or path.suffix.lower() != ".svg":
            raise ValueError("output_path must be an absolute .svg path")
        if path.exists():
            raise ValueError("Output already exists; choose a new path")
        panels, consumed = [], 0
        for obj in objects:
            row, triangles, used = _extract(obj, uv_map, max_triangles - consumed)
            if not row["complete"] or row["issues"]:
                raise ValueError("Cannot export {}: {}".format(obj.name, row))
            consumed += used
            coords = [p for _, triangle in triangles for p in triangle]
            if any(not math.isfinite(c) or abs(c) > 1e12 for p in coords for c in p):
                raise ValueError("Invalid UV coordinates on {}".format(obj.name))
            layer = obj.data.uv_layers.get(uv_map) if uv_map else obj.data.uv_layers.active
            # Polygon edges, not tessellation diagonals or an artistic wire texture.
            edges = set()
            for poly in obj.data.polygons:
                points = [tuple(float(c) for c in layer.data[i].uv) for i in poly.loop_indices]
                for a, b in zip(points, points[1:] + points[:1]):
                    edges.add(tuple(sorted((a, b))))
            panels.append((obj.name, layer.name, coords, sorted(edges)))
        if layout_mode == "overlay":
            coords = [point for panel in panels for point in panel[2]]
            edges = sorted({edge for panel in panels for edge in panel[3]})
            panels = [("Shared UV space ({} objects)".format(len(objects)), uv_map or "active maps", coords, edges)]
        columns = math.ceil(math.sqrt(len(panels)))
        rows = math.ceil(len(panels) / columns)
        size = resolution / columns
        height = math.ceil(rows * size)
        parts = [
            '<svg xmlns="http://www.w3.org/2000/svg" width="{}" height="{}" viewBox="0 0 {} {}">'.format(
                resolution, height, resolution, height
            ),
            '<rect width="100%" height="100%" fill="#151d24"/>',
        ]
        for index, (name, layer, coords, edges) in enumerate(panels):
            x = (index % columns) * size
            y = (index // columns) * size
            pad = size * 0.07
            xs, ys = zip(*coords)
            lo_u, hi_u = min(0.0, min(xs)), max(1.0, max(xs))
            lo_v, hi_v = min(0.0, min(ys)), max(1.0, max(ys))
            scale = (size - 3 * pad) / max(hi_u - lo_u, hi_v - lo_v)

            def xy(p):
                return x + pad + (p[0] - lo_u) * scale, y + size - pad - (p[1] - lo_v) * scale

            tx, ty = xy((0, 1))
            parts.append(
                '<rect x="{:.5f}" y="{:.5f}" width="{:.5f}" height="{:.5f}" fill="none" stroke="#52606a"/>'.format(
                    tx, ty, scale, scale
                )
            )
            parts.append(
                '<text x="{}" y="{}" fill="#e1e8ec" font-family="sans-serif" font-size="{}">{}</text>'.format(
                    x + pad, y + pad, size * 0.025, escape("{} | {}".format(name, layer))
                )
            )
            commands = []
            for a, b in edges:
                ax, ay = xy(a)
                bx, by = xy(b)
                commands.append("M{:.5f},{:.5f}L{:.5f},{:.5f}".format(ax, ay, bx, by))
            parts.append(
                '<path d="{}" fill="none" stroke="#71d6e4" stroke-width="{}"/>'.format(
                    " ".join(commands), max(0.25, size / 1400)
                )
            )
        parts.append("</svg>")
        content = "\n".join(parts)
        ElementTree.fromstring(content)  # Reject invalid XML characters before creating the file.
        # Exclusive creation never replaces a previous delivery, including a race.
        with path.open("x", encoding="utf-8") as stream:
            stream.write(content)
        return skill_success(
            "UV SVG exported",
            output_path=str(path),
            format="SVG",
            width=resolution,
            height=height,
            object_count=len(objects),
            panel_count=len(panels),
            layout_mode=layout_mode,
            edge_count=sum(len(p[3]) for p in panels),
            triangles_read=consumed,
            mutation_applied=False,
            topology="source_polygon_uv_edges",
        )
    except Exception as exc:
        return skill_exception(exc, message="UV SVG export failed")
