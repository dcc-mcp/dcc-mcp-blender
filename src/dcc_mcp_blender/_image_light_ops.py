"""Blender image lifecycle and lighting detail operations.

Image tools here own the datablock lifecycle: loading, saving, packing,
unpacking, and UDIM inspection. They reuse the reporting helpers from
_material_pipeline_ops so a caller sees the same shape as list_images and
reload_image.

Lighting tools here cover what create_light and set_light_properties do not:
IES textures and Blender 4.x light linking, both of which are version or
engine dependent and therefore checked before being reported as available.
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


def save_image(image_name: str, file_path: Optional[str] = None) -> dict:
    """Save an image datablock back to disk.

    Args:
        image_name: Loaded image to save.
        file_path: Destination path; defaults to the image's current path.
    """
    try:
        import bpy

        image, error = _resolve_image(bpy, image_name)
        if error:
            return error

        destination = Path(file_path).expanduser() if file_path else Path(image.filepath).expanduser()
        if not file_path and not image.filepath:
            return skill_error(
                f"{image_name} has no file path",
                "The image was generated or packed; pass file_path explicitly.",
            )

        # Under blender --background an image loaded from disk has no decoded
        # pixels until one is actually read, and image.save() then fails with
        # "does not have any image data".
        #
        # Indexing a pixel is what forces the decode. len(image.pixels) does
        # not: a probe on every supported Blender reported len == 16 for a 2x2
        # image while has_data was still False, so length is a misleading
        # signal. Generated images already have data and need none of this.
        # Packing needs neither because it copies the source file.
        pixels = getattr(image, "pixels", None)
        if pixels is not None:
            try:
                _ = pixels[0]
            except Exception as exc:
                return skill_exception(
                    exc,
                    message=f"Failed to read pixel data for {image_name}",
                    filepath=str(destination),
                )

        # Confirm the decode happened rather than assuming it. If a future
        # Blender stops materialising on read, this becomes a clear failure
        # instead of a save that quietly writes nothing.
        has_data = getattr(image, "has_data", None)
        if has_data is False:
            return skill_error(
                f"Image has no pixel data to save: {image_name}",
                "The image could not be decoded, so there is nothing to write. "
                "This is typical under blender --background for images loaded from disk.",
                filepath=str(destination),
            )

        original = image.filepath
        try:
            if file_path:
                image.filepath = str(destination)
            image.save()
        except Exception as exc:
            return skill_exception(exc, message=f"Failed to save image {image_name}")
        finally:
            if file_path:
                image.filepath = original

        # Confirm the file exists rather than trusting the call: a save that
        # silently wrote nothing must be reported as a failure.
        if not destination.is_file():
            return skill_error(
                f"Image was not saved: {image_name}",
                f"Blender completed the save call but no file exists at '{destination}'.",
                filepath=str(destination),
            )

        return skill_success(
            f"Saved image {image.name}",
            image=_image_info(image),
            filepath=str(destination),
            size_bytes=destination.stat().st_size,
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
        exists_on_disk = bool(filepath) and Path(filepath).expanduser().is_file()

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
            is_udim=source == "UDIM" or len(tiles) > 1,
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


def set_light_ies(
    light_name: str,
    ies_file_path: Optional[str] = None,
    ies_strength: Optional[float] = None,
    clear: bool = False,
) -> dict:
    """Configure an IES texture on a spot light.

    IES describes a light's real-world falloff. Blender applies it to SPOT
    lights only, and older lights have no ``ies_file`` property, so both are
    checked and reported rather than written and ignored.

    Args:
        light_name: Spot light to configure.
        ies_file_path: Path to the ``.ies`` file.
        ies_strength: Multiplier for the IES profile.
        clear: Remove the current IES file instead of setting one.
    """
    try:
        import bpy

        obj, error = _resolve_light(bpy, light_name)
        if error:
            return error
        light = obj.data

        if getattr(light, "type", None) != "SPOT":
            return skill_error(
                f"{light_name} is not a spot light",
                f"IES textures apply to spot lights only; this light is {getattr(light, 'type', '?')}.",
            )
        if not hasattr(light, "ies_file"):
            return skill_error(
                "IES unavailable on this Blender version",
                f"{light_name} exposes no ies_file property, so an IES profile cannot be attached here.",
            )

        if clear:
            light.ies_file = ""
            return skill_success(
                f"Cleared IES on {light_name}",
                object_name=light_name,
                ies_file=None,
                prompt="Use set_light_ies with ies_file_path to attach a profile again.",
            )

        if ies_file_path:
            path = Path(ies_file_path).expanduser()
            if not path.is_file():
                return skill_error(f"IES file not found: {path}", f"No file at '{path}'.")
            try:
                light.ies_file = str(path)
            except Exception as exc:
                return skill_exception(exc, message=f"Failed to set IES file on {light_name}")

        if ies_strength is not None:
            if ies_strength < 0:
                return skill_error("Invalid IES strength", "ies_strength must not be negative.")
            light.ies_strength = float(ies_strength)

        return skill_success(
            f"Updated IES on {light_name}",
            object_name=light_name,
            ies_file=getattr(light, "ies_file", None) or None,
            ies_strength=getattr(light, "ies_strength", None),
            prompt="IES affects Cycles renders; use render_scene to see it.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message=f"Failed to set IES on {light_name}")


def set_light_linking(
    light_name: str,
    receiver_collection: Optional[str] = None,
    blocker_collection: Optional[str] = None,
    clear: bool = False,
) -> dict:
    """Restrict which objects a light affects using Blender 4.x light linking.

    Light linking makes a light only illuminate a chosen collection, and lets
    another collection block it. It was added in Blender 4.1 and is not
    present on lights in earlier versions, so availability is reported rather
    than assumed.

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
        light = obj.data

        linking = getattr(light, "light_linking", None)
        if linking is None:
            return skill_error(
                "Light linking unavailable on this Blender version",
                f"{light_name} exposes no light_linking property. Light linking was added in Blender 4.1.",
            )

        applied: Dict[str, Any] = {}
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
                setattr(linking, role, None)
                applied[role] = None
                continue
            collection = bpy.data.collections.get(collection_name)
            if collection is None:
                return skill_error(
                    f"Collection not found: {collection_name}",
                    f"No collection named '{collection_name}'.",
                )
            setattr(linking, role, collection)
            applied[role] = collection_name

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
