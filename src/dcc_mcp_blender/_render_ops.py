"""Blender render configuration operations.

Covers the gaps left by the ``blender-render`` skill's scene-level settings:
view layer AOV switches, denoise settings, output format configuration
including multi-layer EXR, border (region) rendering, and a consolidated
render status read.

All functions degrade to structured errors when ``bpy`` is unavailable so the
module stays importable outside Blender.
"""

from __future__ import annotations

from typing import Any, Sequence

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

from dcc_mcp_blender._scene_assembly_ops import _VIEW_LAYER_PASSES

# Output file formats exposed through `set_render_output`. Anything Blender
# accepts is allowed; this list only powers the helpful error message.
_IMAGE_FORMATS = (
    "PNG",
    "JPEG",
    "OPEN_EXR",
    "OPEN_EXR_MULTILAYER",
    "TIFF",
    "TARGA",
    "TARGA_RAW",
    "BMP",
    "HDR",
    "CINEON",
    "DPX",
    "WEBP",
)

_MULTILAYER_FORMAT = "OPEN_EXR_MULTILAYER"
_SINGLE_LAYER_EXR_FORMAT = "OPEN_EXR"

_COLOR_MODES = ("RGB", "RGBA", "BW", "RGBA_PREMUL")
_COLOR_DEPTHS = ("8", "10", "12", "16", "16F", "32F")
_EXR_CODECS = ("NONE", "PXR24", "ZIP", "PIZ", "RLE", "ZIPS", "B44", "B44A", "DWAA", "DWAB")
_DENOISERS = ("AUTO", "OPENIMAGEDENOISE", "OPTIX", "NONE")
_DENOISE_INPUT_PASSES = ("RGB", "RGB_ALBEDO", "RGB_ALBEDO_NORMAL")


def _iter_items(collection: Any) -> list:
    try:
        return list(collection)
    except TypeError:
        return []


def _resolve_scene(bpy: Any, scene_name: str | None) -> tuple:
    """Resolve a scene by name, falling back to the active scene."""
    if scene_name:
        scene = bpy.data.scenes.get(str(scene_name))
        if scene is None:
            return None, skill_error(f"Scene not found: {scene_name}", f"No scene named '{scene_name}'.")
        return scene, None
    scene = getattr(bpy.context, "scene", None)
    if scene is None:
        return None, skill_error("No active scene", "bpy.context.scene is unavailable.")
    return scene, None


def _resolve_view_layer(
    bpy: Any,
    scene: Any,
    view_layer_name: str | None,
    *,
    use_active: bool = True,
) -> tuple:
    """Resolve a view layer for *scene*.

    Args:
        bpy: The Blender module, used to read ``bpy.context.view_layer``.
        scene: Scene owning the view layers.
        view_layer_name: Explicit name; when omitted the active view layer wins.
        use_active: Honour ``bpy.context.view_layer`` when no name is given.
            Set to ``False`` for scenes other than the active one, where the
            context view layer may belong to a different scene.
    """
    layers = getattr(scene, "view_layers", None)
    if layers is None:
        return None, skill_error("No view layers", "The scene exposes no view layers.")
    if view_layer_name:
        layer = layers.get(str(view_layer_name))
        if layer is None:
            return (
                None,
                skill_error(
                    f"View layer not found: {view_layer_name}",
                    f"Scene '{getattr(scene, 'name', '')}' has no view layer named '{view_layer_name}'.",
                ),
            )
        return layer, None
    if use_active:
        active = getattr(getattr(bpy, "context", None), "view_layer", None)
        active_name = getattr(active, "name", None)
        if isinstance(active_name, str):
            active_layer = layers.get(active_name)
            if active_layer is not None:
                return active_layer, None
    layer = layers.get("ViewLayer") or next(iter(_iter_items(layers)), None)
    if layer is None:
        return None, skill_error("No view layer", "The scene has no view layer to configure.")
    return layer, None


