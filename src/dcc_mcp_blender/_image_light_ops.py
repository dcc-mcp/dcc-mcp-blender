"""Blender image lifecycle and lighting detail operations.

Image tools here own the datablock lifecycle: loading, saving, packing,
unpacking, and UDIM inspection. They reuse the reporting helpers from
_material_pipeline_ops so a caller sees the same shape as list_images and
reload_image.

Lighting tools here cover what create_light and set_light_properties do not:
Blender 4.x light linking, which is version dependent and therefore checked
before being reported as available, and IES photometric profiles, which are a
node in the light's shader tree rather than a property on the light.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

from dcc_mcp_blender._material_pipeline_ops import _image_info, _image_named, _iter_collection


def _resolve_image(bpy: Any, image_name: str) -> Tuple[Any, Optional[dict]]:
    """Return a loaded image, or an error for the caller."""
    image = _image_named(bpy, image_name)
    if image is None:
        return None, skill_error(f"Image not found: {image_name}", f"No image named '{image_name}'.")
    return image, None


def _abspath(bpy: Any, value: str) -> str:
    """Resolve a Blender path, including the ``//`` blend-relative form.

    ``//`` is Blender's default way to store image paths, so reading it as a
    literal makes a file that sits next to the .blend look missing, and makes a
    successful save look failed because the write is checked at the wrong path.
    """
    resolve = getattr(getattr(bpy, "path", None), "abspath", None)
    if callable(resolve):
        try:
            resolved = resolve(value)
        except Exception:
            resolved = None
        if isinstance(resolved, str) and resolved:
            return resolved
    return str(Path(value).expanduser())


def _file_state(path: Path) -> Optional[Tuple[int, int]]:
    """Return (mtime_ns, size) for a write check, or None when absent."""
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


def load_image(
    file_path: str,
    image_name: Optional[str] = None,
    check_existing: bool = True,
    color_space: Optional[str] = None,
) -> dict:
    """Load an image from disk into the file.

    Args:
        file_path: Path to the image file.
        image_name: Override the datablock name; defaults to Blender's name.
        check_existing: Reuse an already loaded image for the same path
            instead of creating a duplicate datablock.
        color_space: Color space to assign, for example ``sRGB`` or
            ``Non-Color``. Blender ignores names this build does not define,
            which is reported back rather than silently dropped.
    """
    path = Path(file_path).expanduser()
    if not path.is_file():
        return skill_error(f"Image file not found: {path}", f"No file at '{path}'.")

    try:
        import bpy

        image = bpy.data.images.load(str(path), check_existing=bool(check_existing))
        if image_name:
            image.name = image_name

        applied: Dict[str, Any] = {}
        skipped: List[str] = []
        if color_space:
            settings = getattr(image, "colorspace_settings", None)
            if settings is None:
                skipped.append("color_space")
            else:
                try:
                    settings.name = color_space
                    applied["color_space"] = color_space
                except Exception:
                    # Blender raises for names this build does not define.
                    skipped.append("color_space")

        return skill_success(
            f"Loaded image {image.name}",
            image=_image_info(image),
            applied=applied,
            not_applied=list(skipped),
            prompt="Use pack_image to embed it, or list_images to review loaded images.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to load image {path}")


def _decode_pixels(image: Any) -> Tuple[bool, Optional[str]]:
    """Materialise an image's pixel data.

    Under blender --background an image loaded from disk has no decoded pixels
    until one is actually read. Indexing is what forces the decode; len() does
    not, because a lazily loaded collection already reports the full count while
    has_data is still False.

    Returns (ok, reason). reason is None on success and explains the failure
    otherwise, so a caller can surface it rather than guessing.
    """
    pixels = getattr(image, "pixels", None)
    if pixels is None:
        return True, None
    try:
        _ = pixels[0]
    except Exception as exc:
        # An empty collection raises IndexError rather than returning short, so
        # treat that the same as a decode that produced nothing.
        return False, f"could not read pixel data ({type(exc).__name__}: {exc})"
    if getattr(image, "has_data", None) is False:
        return False, "the image still reports no pixel data after decoding"
    return True, None


def save_image(image_name: str, file_path: Optional[str] = None) -> dict:
    """Save an image datablock to disk.

    With ``file_path`` this is "save a copy at that path"; without it, the
    image is written back over its own file.

    Args:
        image_name: Loaded image to save.
        file_path: Destination path; defaults to the image's current path.
    """
    try:
        import bpy

        image, error = _resolve_image(bpy, image_name)
        if error:
            return error

        if file_path:
            destination = Path(_abspath(bpy, file_path))
        else:
            if not image.filepath:
                return skill_error(
                    f"{image_name} has no file path",
                    "The image was generated or packed; pass file_path explicitly.",
                )
            # image.filepath is usually blend-relative ("//textures/x.png"), and
            # image.save() writes relative to the .blend, so the destination has
            # to be resolved the same way or a successful save is reported as a
            # failure.
            destination = Path(_abspath(bpy, image.filepath))

        # Assigning image.filepath is deliberately avoided. Under background
        # mode it re-associates the datablock with that file and invalidates the
        # decoded pixel buffer: assigning before the decode leaves pixels empty
        # (IndexError on read), assigning after it makes save() fail with
        # "does not have any image data". No ordering of the assignment works,
        # so save_render is used to write to an explicit path instead, which
        # writes without re-pointing the datablock.

        decoded, reason = _decode_pixels(image)
        has_data = getattr(image, "has_data", None)
        if not decoded:
            return skill_error(
                f"Image has no pixel data to save: {image_name}",
                f"The image could not be decoded, so there is nothing to write: {reason}. "
                "This is typical under blender --background for images loaded from disk.",
                filepath=str(destination),
                has_data=has_data,
            )

        # Record the state before writing: a file that is already there proves
        # nothing about this call, so the check below has to be a change, not an
        # existence test.
        before = _file_state(destination)

        try:
            if file_path:
                image.save_render(str(destination))
            else:
                image.save()
        except Exception as exc:
            # Report the measured state so the failure is diagnosable instead of
            # a bare operator error.
            return skill_exception(
                exc,
                message=f"Failed to save image {image_name}",
                filepath=str(destination),
                has_data=getattr(image, "has_data", None),
            )

        # Confirm the write rather than trusting the call. A file that already
        # existed is not evidence of this save, so require the file both to
        # exist and to differ from the state recorded before the write.
        after = _file_state(destination)
        if after is None:
            return skill_error(
                f"Image was not saved: {image_name}",
                f"Blender completed the save call but no file exists at '{destination}'.",
                filepath=str(destination),
                has_data=getattr(image, "has_data", None),
            )
        if before is not None and before == after:
            return skill_error(
                f"Image was not written: {image_name}",
                f"Blender completed the save call but '{destination}' is unchanged "
                f"(mtime_ns {before[0]}, size {before[1]}), so nothing was written this time.",
                filepath=str(destination),
                has_data=getattr(image, "has_data", None),
            )

        return skill_success(
            f"Saved image {image.name}",
            image=_image_info(image),
            filepath=str(destination),
            size_bytes=destination.stat().st_size,
            has_data=getattr(image, "has_data", None),
            method="save_render" if file_path else "save",
            prompt="Use pack_image or unpack_image to control how the file is stored.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to save image {image_name}")


def pack_image(image_name: str) -> dict:
    """Embed an image into the .blend file.

    Args:
        image_name: Loaded image to pack.
    """
    try:
        import bpy

        image, error = _resolve_image(bpy, image_name)
        if error:
            return error

        if getattr(image, "packed_file", None) is not None:
            return skill_success(
                f"Image {image.name} is already packed",
                image=_image_info(image),
                packed=True,
                changed=False,
            )

        packer = getattr(image, "pack", None)
        if not callable(packer):
            return skill_error("Packing unavailable", f"{image.name} exposes no pack() method.")
        try:
            packer()
        except Exception as exc:
            return skill_exception(exc, message=f"Failed to pack image {image_name}")

        packed = getattr(image, "packed_file", None) is not None
        if not packed:
            return skill_error(
                f"Image was not packed: {image_name}",
                "Blender completed the pack call but no packed file is attached. "
                "The image may have no source file on disk to read from.",
            )
        return skill_success(f"Packed image {image.name}", image=_image_info(image), packed=True, changed=True)
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to pack image {image_name}")


def unpack_image(image_name: str, method: str = "USE_ORIGINAL") -> dict:
    """Write a packed image out to disk and stop embedding it.

    Args:
        image_name: Packed image to unpack.
        method: One of ``USE_ORIGINAL``, ``WRITE_ORIGINAL``, ``USE_LOCAL``,
            or ``WRITE_LOCAL``.
    """
    wanted = str(method or "USE_ORIGINAL").upper()
    valid = {"USE_ORIGINAL", "WRITE_ORIGINAL", "USE_LOCAL", "WRITE_LOCAL"}
    if wanted not in valid:
        return skill_error(
            f"Unsupported unpack method: {method}",
            f"Supported methods: {', '.join(sorted(valid))}.",
        )
    try:
        import bpy

        image, error = _resolve_image(bpy, image_name)
        if error:
            return error

        if getattr(image, "packed_file", None) is None:
            return skill_success(
                f"Image {image.name} is not packed",
                image=_image_info(image),
                packed=False,
                changed=False,
                prompt="Only packed images need unpacking.",
            )

        unpacker = getattr(image, "unpack", None)
        if not callable(unpacker):
            return skill_error("Unpacking unavailable", f"{image.name} exposes no unpack() method.")
        try:
            unpacker(method=wanted)
        except Exception as exc:
            return skill_exception(exc, message=f"Failed to unpack image {image_name}")

        if getattr(image, "packed_file", None) is not None:
            return skill_error(
                f"Image was not unpacked: {image_name}",
                "Blender completed the unpack call but the image is still packed.",
            )
        return skill_success(f"Unpacked image {image.name}", image=_image_info(image), packed=False, method=wanted)
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to unpack image {image_name}")


def image_file_status(image_name: str) -> dict:
    """Report where an image lives and whether the file is reachable.

    Covers the states that matter before saving or packing: unsaved, missing
    from disk, packed inside the blend, or edited in memory since load.
    """
    try:
        import bpy

        image, error = _resolve_image(bpy, image_name)
        if error:
            return error

        filepath = getattr(image, "filepath", "") or ""
        packed = getattr(image, "packed_file", None) is not None
        # Resolve "blend-relative" paths before asking the disk, or an image
        # that is present next to the .blend is reported as missing.
        resolved = _abspath(bpy, filepath) if filepath else ""
        exists_on_disk = bool(resolved) and Path(resolved).expanduser().is_file()

        if packed:
            state = "packed"
        elif not filepath:
            state = "unsaved"
        elif not exists_on_disk:
            state = "missing"
        elif bool(getattr(image, "is_dirty", False)):
            state = "modified_unsaved"
        else:
            state = "external"

        return skill_success(
            f"Image {image.name} is {state}",
            image=_image_info(image),
            state=state,
            packed=packed,
            exists_on_disk=exists_on_disk,
            is_dirty=bool(getattr(image, "is_dirty", False)),
            prompt="Use save_image, pack_image, or unpack_image to change how it is stored.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to inspect image {image_name}")


def list_image_tiles(image_name: str) -> dict:
    """List the UDIM tiles of an image.

    A non-UDIM image reports one tile and ``is_udim: False`` rather than an
    error, so a caller can ask about any image.
    """
    try:
        import bpy

        image, error = _resolve_image(bpy, image_name)
        if error:
            return error

        source = getattr(image, "source", None)
        tiles = []
        for tile in _iter_collection(getattr(image, "tiles", [])):
            tiles.append(
                {
                    "number": getattr(tile, "number", None),
                    "label": getattr(tile, "label", None),
                }
            )

        return skill_success(
            f"Image {image.name} has {len(tiles)} tile(s)",
            image=_image_info(image),
            source=source,
            # TILED is Blender's single-tile UDIM source, so matching UDIM alone
            # misreports a one-tile UDIM image as a plain image.
            is_udim=source in ("UDIM", "TILED") or len(tiles) > 1,
            count=len(tiles),
            tiles=tiles,
            prompt="Use load_image with a UDIM path pattern to populate tiles, then save_image.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to list tiles for {image_name}")


# The adapter's declared host baseline, mirrored from install.MIN_BLENDER_VERSION
# (Blender 4.5, see "raise the supported host baseline to Blender 4.5"). It is
# copied rather than imported so the IES path stays importable on its own.
#
# This floor is the adapter's support window, NOT an IES requirement:
# ShaderNodeTexIES predates 4.5 by years. It is checked first because a refusal
# that names the supported window is more actionable than one naming a node type
# the caller has never heard of. The floor is deliberately not the real gate --
# that is the "can this build create the node" check below, which is what decides
# support on any build that clears the baseline.
MIN_BLENDER_VERSION_FOR_IES = (4, 5)

# Node type that carries a photometric profile. Named once so the refusal, the
# lookup, and the verification all agree on what "IES support" means.
IES_NODE_TYPE = "ShaderNodeTexIES"
IES_NODE_TREE_TYPE = "TEX_IES"


def _resolve_light(bpy: Any, light_name: str) -> Tuple[Any, Optional[dict]]:
    """Return a light object's data, or an error for the caller."""
    obj = bpy.data.objects.get(light_name)
    if obj is None:
        return None, skill_error(f"Object not found: {light_name}", f"No object named '{light_name}'.")
    if getattr(obj, "type", None) != "LIGHT":
        return None, skill_error(
            f"{light_name} is not a light", f"Object type is {getattr(obj, 'type', '?')}, expected LIGHT."
        )
    return obj, None


