"""Blender image lifecycle and lighting detail operations.

Image tools here own the datablock lifecycle: loading, saving, packing,
unpacking, and UDIM inspection. They reuse the reporting helpers from
_material_pipeline_ops so a caller sees the same shape as list_images and
reload_image.

Lighting tools here cover what create_light and set_light_properties do not:
Blender 4.x light linking, which is version dependent and therefore checked
before being reported as available.
"""

from __future__ import annotations

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
                f"{light_name} exposes no light_linking property. Light linking was added in Blender 4.1.",
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
