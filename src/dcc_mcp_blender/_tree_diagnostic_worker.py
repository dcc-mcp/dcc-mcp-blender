"""Blender-owned tree preview worker, derived from dcc-mcp-speedtree PR #17."""

import hashlib
import json
import math
import shlex
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector


def _hash_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _obj_material_libraries(obj_path):
    """Parse every mtllib statement, including leading space and multiple files.

    Quotes may group a path containing spaces. Backslashes remain literal so
    Windows paths survive. Continuations and malformed quotes fail closed.
    """
    paths = []
    for line in obj_path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.endswith("\\"):
            raise ValueError("OBJ line continuations are unsupported")
        lexer = shlex.shlex(stripped, posix=True)
        lexer.whitespace_split = True
        lexer.escape = ""
        try:
            tokens = list(lexer)
        except ValueError as exc:
            raise ValueError("Malformed OBJ statement: " + stripped) from exc
        if tokens and tokens[0].lower() == "mtllib":
            if len(tokens) < 2:
                raise ValueError("Empty OBJ mtllib statement")
            for name in tokens[1:]:
                path = (obj_path.parent / name).resolve(strict=True)
                if not path.is_file():
                    raise ValueError("Material library is not a file: " + str(path))
                if path not in paths:
                    paths.append(path)
    return paths


def _texture_warnings(libraries):
    warnings = []
    for mtl in libraries:
        for entry in mtl.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            parts = shlex.split(entry, posix=False)
            if not parts or not (parts[0].lower().startswith("map_") or parts[0].lower() == "bump"):
                continue
            if len(parts) != 2 or parts[1].startswith("-"):
                warnings.append("Unsupported MTL texture options; inspect manually: " + entry)
                continue
            texture = mtl.parent / parts[1].strip('"')
            if not texture.is_file():
                warnings.append("Missing MTL texture: " + str(texture))
    return warnings


def _apply_mtl_images(libraries, mapping):
    """Use SpeedTree's map_Kd/map_d, which Blender OBJ import may ignore."""
    found = {}
    for mtl in libraries:
        material_name = None
        for entry in mtl.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            fields = entry.strip().split(maxsplit=1)
            if not fields:
                continue
            tag = fields[0].lower()
            if tag == "newmtl" and len(fields) == 2:
                material_name = fields[1]
                found.setdefault(material_name, {})
            elif tag in {"map_kd", "map_d", "map_bump"} and len(fields) == 2 and material_name:
                filename = fields[1].strip().strip('"')
                if not filename or filename.startswith("-"):
                    continue
                target = (mtl.parent / filename).resolve()
                if not target.is_file():
                    raise ValueError("Missing material texture: " + str(target))
                found[material_name][tag] = target
    warnings = []
    for name, kind in mapping.items():
        material = bpy.data.materials.get(name)
        if material is None:
            continue
        maps = found.get(name, {})
        if kind == "card" and "map_d" not in maps:
            warnings.append("Card material has no MTL map_d; transparency cannot be verified: " + name)
        material.use_nodes = True
        tree = material.node_tree
        shader = next((node for node in tree.nodes if node.type == "BSDF_PRINCIPLED"), None)
        if shader is None:
            warnings.append("No Principled shader available for material: " + name)
            continue
        for tag, input_name in (("map_kd", "Base Color"), ("map_d", "Alpha")):
            if tag not in maps:
                continue
            texture = tree.nodes.new("ShaderNodeTexImage")
            texture.image = bpy.data.images.load(str(maps[tag]), check_existing=True)
            if tag == "map_d":
                texture.image.colorspace_settings.name = "Non-Color"
            tree.links.new(texture.outputs["Color"], shader.inputs[input_name])
        if "map_d" in maps:
            # Eevee must be told to evaluate alpha even if OBJ import left it opaque.
            if hasattr(material, "surface_render_method"):
                material.surface_render_method = "DITHERED"
            elif hasattr(material, "blend_method"):
                material.blend_method = "HASHED"
        if "map_bump" in maps:
            normal_texture = tree.nodes.new("ShaderNodeTexImage")
            normal_texture.image = bpy.data.images.load(str(maps["map_bump"]), check_existing=True)
            normal_texture.image.colorspace_settings.name = "Non-Color"
            normal = tree.nodes.new("ShaderNodeNormalMap")
            tree.links.new(normal_texture.outputs["Color"], normal.inputs["Color"])
            tree.links.new(normal.outputs["Normal"], shader.inputs["Normal"])
    return warnings