def _pass_owner(layer: Any, pass_name: str) -> tuple:
    """Return the object that owns the ``use_pass_*`` flag for *pass_name*."""
    target_kind, attribute = _VIEW_LAYER_PASSES[pass_name]
    owner = layer if target_kind == "layer" else getattr(layer, "cycles", None)
    if owner is None or not hasattr(owner, attribute):
        return None, attribute
    return owner, attribute


def _pass_unavailable_reason(layer: Any, pass_name: str) -> str:
    """Explain why a pass cannot be set, naming the owning object.

    A missing Cycles add-on and an older Blender build look identical from the
    outside but need different handling, so the message separates them.
    """
    target_kind, attribute = _VIEW_LAYER_PASSES[pass_name]
    if target_kind == "cycles":
        if getattr(layer, "cycles", None) is None:
            return (
                f"{pass_name}: Cycles is not available on view layer '{getattr(layer, 'name', '')}' "
                f"(scene.{getattr(layer, 'name', '')}.cycles is unset)"
            )
        return f"{pass_name}: cycles.{attribute} is not exposed by this Blender build"
    return f"{pass_name}: layer.{attribute} is not exposed by this Blender build"


def _is_multilayer(render: Any) -> bool:
    """Return True when the output container is a multi-layer EXR.

    Multi-layer output is a property of the container format
    (``OPEN_EXR_MULTILAYER``), not of ``use_single_layer``, which only controls
    whether all layers are rendered.
    """
    settings = getattr(render, "image_settings", None)
    return getattr(settings, "file_format", None) == _MULTILAYER_FORMAT


def _read_pass_states(layer: Any, names: Sequence[str] | None = None) -> dict:
    wanted = list(names) if names else sorted(_VIEW_LAYER_PASSES)
    states: dict = {}
    for pass_name in wanted:
        owner, attribute = _pass_owner(layer, pass_name)
        states[pass_name] = bool(getattr(owner, attribute, False)) if owner is not None else None
    return states


def get_view_layer_passes(view_layer_name: str | None = None, scene_name: str | None = None) -> dict:
    """Report the enabled AOV passes for a view layer.

    Args:
        view_layer_name: Target view layer; defaults to the active one.
        scene_name: Target scene; defaults to the active scene.
    """
    try:
        import bpy

        scene, error = _resolve_scene(bpy, scene_name)
        if error:
            return error
        layer, error = _resolve_view_layer(bpy, scene, view_layer_name, use_active=scene_name is None)
        if error:
            return error
        states = _read_pass_states(layer)
        enabled = sorted(name for name, value in states.items() if value)
        return skill_success(
            f"View layer {layer.name}: {len(enabled)} pass(es) enabled",
            scene_name=getattr(scene, "name", scene_name),
            view_layer_name=layer.name,
            passes=states,
            enabled_passes=enabled,
            count=len(enabled),
            prompt="Use set_view_layer_passes to toggle passes on or off.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to read view layer passes")