def set_light_linking(
    light_name: str,
    receiver_collection: Optional[str] = None,
    blocker_collection: Optional[str] = None,
    clear: bool = False,
) -> dict:
    """Restrict which objects a light affects using Blender 4.x light linking.

    Light linking makes a light only illuminate a chosen collection, and lets
    another collection block it. Blender 4.1 added it on the *object*
    (``Object.light_linking``), not on the light data block, so the object is
    what is read here. Earlier versions have no such property and are reported
    rather than assumed.

    Args:
        light_name: Light to constrain.
        receiver_collection: Collection the light is allowed to illuminate.
        blocker_collection: Collection that blocks this light.
        clear: Remove existing linking instead of setting it.
    """
    if not clear and receiver_collection is None and blocker_collection is None:
        return skill_error(
            "No linking change supplied",
            "Provide receiver_collection, blocker_collection, or clear=true.",
        )
    try:
        import bpy

        obj, error = _resolve_light(bpy, light_name)
        if error:
            return error

        # Light linking lives on the object. Reading it from obj.data (the Light
        # data block) reports "unavailable" on the builds that do have the
        # feature, which turns the tool into a permanent no-op.
        linking = getattr(obj, "light_linking", None)
        if linking is None:
            return skill_error(
                "Light linking unavailable on this Blender version",
                f"{light_name} exposes no light_linking property; this build does not support light linking.",
            )

        # Resolve every collection before writing any of them. Assigning the
        # receiver and then failing on the blocker leaves the light half-linked
        # while the caller is told the call failed.
        resolved: List[Tuple[str, Optional[Any]]] = []
        for role, collection_name in (
            ("receiver_collection", receiver_collection),
            ("blocker_collection", blocker_collection),
        ):
            if collection_name is None and not clear:
                continue
            # hasattr matters, not truthiness: an unset link is None, which is
            # different from a build that has no such property at all.
            if not hasattr(linking, role):
                return skill_error(
                    "Light linking incomplete on this Blender version",
                    f"light_linking exposes no {role}; this build does not support {role.replace('_', ' ')}.",
                )
            if clear or collection_name is None:
                resolved.append((role, None))
                continue
            collection = bpy.data.collections.get(collection_name)
            if collection is None:
                return skill_error(
                    f"Collection not found: {collection_name}",
                    f"No collection named '{collection_name}'.",
                )
            resolved.append((role, collection))

        applied: Dict[str, Any] = {}
        for role, collection in resolved:
            setattr(linking, role, collection)
            applied[role] = getattr(collection, "name", None)

        return skill_success(
            f"Updated light linking on {light_name}",
            object_name=light_name,
            applied=applied,
            receiver=getattr(getattr(linking, "receiver_collection", None), "name", None),
            blocker=getattr(getattr(linking, "blocker_collection", None), "name", None),
            prompt="Light linking affects Cycles and EEVEE Next; render to see the result.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to set light linking on {light_name}")