def _used_images(mapping):
    """Inspect image nodes reachable from the material outputs, not orphaned imports."""
    images = set()
    for name in mapping:
        material = bpy.data.materials.get(name)
        if not material or not material.use_nodes:
            continue
        todo = [node for node in material.node_tree.nodes if node.type == "OUTPUT_MATERIAL"]
        seen = set()
        while todo:
            node = todo.pop()
            if node in seen:
                continue
            seen.add(node)
            if node.type == "TEX_IMAGE" and node.image and node.image.source == "FILE":
                images.add(node.image)
            for socket in node.inputs:
                todo.extend(link.from_node for link in socket.links)
    return images


def _trim(obj, keep):
    """Keep selected polygon indices while preserving original UV layers."""
    mesh = obj.data.copy()
    result = obj.copy()
    result.data = mesh
    bpy.context.collection.objects.link(result)
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[face for face in bm.faces if face.index not in keep], context="FACES")
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return result


def _corners(objects):
    points = [obj.matrix_world @ vertex.co for obj in objects for vertex in obj.data.vertices]
    if not points:
        raise ValueError("No exported vertices available")
    low = Vector(tuple(min(v[i] for v in points) for i in range(3)))
    high = Vector(tuple(max(v[i] for v in points) for i in range(3)))
    return low, high


def _mask(path, target):
    # Render alpha becomes grayscale mask; white=tree and black=background.
    image = bpy.data.images.load(str(path), check_existing=False)
    pixels = list(image.pixels[:])
    for i in range(0, len(pixels), 4):
        alpha = pixels[i + 3]
        pixels[i : i + 4] = [alpha, alpha, alpha, 1.0]
    image.pixels[:] = pixels
    image.filepath_raw = str(target)
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)