def set_view_layer_passes(
    enable: Sequence[str] | None = None,
    disable: Sequence[str] | None = None,
    view_layer_name: str | None = None,
    scene_name: str | None = None,
) -> dict:
    """Turn view layer AOV passes on or off.

    Complements ``blender-scene-assembly``'s ``configure_view_layer``, which can
    only switch passes on. Unlisted passes keep their current state, so the
    call is idempotent and composable.

    Args:
        enable: Pass names to switch on.
        disable: Pass names to switch off.
        view_layer_name: Target view layer; defaults to the active one.
        scene_name: Target scene; defaults to the active scene.
    """
    requested_enable = [str(name) for name in (enable or [])]
    requested_disable = [str(name) for name in (disable or [])]
    if not requested_enable and not requested_disable:
        return skill_error(
            "No pass changes requested",
            "Provide enable and/or disable pass names; use get_view_layer_passes to list them.",
        )
    unknown = sorted(set(requested_enable + requested_disable) - set(_VIEW_LAYER_PASSES))
    if unknown:
        return skill_error(
            "Unsupported view-layer pass",
            f"Unsupported passes: {', '.join(unknown)}. Supported passes: {', '.join(sorted(_VIEW_LAYER_PASSES))}.",
        )
    conflict = sorted(set(requested_enable) & set(requested_disable))
    if conflict:
        return skill_error(
            "Conflicting pass changes",
            f"Passes listed in both enable and disable: {', '.join(conflict)}. "
            "List each pass in at most one of the two arguments.",
        )
    try:
        import bpy

        scene, error = _resolve_scene(bpy, scene_name)
        if error:
            return error
        layer, error = _resolve_view_layer(bpy, scene, view_layer_name, use_active=scene_name is None)
        if error:
            return error

        # Preflight every target before writing anything: a partially applied
        # batch is worse than a rejected one because the caller cannot tell
        # what changed.
        unavailable = []
        targets: list = []
        for pass_name, desired in (*((n, True) for n in requested_enable), *((n, False) for n in requested_disable)):
            owner, attribute = _pass_owner(layer, pass_name)
            if owner is None:
                unavailable.append(_pass_unavailable_reason(layer, pass_name))
            else:
                targets.append((owner, attribute, pass_name, desired))
        if unavailable:
            return skill_error(
                "View-layer pass unavailable",
                "Unavailable: " + "; ".join(unavailable) + ". No passes were changed.",
            )

        changes: list = []
        for owner, attribute, pass_name, desired in targets:
            if bool(getattr(owner, attribute, False)) != desired:
                setattr(owner, attribute, desired)
                changes.append({"pass": pass_name, "enabled": desired})
            else:
                changes.append({"pass": pass_name, "enabled": desired, "changed": False})

        states = _read_pass_states(layer)
        return skill_success(
            f"Updated {len(changes)} pass(es) on {layer.name}",
            scene_name=getattr(scene, "name", scene_name),
            view_layer_name=layer.name,
            changes=changes,
            enabled_passes=sorted(name for name, value in states.items() if value),
            prompt="Use get_view_layer_passes to verify, then set_render_output for a multi-layer EXR.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to set view layer passes")