def _first_socket(sockets: Any) -> Any:
    """Return the first socket of a collection, or None when there is none.

    Blender collections index by position, while a plain mapping only supports
    its keys, so both shapes are handled rather than assuming that indexing by
    0 works everywhere.
    """
    if sockets is None:
        return None
    try:
        return sockets[0]
    except (KeyError, IndexError, TypeError):
        pass
    values = getattr(sockets, "values", None)
    if callable(values):
        for socket in values():
            return socket
    try:
        for socket in sockets:
            return socket
    except TypeError:
        return None
    return None


def _find_node(nodes: Any, node_type: str) -> Any:
    """Return the first node of ``node_type``, or None."""
    if nodes is None:
        return None
    for node in nodes:
        if getattr(node, "type", None) == node_type:
            return node
    return None


def _socket_by_name(sockets: Any, name: str) -> Any:
    """Return the named socket, or None when there is no such socket."""
    if sockets is None:
        return None
    getter = getattr(sockets, "get", None)
    if callable(getter):
        try:
            socket = getter(name)
        except Exception:
            socket = None
        if socket is not None:
            return socket
    try:
        return sockets[name]
    except (KeyError, IndexError, TypeError):
        return None


def _driving_emission_node(nodes: Any) -> Any:
    """Return the Emission node that feeds ``ShaderNodeOutputLight.Surface``.

    A light tree can hold several emission nodes, and node order says nothing
    about which one the renderer reads. Following the link back from the light
    output is what makes the difference between writing the node that lights the
    scene and writing an orphan that renders nothing. Returns None when the link
    cannot be traced.
    """
    output = _find_node(nodes, "OUTPUT_LIGHT")
    if output is None:
        return None
    surface = _socket_by_name(getattr(output, "inputs", None), "Surface")
    if surface is None:
        return None
    links = getattr(surface, "links", None)
    if not links:
        return None
    try:
        link = links[0]
    except (IndexError, KeyError, TypeError):
        return None
    source_name = getattr(getattr(link, "from_node", None), "name", None)
    if not isinstance(source_name, str):
        return None
    for node in nodes:
        if getattr(node, "name", None) == source_name:
            return node
    return None