def main(config_path):
    cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    if _hash_file(Path(cfg["obj"])) != cfg["source_sha256"]:
        raise ValueError("Source OBJ changed before import")
    library_paths = _obj_material_libraries(Path(cfg["obj"]))
    material_libraries = {str(path): _hash_file(path) for path in library_paths}
    output = Path(cfg["output"])
    scene = bpy.context.scene
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    bpy.ops.wm.obj_import(filepath=cfg["obj"], forward_axis="Y", up_axis="Z")
    originals = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not originals:
        raise ValueError("OBJ contains no mesh")
    mapping = cfg["material_categories"]
    used, bare, card_sets = set(), [], []
    for obj in originals:
        groups = {"wood": set(), "card": set()}
        for polygon in obj.data.polygons:
            if polygon.material_index >= len(obj.data.materials):
                raise ValueError("Face has no explicit material")
            mat = obj.data.materials[polygon.material_index]
            if mat is None or mat.name not in mapping:
                raise ValueError("All face materials must be explicitly mapped: " + str(mat))
            used.add(mat.name)
            groups[mapping[mat.name]].add(polygon.index)
        if groups["wood"]:
            bare.append(_trim(obj, groups["wood"]))
        if groups["card"]:
            # Build face-connected islands; this lets closeup show one card rather
            # than framing the entire canopy. A shared material is still only a
            # caller assertion, not proof that geometry is a leaf card.
            v_to_faces = {}
            for idx in groups["card"]:
                for vertex in obj.data.polygons[idx].vertices:
                    v_to_faces.setdefault(vertex, []).append(idx)
            unvisited = set(groups["card"])
            for start in sorted(groups["card"]):
                if start not in unvisited:
                    continue
                stack, component = [start], set()
                while stack:
                    face = stack.pop()
                    if face not in unvisited:
                        continue
                    unvisited.remove(face)
                    component.add(face)
                    for vertex in obj.data.polygons[face].vertices:
                        stack.extend(v_to_faces[vertex])
                area = sum(obj.data.polygons[i].area for i in component)
                card_sets.append((area, obj, component))
    if not bare or not card_sets:
        raise ValueError("OBJ must have both mapped wood and card faces")
    low, high = _corners(originals)
    center = (low + high) / 2
    extents = high - low
    max_area = max(entry[0] for entry in card_sets)

    def outer_score(entry):
        area, obj, faces = entry
        indices = {v for i in faces for v in obj.data.polygons[i].vertices}
        centroid = sum((obj.matrix_world @ obj.data.vertices[i].co for i in indices), Vector()) / len(indices)
        horizontal = sum(((centroid[i] - center[i]) / max(extents[i], 1e-9)) ** 2 for i in (0, 1))
        elevation = (centroid.z - low.z) / max(extents.z, 1e-9)
        return (horizontal + 0.15 * elevation, area)

    eligible = [entry for entry in card_sets if entry[0] >= max_area * 0.25]
    _, close_source, component = max(eligible, key=outer_score)
    close = [_trim(close_source, component)]
    # Orphaned vertices in a trimmed mesh would enlarge its bounds. Remove them.
    for obj in bare + close:
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
        bm.to_mesh(obj.data)
        bm.free()
    warnings = _texture_warnings(library_paths)
    warnings.extend(_apply_mtl_images(library_paths, mapping))
    used_images = _used_images(mapping)
    for image in used_images:
        if not Path(bpy.path.abspath(image.filepath)).is_file():
            warnings.append("Missing image: " + image.filepath)
    if not used_images:
        warnings.append("No image textures were resolved; material appearance requires review")
    image_paths = sorted(
        {
            Path(bpy.path.abspath(image.filepath)).resolve()
            for image in used_images
            if Path(bpy.path.abspath(image.filepath)).is_file()
        },
        key=str,
    )
    texture_hashes = {str(path): _hash_file(path) for path in image_paths}
    all_objects = originals + bare + close
    scale = max(extents) * 1.24
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("Invalid OBJ bounds")
    engines = {item.identifier for item in scene.render.bl_rna.properties["engine"].enum_items}
    scene.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in engines else "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = scene.render.resolution_y = cfg["resolution"]
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.world = bpy.data.worlds.new("Diagnostic world")
    scene.world.color = (0.35, 0.35, 0.35)
    camera_data = bpy.data.cameras.new("Diagnostic orthographic")
    camera = bpy.data.objects.new("Diagnostic orthographic", camera_data)
    bpy.context.collection.objects.link(camera)
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = scale
    camera_data.clip_end = scale * 20
    scene.camera = camera
    light_data = bpy.data.lights.new("Diagnostic fill", "SUN")
    light_data.energy = 2.0
    light = bpy.data.objects.new("Diagnostic fill", light_data)
    bpy.context.collection.objects.link(light)
    light.rotation_euler = (0.45, -0.55, -0.5)
    fill_data = bpy.data.lights.new("Diagnostic reverse fill", "SUN")
    fill_data.energy = 1.0
    fill = bpy.data.objects.new("Diagnostic reverse fill", fill_data)
    bpy.context.collection.objects.link(fill)
    fill.rotation_euler = (2.6, 0.4, 2.6)

    def show(group):
        selected = set(group)
        for ob in all_objects:
            ob.hide_render = ob not in selected

    def render(name, target, direction, ortho):
        camera.location = target + Vector(direction) * (scale * 4)
        camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
        camera_data.ortho_scale = ortho
        scene.render.filepath = str(output / name)
        bpy.context.view_layer.update()
        camera_state = {
            "location": list(camera.location),
            "rotation_euler_radians": list(camera.rotation_euler),
            "matrix_world": [list(row) for row in camera.matrix_world],
            "clip_start": camera_data.clip_start,
            "clip_end": camera_data.clip_end,
            "ortho_scale": camera_data.ortho_scale,
        }
        bpy.ops.render.render(write_still=True)
        return camera_state

    cameras = {}
    for view, direction in {
        "front": (0, -1, 0),
        "back": (0, 1, 0),
        "left": (-1, 0, 0),
        "right": (1, 0, 0),
    }.items():
        cameras[view] = {
            "direction_from_target": list(direction),
            "target": list(center),
            "up": "+Z",
            "projection": "orthographic",
            "ortho_scale": scale,
        }
        for kind, group in (("full", originals), ("bare", bare)):
            show(group)
            name = f"{kind}_{view}.png"
            cameras[view]["transform"] = render(name, center, direction, scale)
            _mask(output / name, output / f"{kind}_{view}_mask.png")
    close_low, close_high = _corners(close)
    close_center = (close_low + close_high) / 2
    close_scale = max(close_high - close_low) * 1.35
    if close_scale <= 0:
        raise ValueError("Selected card has invalid bounds")
    biggest_face = max(component, key=lambda idx: close_source.data.polygons[idx].area)
    normal = close_source.matrix_world.to_3x3() @ close_source.data.polygons[biggest_face].normal
    if normal.length < 1e-9:
        raise ValueError("Selected card has no stable facing normal")
    direction = normal.normalized()
    show(close)
    close_transform = render("card_closeup.png", close_center, direction, close_scale)
    for filename, original_hash in texture_hashes.items():
        if _hash_file(Path(filename)) != original_hash:
            raise ValueError("Texture changed during rendering: " + filename)
    for filename, original_hash in material_libraries.items():
        if _hash_file(Path(filename)) != original_hash:
            raise ValueError("Material library changed during rendering: " + filename)
    manifest = {
        "schema": "blender.tree-diagnostic-preview.v1",
        "renderer": "Blender " + bpy.app.version_string,
        "source": {"path": cfg["obj"], "sha256": cfg["source_sha256"], "format": "OBJ"},
        "projection": "orthographic",
        "coordinate_system": "OBJ coordinates interpreted Z-up",
        "bounds": {"min": list(low), "max": list(high)},
        "cameras": cameras,
        "render_settings": {
            "engine": scene.render.engine,
            "resolution_x": scene.render.resolution_x,
            "resolution_y": scene.render.resolution_y,
            "resolution_percentage": scene.render.resolution_percentage,
            "film_transparent": scene.render.film_transparent,
            "file_format": scene.render.image_settings.file_format,
            "color_mode": scene.render.image_settings.color_mode,
            "color_depth": scene.render.image_settings.color_depth,
            "view_transform": scene.view_settings.view_transform,
            "look": scene.view_settings.look,
            "exposure": scene.view_settings.exposure,
            "gamma": scene.view_settings.gamma,
            "world_color": list(scene.world.color),
        },
        "lights": [
            {
                "name": obj.name,
                "type": obj.data.type,
                "energy": obj.data.energy,
                "color": list(obj.data.color),
                "rotation_euler_radians": list(obj.rotation_euler),
                "matrix_world": [list(row) for row in obj.matrix_world],
            }
            for obj in (light, fill)
        ],
        "material_categories": mapping,
        "material_libraries": [{"path": path, "sha256": digest} for path, digest in material_libraries.items()],
        "used_materials": sorted(used),
        "textures": [{"path": path, "sha256": digest} for path, digest in texture_hashes.items()],
        "card_closeup": {
            "source_object": close_source.name,
            "face_count": len(component),
            "selection": "outer canopy card-category island with at least 25% of the largest area",
            "target": list(close_center),
            "ortho_scale": close_scale,
            "direction_from_target": list(direction),
            "transform": close_transform,
        },
        "mask_encoding": "black background, white foreground, antialiased grayscale",
        "warnings": warnings,
        "limitations": [
            "Diagnostic Blender renders, not native Modeler screenshots.",
            "Caller material categories do not prove generator ownership.",
            "OBJ provenance, native shaders, and actual exported units are unverified.",
            "Material images and transparency require close visual review.",
        ],
    }
    names = [
        f"{kind}_{view}{suffix}.png"
        for kind in ("full", "bare")
        for view in ("front", "back", "left", "right")
        for suffix in ("", "_mask")
    ]
    names.append("card_closeup.png")
    manifest["images"] = {}
    for name in names:
        path = output / name
        image = bpy.data.images.load(str(path), check_existing=False)
        if tuple(image.size) != (cfg["resolution"], cfg["resolution"]):
            raise ValueError("Unexpected diagnostic image dimensions: " + name)
        bpy.data.images.remove(image)
        manifest["images"][name] = _hash_file(path)
    if _hash_file(Path(cfg["obj"])) != cfg["source_sha256"]:
        raise ValueError("Source OBJ changed during rendering")
    (output / "preview-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1])