def set_render_denoise(
    enabled: bool | None = None,
    denoiser: str | None = None,
    input_passes: str | None = None,
    prefilter: str | None = None,
    use_gpu: bool | None = None,
    scene_name: str | None = None,
) -> dict:
    """Configure Cycles denoising for a scene.

    Args:
        enabled: Turn scene-level denoising on or off.
        denoiser: One of ``AUTO``, ``OPENIMAGEDENOISE``, ``OPTIX``, ``NONE``.
        input_passes: ``RGB``, ``RGB_ALBEDO``, or ``RGB_ALBEDO_NORMAL``.
        prefilter: Denoising prefilter mode reported by the Cycles add-on.
        use_gpu: Request GPU denoising (OPTIX only).
        scene_name: Target scene; defaults to the active scene.
    """
    if enabled is None and denoiser is None and input_passes is None and prefilter is None and use_gpu is None:
        return skill_error(
            "No denoise settings supplied",
            "Provide at least one of enabled, denoiser, input_passes, prefilter, use_gpu.",
        )
    if denoiser is not None and str(denoiser).upper() not in _DENOISERS:
        return skill_error(
            f"Unsupported denoiser: {denoiser}",
            f"Supported denoisers: {', '.join(_DENOISERS)}.",
        )
    if input_passes is not None and str(input_passes).upper() not in _DENOISE_INPUT_PASSES:
        return skill_error(
            f"Unsupported denoise input passes: {input_passes}",
            f"Supported values: {', '.join(_DENOISE_INPUT_PASSES)}.",
        )
    try:
        import bpy

        scene, error = _resolve_scene(bpy, scene_name)
        if error:
            return error
        cycles = getattr(scene, "cycles", None)
        if cycles is None:
            return skill_error(
                "Cycles settings unavailable",
                "Denoise settings require the Cycles render engine add-on.",
            )
        if not hasattr(cycles, "use_denoising"):
            return skill_error(
                "Denoising unavailable in this Blender version",
                "scene.cycles.use_denoising is not exposed by this Blender build.",
            )

        # Preflight every setting before writing, so an unsupported one cannot
        # leave the rest half-applied.
        pending: list = []
        if enabled is not None:
            pending.append(("use_denoising", "scene.cycles.use_denoising", bool(enabled)))
        if denoiser is not None:
            pending.append(("denoiser", "scene.cycles.denoiser", str(denoiser).upper()))
        if input_passes is not None:
            pending.append(("denoising_input_passes", "scene.cycles.denoising_input_passes", str(input_passes).upper()))
        if prefilter is not None:
            pending.append(("denoising_prefilter", "scene.cycles.denoising_prefilter", str(prefilter).upper()))
        if use_gpu is not None:
            pending.append(("use_denoising_use_gpu", "scene.cycles.use_denoising_use_gpu", bool(use_gpu)))
        unsupported = [path for _key, path, _value in pending if not hasattr(cycles, path.rsplit(".", 1)[-1])]
        if unsupported:
            return skill_error(
                "Denoise setting unavailable",
                "Not exposed by this Blender build: " + ", ".join(unsupported) + ". Nothing was changed.",
            )

        applied: dict = {}
        for key, _path, value in pending:
            setattr(cycles, key, value)
            applied[key] = getattr(cycles, key, value)
        if enabled is not None and "denoising" in _VIEW_LAYER_PASSES:
            layer, layer_error = _resolve_view_layer(bpy, scene, None, use_active=scene_name is None)
            if layer_error is None:
                owner, attribute = _pass_owner(layer, "denoising")
                if owner is not None:
                    setattr(owner, attribute, bool(enabled))

        return skill_success(
            f"Updated denoise settings for {getattr(scene, 'name', scene_name)}",
            scene_name=getattr(scene, "name", scene_name),
            engine=getattr(scene.render, "engine", None),
            applied=applied,
            use_denoising=getattr(cycles, "use_denoising", None),
            denoiser=getattr(cycles, "denoiser", None),
            prompt="Cycles-only; EEVEE ignores these settings. Use get_render_status to review.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to set denoise settings")


def get_render_output(scene_name: str | None = None) -> dict:
    """Report the render output configuration for a scene."""
    try:
        import bpy

        scene, error = _resolve_scene(bpy, scene_name)
        if error:
            return error
        render = scene.render
        settings = render.image_settings
        return skill_success(
            f"Render output for {getattr(scene, 'name', scene_name)}",
            scene_name=getattr(scene, "name", scene_name),
            filepath=getattr(render, "filepath", None),
            file_format=getattr(settings, "file_format", None),
            color_mode=getattr(settings, "color_mode", None),
            color_depth=getattr(settings, "color_depth", None),
            exr_codec=getattr(settings, "exr_codec", None),
            use_preview=getattr(settings, "use_preview", None),
            use_single_layer=getattr(render, "use_single_layer", None),
            multilayer=_is_multilayer(render),
            use_file_extension=getattr(render, "use_file_extension", None),
            use_overwrite=getattr(render, "use_overwrite", None),
            use_placeholder=getattr(render, "use_placeholder", None),
            resolution=(getattr(render, "resolution_x", None), getattr(render, "resolution_y", None)),
            resolution_percentage=getattr(render, "resolution_percentage", None),
            prompt="Use set_render_output to change output paths, formats, or EXR layer mode.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to read render output settings")