def _ensure_emission_node(node_tree: Any) -> Tuple[Any, Optional[dict]]:
    """Return the light's driving Emission node, or an error for the caller.

    IES shapes a light by driving an emission node's ``Strength`` input, so the
    node it is attached to has to be the one the renderer reads. When the light
    output is already driven by something that is not an emission node there is
    no Strength input to drive at all, and attaching to any other emission node
    in the tree would wire the profile into something that renders nothing while
    still passing every check on the node itself. That case is refused rather
    than guessed.
    """
    nodes = node_tree.nodes

    driving = _driving_emission_node(nodes)
    if driving is not None:
        if getattr(driving, "type", None) == "EMISSION":
            return driving, None
        # Something other than an emission shader feeds the light output, so the
        # profile has nowhere to land that the renderer would read.
        node_type = getattr(driving, "type", None) or "unknown"
        return None, skill_error(
            f"Light output is driven by a {node_type} node, not an emission shader",
            f"IES drives an emission node's Strength input, but ShaderNodeOutputLight is fed by "
            f"'{node_type}'. Remove that node or route the light through an emission shader first.",
        )

    # Nothing drives the output yet, so the light is free to be taken over.
    emission = _find_node(nodes, "EMISSION")
    if emission is None:
        emission = nodes.new("ShaderNodeEmission")

    output = _find_node(nodes, "OUTPUT_LIGHT")
    if output is None:
        output = nodes.new("ShaderNodeOutputLight")
    surface = _socket_by_name(getattr(output, "inputs", None), "Surface")
    if surface is not None and not getattr(surface, "is_linked", False):
        node_tree.links.new(_first_socket(getattr(emission, "outputs", None)), surface)
    return emission, None


