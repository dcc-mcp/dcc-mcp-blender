"""Read-only validation of material resources without loading artist images."""

from pathlib import Path

_MAX_GRAPH_NODES = 4096
_MAX_GROUP_DEPTH = 16
_MAX_IMAGE_FILES = 1024


def _connected_images(material):
    """Inspect shared node groups once, with a fixed graph work budget."""
    stack = [(material.node_tree, 0)]
    seen = set()
    images = []
    count = 0
    incomplete = False
    while stack:
        tree, depth = stack.pop()
        if tree is None:
            incomplete = True
            continue
        pointer = getattr(tree, "as_pointer", None)
        identity = pointer() if callable(pointer) else id(tree)
        if identity in seen:
            continue
        seen.add(identity)
        if depth > _MAX_GROUP_DEPTH:
            incomplete = True
            continue
        for node in tree.nodes:
            count += 1
            if count > _MAX_GRAPH_NODES:
                return images, True
            if getattr(node, "mute", False) or not any(output.is_linked for output in node.outputs):
                continue
            if node.type in {"TEX_IMAGE", "TEX_ENVIRONMENT"}:
                images.append(node)
            elif node.type == "GROUP":
                stack.append((node.node_tree, depth + 1))
    return images, incomplete


def _image_issue(material, node, image, code, message, tile=None):
    return {
        "code": code,
        "severity": "warning" if code.endswith("UNVERIFIED") else "error",
        "message": message,
        "details": {
            "material": material.name,
            "node": node.name,
            "image": image.name if image else None,
            "tile": tile,
        },
    }


def material_image_issues(bpy, material):
    """Return resource findings for image nodes in an enabled material graph."""
    tree = getattr(material, "node_tree", None)
    # Hosts without the legacy toggle always use material node trees.
    if tree is None or not bool(getattr(material, "use_nodes", True)):
        return []
    issues = []
    nodes, incomplete = _connected_images(material)
    if incomplete:
        issues.append(
            {
                "code": "MATERIAL_GRAPH_UNVERIFIED",
                "severity": "warning",
                "message": "Connected node groups could not be fully inspected within the graph budget.",
                "details": {"material": material.name},
            }
        )
    files_checked = 0
    for node in nodes:
        image = node.image
        packed = image is not None and (
            getattr(image, "packed_file", None) is not None or bool(getattr(image, "packed_files", ()))
        )
        if image is not None and image.source == "TILED" and packed:
            issues.append(
                _image_issue(
                    material,
                    node,
                    image,
                    "MATERIAL_IMAGE_UNVERIFIED",
                    "Packed UDIM coverage is not verified per declared tile.",
                )
            )
            continue
        if image is not None and (image.source in {"GENERATED", "VIEWER"} or image.source == "FILE" and packed):
            continue
        if image is not None and (
            image.source not in {"FILE", "TILED"}
            or image.source == "TILED"
            and ("<UDIM>" not in image.filepath or not image.tiles)
        ):
            issues.append(
                _image_issue(
                    material,
                    node,
                    image,
                    "MATERIAL_IMAGE_UNVERIFIED",
                    "Image source requires sequence/media validation or a declared UDIM tile template.",
                )
            )
            continue
        required_files = len(image.tiles) if image is not None and image.source == "TILED" else 1
        if files_checked + required_files > _MAX_IMAGE_FILES:
            issues.append(
                _image_issue(
                    material,
                    node,
                    image,
                    "MATERIAL_IMAGE_UNVERIFIED",
                    "Material image file-check budget exceeded.",
                )
            )
            return issues
        path = bpy.path.abspath(image.filepath, library=getattr(image, "library", None)) if image else ""
        paths = [(path, None)]
        if image is not None and image.source == "TILED":
            paths = [(path.replace("<UDIM>", str(tile.number)), tile.number) for tile in image.tiles]
        for candidate, tile in paths:
            files_checked += 1
            if not candidate or not Path(candidate).is_file():
                issues.append(
                    _image_issue(
                        material,
                        node,
                        image,
                        "MATERIAL_IMAGE_MISSING",
                        f"Connected image is missing for material {material.name}.",
                        tile,
                    )
                )
    return issues