def set_render_output(
    filepath: str | None = None,
    file_format: str | None = None,
    color_mode: str | None = None,
    color_depth: str | None = None,
    exr_codec: str | None = None,
    multilayer: bool | None = None,
    use_preview: bool | None = None,
    use_file_extension: bool | None = None,
    use_overwrite: bool | None = None,
    use_placeholder: bool | None = None,
    scene_name: str | None = None,
) -> dict:
    """Configure render output path, format, and multi-layer EXR behaviour.

    Args:
        filepath: Output path; may include a trailing frame placeholder.
        file_format: Image format, for example ``OPEN_EXR_MULTILAYER``.
        color_mode: ``RGB``, ``RGBA``, ``BW``, or ``RGBA_PREMUL``.
        color_depth: ``8``, ``10``, ``12``, ``16``, ``16F``, or ``32F``.
        exr_codec: EXR compression codec, for example ``DWAA``.
        multilayer: ``True`` switches the container to ``OPEN_EXR_MULTILAYER`` and
            renders every layer into that single file. ``False`` drops back to
            ``OPEN_EXR`` when the container was multi-layer and renders every
            layer. Applied after ``file_format``, so it wins if both are given.
        use_preview: Write a JPG preview image next to the output when
            rendering animations (``image_settings.use_preview``).
        use_file_extension: Append the format extension to the output path.
        use_overwrite: Overwrite existing files.
        use_placeholder: Create placeholder files while rendering.
        scene_name: Target scene; defaults to the active scene.
    """
    if all(
        value is None
        for value in (
            filepath,
            file_format,
            color_mode,
            color_depth,
            exr_codec,
            multilayer,
            use_preview,
            use_file_extension,
            use_overwrite,
            use_placeholder,
        )
    ):
        return skill_error(
            "No output settings supplied",
            "Provide at least one output setting; use get_render_output to inspect the current state.",
        )
    if file_format is not None and str(file_format).upper() not in _IMAGE_FORMATS:
        return skill_error(
            f"Unsupported output format: {file_format}",
            f"Supported formats: {', '.join(_IMAGE_FORMATS)}.",
        )
    if color_mode is not None and str(color_mode).upper() not in _COLOR_MODES:
        return skill_error(
            f"Unsupported color mode: {color_mode}",
            f"Supported modes: {', '.join(_COLOR_MODES)}.",
        )
    if color_depth is not None and str(color_depth).upper() not in _COLOR_DEPTHS:
        return skill_error(
            f"Unsupported color depth: {color_depth}",
            f"Supported depths: {', '.join(_COLOR_DEPTHS)}.",
        )
    if exr_codec is not None and str(exr_codec).upper() not in _EXR_CODECS:
        return skill_error(
            f"Unsupported EXR codec: {exr_codec}",
            f"Supported codecs: {', '.join(_EXR_CODECS)}.",
        )
    try:
        import bpy

        scene, error = _resolve_scene(bpy, scene_name)
        if error:
            return error
        render = scene.render
        settings = render.image_settings

        # Preflight every property before writing, so an unavailable one cannot
        # leave the rest half-applied. The host object is named explicitly
        # alongside the reported path: deriving it from the path string would
        # give two sources of truth that can drift, and a drifted host makes a
        # usable property look unsupported.
        unsupported = [
            path
            for requested, host, attribute, path in (
                (color_mode, settings, "color_mode", "scene.render.image_settings.color_mode"),
                (color_depth, settings, "color_depth", "scene.render.image_settings.color_depth"),
                (exr_codec, settings, "exr_codec", "scene.render.image_settings.exr_codec"),
                (use_preview, settings, "use_preview", "scene.render.image_settings.use_preview"),
                (multilayer, render, "use_single_layer", "scene.render.use_single_layer"),
            )
            if requested is not None and not hasattr(host, attribute)
        ]
        if unsupported:
            return skill_error(
                "Output setting unavailable",
                "Not exposed by this Blender build: " + ", ".join(unsupported) + ". Nothing was changed.",
            )

        applied: dict = {}
        if filepath is not None:
            render.filepath = str(filepath)
            applied["filepath"] = str(filepath)
        if file_format is not None:
            settings.file_format = str(file_format).upper()
            applied["file_format"] = settings.file_format
        if color_mode is not None:
            settings.color_mode = str(color_mode).upper()
            applied["color_mode"] = settings.color_mode
        if color_depth is not None:
            settings.color_depth = str(color_depth).upper()
            applied["color_depth"] = settings.color_depth
        if exr_codec is not None:
            settings.exr_codec = str(exr_codec).upper()
            applied["exr_codec"] = settings.exr_codec
        if multilayer is not None:
            # Multi-layer output is a container format, not a switch on
            # use_single_layer: use_single_layer only decides whether every
            # layer is rendered. Both have to move together.
            if bool(multilayer):
                settings.file_format = _MULTILAYER_FORMAT
                render.use_single_layer = False
            else:
                if _is_multilayer(render):
                    settings.file_format = _SINGLE_LAYER_EXR_FORMAT
                render.use_single_layer = True
            applied["multilayer"] = bool(multilayer)
            applied["file_format"] = settings.file_format
        # use_preview lives on ImageFormatSettings alongside the other image
        # options; the remaining flags are RenderSettings options.
        if use_preview is not None:
            settings.use_preview = bool(use_preview)
            applied["use_preview"] = bool(use_preview)
        for flag, attribute in (
            (use_file_extension, "use_file_extension"),
            (use_overwrite, "use_overwrite"),
            (use_placeholder, "use_placeholder"),
        ):
            if flag is not None:
                setattr(render, attribute, bool(flag))
                applied[attribute] = bool(flag)

        return skill_success(
            f"Updated render output for {getattr(scene, 'name', scene_name)}",
            scene_name=getattr(scene, "name", scene_name),
            applied=applied,
            filepath=getattr(render, "filepath", None),
            file_format=getattr(settings, "file_format", None),
            multilayer=_is_multilayer(render),
            use_single_layer=getattr(render, "use_single_layer", None),
            prompt="Use set_view_layer_passes to choose the AOVs written into a multi-layer EXR.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to set render output settings")