def _ies_node_on(light: Any) -> Any:
    """Return the light's existing IES node, or None."""
    node_tree = getattr(light, "node_tree", None)
    if node_tree is None:
        return None
    return _find_node(getattr(node_tree, "nodes", None), IES_NODE_TREE_TYPE)


def _remove_ies_nodes(node_tree: Any) -> int:
    """Delete every IES node from a light tree; return how many went away."""
    nodes = getattr(node_tree, "nodes", None)
    if nodes is None:
        return 0
    removed = 0
    for node in [node for node in nodes if getattr(node, "type", None) == IES_NODE_TREE_TYPE]:
        try:
            nodes.remove(node)
            removed += 1
        except Exception:
            # A node that cannot be removed must not hide the ones that can.
            continue
    return removed


def _remove_ies_strength_links(node_tree: Any) -> int:
    """Drop only the Strength links an IES node was driving; return how many.

    Clearing must not touch anything the user wired themselves. An emission
    node's Strength can be driven by a Value node, a driver, or a fallback the
    rigger set up, and removing that to "tidy up" would silently undo their work
    while still reporting success. So a link is only removed when the node on
    the far end is one of ours.

    Every emission node is checked, not just the one driving the light output,
    so a profile attached before this tool refused that shape is still cleaned
    up rather than left behind.
    """
    nodes = getattr(node_tree, "nodes", None)
    if nodes is None:
        return 0
    removed = 0
    for node in nodes:
        if getattr(node, "type", None) != "EMISSION":
            continue
        strength = _socket_by_name(getattr(node, "inputs", None), "Strength")
        links = getattr(strength, "links", None)
        if not links:
            continue
        for link in list(links):
            if getattr(getattr(link, "from_node", None), "type", None) != IES_NODE_TREE_TYPE:
                continue
            try:
                node_tree.links.remove(link)
                removed += 1
            except Exception:
                # A link that will not go must not stop the rest from going.
                continue
    return removed


