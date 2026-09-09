"""Blender-only isolated worker. Imports no adapter or native Core extension."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _multiview_receipt import png_evidence, read_receipt, write_receipt  # noqa: E402


def prepare_wire(scene, radius, max_source_edges=100000):
    import bpy

    surface = bpy.data.materials.new("DCC Wire Surface")
    surface.diffuse_color = (0.35, 0.38, 0.42, 1)
    line = bpy.data.materials.new("DCC Source Mesh Edges")
    line.diffuse_color = (0.008, 0.008, 0.008, 1)
    for material in (surface, line):
        material.use_nodes = True
        shader = material.node_tree.nodes.get("Principled BSDF")
        shader.inputs["Base Color"].default_value = material.diffuse_color
        shader.inputs["Roughness"].default_value = 1
    objects = list(scene.objects)
    edge_count = sum(len(obj.data.edges) for obj in objects if obj.type == "MESH" and not obj.hide_render)
    if type(max_source_edges) is not int or not 1 <= max_source_edges <= 500000 or edge_count > max_source_edges:
        raise ValueError("Wire pass exceeds its bounded source edge budget")
    for obj in objects:
        if obj.type != "MESH":
            if obj.type != "CAMERA":
                obj.hide_render = True
            continue
        if obj.hide_render:
            continue
        for modifier in obj.modifiers:
            modifier.show_render = False
            modifier.show_viewport = False
        obj.data = obj.data.copy()
        if obj.data.shape_keys is not None:
            obj.shape_key_clear()
        obj.instance_type = "NONE"
        obj.data.materials.clear()
        obj.data.materials.append(surface)
        for polygon in obj.data.polygons:
            polygon.material_index = 0
        curve = bpy.data.curves.new("DCC Source Edges", "CURVE")
        curve.dimensions = "3D"
        curve.bevel_depth = radius
        curve.bevel_resolution = 0
        curve.resolution_u = 1
        curve.materials.append(line)
        for edge in obj.data.edges:
            spline = curve.splines.new("POLY")
            spline.points.add(1)
            for point, vertex_index in zip(spline.points, edge.vertices):
                point.co = (*obj.data.vertices[vertex_index].co, 1)
        overlay = bpy.data.objects.new("DCC Source Edges", curve)
        for collection in obj.users_collection:
            collection.objects.link(overlay)
        overlay.matrix_world = obj.matrix_world.copy()
    # CPU ray tracing avoids requiring an OpenGL context on headless workers.
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 64
    scene.cycles.use_denoising = True
    scene.world = bpy.data.worlds.new("DCC Wire World")
    scene.world.color = (0.15, 0.15, 0.15)
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    if background is not None:
        background.inputs["Color"].default_value = (0.6, 0.6, 0.6, 1)
        background.inputs["Strength"].default_value = 1
    return edge_count


def run(directory):
    import bpy

    directory = Path(directory)
    request = json.loads((directory / "request.json").read_text(encoding="utf-8"))
    result = read_receipt(directory, request["job_id"])
    for index, item in enumerate(result["items"]):
        if (directory / "cancel").exists():
            result["status"] = "cancelled"
            for pending in result["items"]:
                if pending["status"] == "pending":
                    pending["status"] = "cancelled"
            write_receipt(directory, result)
            return
        item["status"] = "running"
        write_receipt(directory, result)
        try:
            bpy.ops.wm.open_mainfile(filepath=str(directory / "scene.blend"), load_ui=False, use_scripts=False)
            scene = bpy.context.scene
            camera = scene.objects.get(item["camera"])
            if camera is None or camera.type != "CAMERA":
                raise ValueError("Camera missing in the saved scene")
            scene.camera = camera
            if item["pass"] == "wire":
                item["source_edge_count"] = prepare_wire(
                    scene, request["wire_radius"], request.get("max_source_edges", 100000)
                )
            if scene.render.engine == "CYCLES":
                scene.cycles.device = "CPU"
            scene.render.resolution_x = request["resolution_x"]
            scene.render.resolution_y = request["resolution_y"]
            scene.render.resolution_percentage = 100
            scene.render.image_settings.file_format = "PNG"
            scene.render.image_settings.color_mode = "RGBA"
            scene.render.image_settings.color_depth = "8"
            # A compositor File Output node must not write outside the job directory.
            scene.render.use_compositing = False
            scene.render.use_sequencer = False
            scene.render.use_border = False
            scene.render.use_multiview = False
            scene.render.film_transparent = False
            path = directory / "{:02d}_{}.png".format(index, item["pass"])
            scene.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
            image = bpy.data.images.load(str(path), check_existing=False)
            try:
                if tuple(image.size) != (request["resolution_x"], request["resolution_y"]) or not image.has_data:
                    raise ValueError("Rendered PNG failed decode/dimension verification")
                # Force pixel decoding, rather than accepting a filename or header.
                if len(image.pixels) != image.size[0] * image.size[1] * 4:
                    raise ValueError("Rendered image pixel data is incomplete")
            finally:
                bpy.data.images.remove(image)
            item["image"] = png_evidence(path)
            item["path"] = str(path)
            item["status"] = "completed"
        except Exception as exc:
            item["status"] = "failed"
            item["error"] = str(exc)
        write_receipt(directory, result)
    result["status"] = "completed" if all(item["status"] == "completed" for item in result["items"]) else "failed"
    write_receipt(directory, result)


if __name__ == "__main__":
    run(sys.argv[sys.argv.index("--") + 1])