def set_render_region(
    min_x: float = 0.0,
    min_y: float = 0.0,
    max_x: float = 1.0,
    max_y: float = 1.0,
    enabled: bool = True,
    scene_name: str | None = None,
) -> dict:
    """Enable and configure border (region) rendering.

    Coordinates are normalised: (0, 0) is the bottom-left of the frame and
    (1, 1) the top-right.

    Args:
        min_x: Left edge of the region.
        min_y: Bottom edge of the region.
        max_x: Right edge of the region.
        max_y: Top edge of the region.
        enabled: ``False`` disables border rendering but keeps the coordinates.
        scene_name: Target scene; defaults to the active scene.
    """
    try:
        values = [float(min_x), float(min_y), float(max_x), float(max_y)]
    except (TypeError, ValueError):
        return skill_error(
            "Invalid render region",
            "min_x, min_y, max_x, and max_y must be numbers in the 0..1 range.",
        )
    if any(value < 0.0 or value > 1.0 for value in values):
        return skill_error(
            "Invalid render region",
            "Region coordinates must be normalised values between 0 and 1.",
        )
    if values[2] <= values[0] or values[3] <= values[1]:
        return skill_error(
            "Invalid render region",
            "max_x must be greater than min_x, and max_y greater than min_y.",
        )
    try:
        import bpy

        scene, error = _resolve_scene(bpy, scene_name)
        if error:
            return error
        render = scene.render
        if not hasattr(render, "use_border"):
            return skill_error(
                "Border rendering unavailable in this Blender version",
                "scene.render.use_border is not exposed by this Blender build.",
            )
        render.border_min_x, render.border_min_y = values[0], values[1]
        render.border_max_x, render.border_max_y = values[2], values[3]
        render.use_border = bool(enabled)
        return skill_success(
            f"{'Enabled' if enabled else 'Disabled'} render region on {getattr(scene, 'name', scene_name)}",
            scene_name=getattr(scene, "name", scene_name),
            enabled=bool(enabled),
            region={
                "min_x": values[0],
                "min_y": values[1],
                "max_x": values[2],
                "max_y": values[3],
            },
            prompt="Use get_render_status to confirm the region before rendering.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to set the render region")