def _ies_node_from_link(link: Any) -> Any:
    """Return the IES node at the far end of a link, or None.

    Used to find the node that is currently driving an emission node's Strength
    input, which is the only one whose profile actually reaches the render.
    """
    if link is None:
        return None
    node = getattr(link, "from_node", None)
    if getattr(node, "type", None) != IES_NODE_TREE_TYPE:
        return None
    return node


def _ies_link_is_from(emission: Any, ies: Any) -> bool:
    """True when ``ies`` is the node driving ``emission``'s Strength input.

    Compares by node name rather than identity. Blender returns a fresh wrapper
    object on every attribute access, so a node reached through a link is never
    identity-equal to the same node reached by iterating the tree -- an ``is``
    check here would report failure for a wiring that is perfectly correct.
    Node names are unique within a tree, which makes the name check exact.
    """
    link = _strength_link(emission)
    if link is None:
        return False
    source = getattr(link, "from_node", None)
    if getattr(source, "type", None) != IES_NODE_TREE_TYPE:
        return False
    expected = getattr(ies, "name", None)
    actual = getattr(source, "name", None)
    if not isinstance(expected, str) or not isinstance(actual, str):
        # Without names to compare, fall back to identity rather than assume.
        return source is ies
    return actual == expected


def _strength_link_is(emission: Any, socket: Any) -> bool:
    """True when ``socket`` is what currently drives ``emission``'s Strength.

    Used to confirm a restored link really landed. Compares sockets by identity,
    which holds here because both come from the same link object rather than
    from separate traversals of the tree.
    """
    if socket is None:
        return False
    link = _strength_link(emission)
    if link is None:
        return False
    return getattr(link, "from_socket", None) is socket


def _strength_link(emission: Any) -> Any:
    """Return the link driving an emission node's Strength input, or None."""
    strength = _socket_by_name(getattr(emission, "inputs", None), "Strength")
    if strength is None:
        return None
    links = getattr(strength, "links", None)
    if not links:
        return None
    try:
        return links[0]
    except (IndexError, KeyError, TypeError):
        return None


