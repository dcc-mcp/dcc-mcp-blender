"""Export the current Blender scene to OBJ."""

from __future__ import annotations

from pathlib import Path

from dcc_mcp_core.skill import skill_entry, skill_error, skill_exception, skill_success


def _has_nonempty_file(path: str) -> bool:
    target = Path(path)
    return target.is_file() and target.stat().st_size > 0


def _call_blender_exporter(bpy, path: str) -> None:
    wm_export = getattr(bpy.ops.wm, "obj_export", None)
    if callable(wm_export):
        wm_export(filepath=path)
        if _has_nonempty_file(path):
            return

    scene_export = getattr(getattr(bpy.ops, "export_scene", None), "obj", None)
    if callable(scene_export):
        scene_export(filepath=path)
        if _has_nonempty_file(path):
            return

    raise RuntimeError("No OBJ export operator is available")


def _iter_mesh_objects(bpy):
    for obj in getattr(getattr(bpy, "data", None), "objects", []):
        if getattr(obj, "type", None) == "MESH" and getattr(obj, "data", None) is not None:
            yield obj


def _coordinate(obj, vertex):
    co = getattr(vertex, "co", vertex)
    matrix = getattr(obj, "matrix_world", None)
    if matrix is not None:
        try:
            co = matrix @ co
        except Exception:
            pass
    return (float(co[0]), float(co[1]), float(co[2]))


def _write_basic_obj(bpy, path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    vertex_offset = 1
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Exported by dcc-mcp-blender\n")
        for obj in _iter_mesh_objects(bpy):
            mesh = obj.data
            vertices = list(getattr(mesh, "vertices", []))
            polygons = list(getattr(mesh, "polygons", []))
            handle.write(f"o {getattr(obj, 'name', 'Object')}\n")
            for vertex in vertices:
                x, y, z = _coordinate(obj, vertex)
                handle.write(f"v {x:.9g} {y:.9g} {z:.9g}\n")
            for polygon in polygons:
                indices = [str(vertex_offset + int(index)) for index in getattr(polygon, "vertices", [])]
                if len(indices) >= 3:
                    handle.write(f"f {' '.join(indices)}\n")
            vertex_offset += len(vertices)


def export_obj(path: str) -> dict:
    """Export OBJ using Blender 3.x/4.x compatible operators."""
    try:
        import bpy

        try:
            _call_blender_exporter(bpy, path)
        except Exception:
            _write_basic_obj(bpy, path)
        return skill_success(f"Exported OBJ: {path}", filepath=path, prompt="OBJ exported.")
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to export OBJ: {path}")


@skill_entry
def main(**kwargs) -> dict:
    """Entry point; delegates to :func:`export_obj`."""
    return export_obj(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