def clear_render_region(scene_name: str | None = None) -> dict:
    """Disable border rendering and reset the region to the full frame."""
    try:
        import bpy

        scene, error = _resolve_scene(bpy, scene_name)
        if error:
            return error
        render = scene.render
        if not hasattr(render, "use_border"):
            return skill_error(
                "Border rendering unavailable in this Blender version",
                "scene.render.use_border is not exposed by this Blender build.",
            )
        render.border_min_x, render.border_min_y = 0.0, 0.0
        render.border_max_x, render.border_max_y = 1.0, 1.0
        render.use_border = False
        return skill_success(
            f"Cleared render region on {getattr(scene, 'name', scene_name)}",
            scene_name=getattr(scene, "name", scene_name),
            enabled=False,
            region={"min_x": 0.0, "min_y": 0.0, "max_x": 1.0, "max_y": 1.0},
            prompt="Use set_render_region to render a sub-rectangle again.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to clear the render region")


def get_render_status(scene_name: str | None = None, view_layer_name: str | None = None) -> dict:
    """Report animation frame range and the render state that affects output.

    Args:
        scene_name: Target scene; defaults to the active scene.
        view_layer_name: View layer whose passes are summarised; defaults to the active one.
    """
    try:
        import bpy

        scene, error = _resolve_scene(bpy, scene_name)
        if error:
            return error
        render = scene.render
        settings = render.image_settings
        frame_start = getattr(scene, "frame_start", None)
        frame_end = getattr(scene, "frame_end", None)
        frame_step = getattr(scene, "frame_step", None)
        frame_count = None
        if isinstance(frame_start, int) and isinstance(frame_end, int) and isinstance(frame_step, int):
            if frame_step > 0 and frame_end >= frame_start:
                frame_count = ((frame_end - frame_start) // frame_step) + 1

        layer, layer_error = _resolve_view_layer(bpy, scene, view_layer_name, use_active=scene_name is None)
        if layer_error:
            return layer_error
        passes = _read_pass_states(layer, sorted(_VIEW_LAYER_PASSES))

        cycles = getattr(scene, "cycles", None)
        return skill_success(
            f"Render status for {getattr(scene, 'name', scene_name)}",
            scene_name=getattr(scene, "name", scene_name),
            engine=getattr(render, "engine", None),
            frame_start=frame_start,
            frame_end=frame_end,
            frame_step=frame_step,
            frame_current=getattr(scene, "frame_current", None),
            frame_count=frame_count,
            fps=getattr(render, "fps", None),
            resolution=(getattr(render, "resolution_x", None), getattr(render, "resolution_y", None)),
            resolution_percentage=getattr(render, "resolution_percentage", None),
            active_camera=getattr(getattr(scene, "camera", None), "name", None),
            has_active_camera=getattr(scene, "camera", None) is not None,
            filepath=getattr(render, "filepath", None),
            file_format=getattr(settings, "file_format", None),
            multilayer=_is_multilayer(render),
            border_enabled=getattr(render, "use_border", None),
            border_region={
                "min_x": getattr(render, "border_min_x", None),
                "min_y": getattr(render, "border_min_y", None),
                "max_x": getattr(render, "border_max_x", None),
                "max_y": getattr(render, "border_max_y", None),
            },
            use_denoising=getattr(cycles, "use_denoising", None),
            denoiser=getattr(cycles, "denoiser", None),
            view_layer_name=getattr(layer, "name", None) if layer_error is None else None,
            enabled_passes=sorted(name for name, value in passes.items() if value),
            view_layer_count=len(_iter_items(getattr(scene, "view_layers", []))),
            prompt="Use set_render_output, set_render_region, or set_render_denoise to adjust the plan.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to read render status")