def set_light_ies(
    light_name: str,
    ies_path: Optional[str] = None,
    strength: Optional[float] = None,
    clear: bool = False,
) -> dict:
    """Attach an IES photometric profile to a light.

    Blender has no ``Light.ies_file`` property. A photometric profile is a
    ``ShaderNodeTexIES`` in the light's shader tree whose ``Fac`` output drives
    the emission node's ``Strength`` input, so that is what this builds.

    Two things decide whether the profile actually reaches the render, and both
    are verified here rather than assumed:

    * the node has to feed the emission node that drives the light output -- an
      emission node that renders nothing would make the whole call a no-op; and
    * an external profile has to point at a file that exists. Blender accepts a
      missing path without complaint and then renders the light unshaped, which
      is the failure this check exists to catch.

    The node's ``Vector`` input is deliberately left unconnected: the renderer
    resolves the profile direction from the light itself, and connecting a
    Geometry node there mis-aims the beam.

    Args:
        light_name: Light to shape.
        ies_path: Path to an ``.ies`` photometric file. Required unless ``clear``.
        strength: Optional multiplier on the profile's contribution.
        clear: Remove the IES node instead of setting one.
    """
    if not clear and not ies_path:
        return skill_error(
            "No IES profile supplied",
            "Provide ies_path, or clear=true to remove an existing profile.",
        )

    try:
        import bpy

        obj, error = _resolve_light(bpy, light_name)
        if error:
            return error

        version = tuple(bpy.app.version[:3])
        if version < MIN_BLENDER_VERSION_FOR_IES:
            return skill_error(
                "IES profiles unavailable on this Blender version",
                "this build runs Blender {0}.{1}.{2}; the adapter supports {3}.{4} and newer".format(
                    version[0], version[1], version[2], MIN_BLENDER_VERSION_FOR_IES[0], MIN_BLENDER_VERSION_FOR_IES[1]
                ),
            )

        light = obj.data

        # Clearing leaves the light unshaped; the profile file is not needed.
        if clear:
            node_tree = getattr(light, "node_tree", None)
            if node_tree is None:
                return skill_success(
                    f"No IES profile on {light_name}",
                    object_name=light_name,
                    applied=False,
                    removed=0,
                    prompt="The light has no shader tree, so there is no profile to remove.",
                )
            removed = _remove_ies_nodes(node_tree)
            links_removed = _remove_ies_strength_links(node_tree)

            # Confirm the tree no longer carries a profile before calling it done.
            still_present = _ies_node_on(light) is not None
            if still_present:
                return skill_error(
                    f"IES profile not removed from {light_name}",
                    "an IES node is still present in the light's shader tree after removal.",
                )
            return skill_success(
                f"Removed IES profile from {light_name}",
                object_name=light_name,
                applied=False,
                removed=removed,
                links_removed=links_removed,
                prompt="The light renders unshaped again; render to confirm.",
            )

        # An external profile Blender cannot open shapes nothing at all, and the
        # failure is silent at render time, so the file is checked up front.
        resolved_path = os.path.abspath(os.path.expanduser(str(ies_path)))
        if not os.path.isfile(resolved_path):
            return skill_error(
                f"IES profile not found: {ies_path}",
                f"No readable file at '{resolved_path}'. Blender accepts a missing path and then "
                "renders the light unshaped, so the path is verified before it is used.",
            )

        node_tree = getattr(light, "node_tree", None)
        if node_tree is None:
            # Blender materialises the default tree once nodes are switched on.
            use_nodes = getattr(light, "use_nodes", None)
            if use_nodes is not None and not use_nodes:
                light.use_nodes = True
            node_tree = getattr(light, "node_tree", None)
        if node_tree is None:
            return skill_error(
                f"{light_name} has no shader tree",
                "this build does not expose a node tree on the light, so no IES node can be added.",
            )

        emission, ensure_error = _ensure_emission_node(node_tree)
        if ensure_error:
            return ensure_error

        # Reuse the node that is actually driving the light, so repeat calls
        # update the profile the renderer reads instead of stacking a second one.
        # Taking the first IES node in the tree is not enough: with two of them,
        # configuring the one that is not connected reports success for a profile
        # that never renders.
        target = _socket_by_name(getattr(emission, "inputs", None), "Strength")
        existing_link = _strength_link(emission)
        ies = _ies_node_from_link(existing_link)
        if ies is None:
            ies = _ies_node_on(light)
        if ies is None:
            try:
                ies = node_tree.nodes.new(IES_NODE_TYPE)
            except Exception as exc:
                return skill_error(
                    "IES profiles unavailable on this Blender version",
                    f"this build cannot create a {IES_NODE_TYPE} node ({exc}).",
                )

        ies.mode = "EXTERNAL"
        ies.filepath = resolved_path
        if strength is not None:
            strength_socket = _socket_by_name(getattr(ies, "inputs", None), "Strength")
            if strength_socket is None:
                return skill_error(
                    f"IES node on {light_name} has no Strength input",
                    "this build's IES node exposes no Strength socket, so the multiplier cannot be applied.",
                )
            strength_socket.default_value = float(strength)

        fac = _socket_by_name(getattr(ies, "outputs", None), "Fac")
        if fac is None or target is None:
            return skill_error(
                f"IES node cannot drive {light_name}",
                "the IES node has no Fac output, or the emission node has no Strength input.",
            )
        # Taking over the socket is destructive, so the previous wiring is
        # remembered and put back if anything goes wrong afterwards. Without
        # this, a link that fails to land leaves the caller being told "it did
        # not work" while the light has in fact lost whatever drove it before --
        # the caller reasonably reads a failure as "nothing changed".
        previous = None
        if existing_link is not None:
            previous = (existing_link.from_socket, existing_link.to_socket)
        previous_type = None
        if existing_link is not None:
            previous_type = getattr(getattr(existing_link, "from_node", None), "type", None)
        rewired = False

        restored = False

        def _restore_previous_link() -> None:
            """Put the previous wiring back; remember whether it actually landed.

            A restore that silently fails would leave the light un driven while
            the caller is told the previous wiring is in place, so the outcome is
            recorded and surfaced rather than assumed.
            """
            nonlocal restored
            if not rewired or previous is None:
                return
            try:
                node_tree.links.new(previous[0], previous[1])
            except Exception:
                return
            # Confirm the link is really back instead of trusting the call.
            restored = _strength_link_is(emission, previous[0])

        # Rewire when a different IES node currently holds the socket; otherwise
        # the profile we just configured stays off the render path.
        if not _ies_link_is_from(emission, ies):
            if existing_link is not None:
                try:
                    node_tree.links.remove(existing_link)
                except Exception:
                    pass
            try:
                node_tree.links.new(fac, target)
            except Exception as exc:
                _restore_previous_link()
                return skill_error(
                    f"IES profile could not be wired into {light_name}",
                    f"the emission node's Strength input could not be linked ({exc}); the previous "
                    "wiring was left as it was.",
                )
            rewired = True

        # ── Verify: the node we configured is the one actually driving the
        # emission node the renderer reads. Every failure from here on puts the
        # previous wiring back before reporting, so a refusal never leaves the
        # light in a worse state than it was found.
        confirmed = ies

        def _refuse(message: str, error: str) -> dict:
            _restore_previous_link()
            if rewired and previous is not None and not restored:
                # The previous wiring could not be put back. Say so loudly: the
                # light is now driven by nothing, and reporting only the original
                # failure would hide that.
                error = (
                    error + " The previous wiring on the Strength input could not be restored, so the "
                    "light is left with nothing driving it."
                )
            return skill_error(
                message,
                error,
                previous_link=previous_type,
                took_over_link=rewired and previous is not None,
                previous_link_restored=restored if (rewired and previous is not None) else None,
            )

        if _ies_node_on(light) is None:
            return _refuse(
                f"IES profile not applied to {light_name}",
                "no IES node is present in the light's shader tree after the write.",
            )

        confirmed_path = getattr(confirmed, "filepath", None)
        if confirmed_path and os.path.abspath(os.path.expanduser(str(confirmed_path))) != resolved_path:
            return _refuse(
                f"IES profile not applied to {light_name}",
                f"the node points at '{confirmed_path}', not '{resolved_path}'.",
            )

        if not _ies_link_is_from(emission, confirmed):
            return _refuse(
                f"IES profile is not driving {light_name}",
                "the IES node's Fac output did not take over the emission node's Strength input, "
                "so the profile would not render",
            )

        strength_socket = _socket_by_name(getattr(confirmed, "inputs", None), "Strength")
        return skill_success(
            f"Set IES profile on {light_name}",
            object_name=light_name,
            applied=True,
            ies_path=resolved_path,
            mode="EXTERNAL",
            node_name=getattr(confirmed, "name", None),
            strength=getattr(strength_socket, "default_value", None),
            # Taking over somebody else's wiring is a real change to their scene,
            # so it is reported rather than done quietly.
            replaced_link=previous_type,
            prompt="IES shapes the light in Cycles and EEVEE Next; render to see the beam.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to set IES profile on {light_name}")
