"""Photographic Cycles render profiles for Blender 5.x."""

from __future__ import annotations

import math
from typing import Any, Iterable

from dcc_mcp_core.skill import skill_error, skill_exception, skill_success

from dcc_mcp_blender._image_format import set_image_format
from dcc_mcp_blender._render_ops import _resolve_scene

PROFILE_NAMES = ("PREVIEW", "FINAL")
SCENE_KINDS = ("EXTERIOR", "INTERIOR")
DEVICE_BACKENDS = ("AUTO", "OPTIX", "CUDA", "HIP", "ONEAPI", "METAL", "CPU")
GPU_BACKENDS = ("OPTIX", "METAL", "CUDA", "HIP", "ONEAPI")
_PROFILE_VERSION = "dcc-mcp-blender.render-profile.v1"

_BASE_PROFILE = {
    "engine": "CYCLES",
    "resolution_x": 3840,
    "resolution_y": 2160,
    "fps": 24,
    "fps_base": 1.0,
    "adaptive_sampling": True,
    "adaptive_threshold": 0.02,
    "denoising": True,
    "denoiser": "OPENIMAGEDENOISE",
    "denoising_input_passes": "RGB_ALBEDO_NORMAL",
    "denoising_prefilter": "ACCURATE",
    "denoising_use_gpu": False,
    "denoising_store_passes": True,
    "max_bounces": 7,
    "diffuse_bounces": 4,
    "glossy_bounces": 4,
    "transmission_bounces": 6,
    "transparent_max_bounces": 12,
    "sample_clamp_direct": 0.0,
    "sample_clamp_indirect": 6.0,
    "caustics_reflective": False,
    "caustics_refractive": False,
    "blur_glossy": 0.6,
    "filter_width": 1.5,
    "render_filter_size": 1.5,
    "motion_blur": True,
    "motion_blur_shutter": 0.5,
    "motion_blur_position": "CENTER",
    "persistent_data": True,
    "file_format": "JPEG",
    "color_mode": "RGB",
    "color_depth": "8",
    "quality": 96,
    "view_transform": "AgX",
    "look": "AgX - Medium High Contrast",
    "exposure": 0.0,
}


def _profile_values(profile_name: str, scene_kind: str, samples: int | None) -> dict:
    profile = str(profile_name or "").strip().upper()
    kind = str(scene_kind or "EXTERIOR").strip().upper()
    if profile not in PROFILE_NAMES:
        raise ValueError("profile_name must be PREVIEW or FINAL")
    if kind not in SCENE_KINDS:
        raise ValueError("scene_kind must be EXTERIOR or INTERIOR")
    if samples is not None:
        if isinstance(samples, bool) or not isinstance(samples, int) or samples < 1:
            raise ValueError("samples must be a positive integer")

    values = dict(_BASE_PROFILE)
    if profile == "PREVIEW":
        values.update(resolution_percentage=25, samples=samples or 32)
    else:
        values.update(
            resolution_percentage=100,
            samples=samples or (112 if kind == "INTERIOR" else 64),
        )
    return values


def _resolve_device_backend(requested: str, available: Iterable[str], allow_cpu_fallback: bool) -> tuple[str, bool]:
    requested_name = str(requested or "AUTO").strip().upper()
    if requested_name not in DEVICE_BACKENDS:
        raise ValueError("device_backend must be one of: {}".format(", ".join(DEVICE_BACKENDS)))
    available_names = {str(value).upper() for value in available}
    available_names.add("CPU")
    if requested_name == "AUTO":
        for backend in GPU_BACKENDS:
            if backend in available_names:
                return backend, False
        if allow_cpu_fallback:
            return "CPU", True
        raise ValueError("No supported GPU backend is available and CPU fallback is disabled")
    if requested_name == "CPU":
        return "CPU", False
    if requested_name not in available_names:
        raise ValueError(
            "Requested Cycles backend {} is unavailable. Available backends: {}".format(
                requested_name, ", ".join(sorted(available_names))
            )
        )
    return requested_name, False


def _cycles_preferences(bpy: Any) -> Any | None:
    preferences = getattr(getattr(bpy, "context", None), "preferences", None)
    addons = getattr(preferences, "addons", None)
    getter = getattr(addons, "get", None)
    addon = getter("cycles") if callable(getter) else None
    return getattr(addon, "preferences", None) if addon is not None else None


def _as_device_list(value: Any) -> list[Any]:
    try:
        return list(value or [])
    except TypeError:
        return []


def _device_identity(device: Any, backend_hint: str | None = None) -> tuple[str, str]:
    backend = str(getattr(device, "type", backend_hint or "")).strip().upper()
    identifier = getattr(device, "id", None)
    if identifier in (None, ""):
        identifier = getattr(device, "name", "")
    return backend, str(identifier)


def _device_objects(preferences: Any) -> tuple[list[Any], list[Any], bool]:
    """Return saved objects, live objects and whether live enumeration was available."""
    refresh_devices = getattr(preferences, "refresh_devices", None)
    get_devices = getattr(preferences, "get_devices", None)
    refresh = refresh_devices if callable(refresh_devices) else get_devices
    if callable(refresh):
        try:
            refresh()
        except Exception:
            pass
    saved_devices = _as_device_list(getattr(preferences, "devices", []))

    get_devices_for_type = getattr(preferences, "get_devices_for_type", None)
    if not callable(get_devices_for_type):
        return saved_devices, saved_devices, False

    live_devices = []
    seen: set[tuple[str, str]] = set()
    for backend in GPU_BACKENDS:
        try:
            candidates = _as_device_list(get_devices_for_type(backend))
        except Exception:
            candidates = []
        for device in candidates:
            identity = _device_identity(device, backend)
            if identity in seen:
                continue
            seen.add(identity)
            live_devices.append(device)
    return saved_devices, live_devices, True


def _device_inventory(preferences: Any | None) -> dict:
    if preferences is None:
        return {
            "compute_device_type": None,
            "devices": [],
            "available_backends": ["CPU"],
            "gpu_backends": [],
            "active_devices": [],
            "active_device_count": 0,
            "live_device_enumeration": False,
        }

    saved_devices, live_devices, live_enumeration = _device_objects(preferences)
    if not live_enumeration:
        live_devices = saved_devices

    saved_by_identity = {}
    saved_by_name = {}
    for device in saved_devices:
        backend, identifier = _device_identity(device)
        saved_by_identity[(backend, identifier)] = device
        name = str(getattr(device, "name", ""))
        if name:
            saved_by_name[(backend, name)] = device

    devices = []
    for device in live_devices:
        backend, identifier = _device_identity(device)
        saved = saved_by_identity.get((backend, identifier))
        if saved is None:
            saved = saved_by_name.get((backend, str(getattr(device, "name", ""))))
        source = saved if saved is not None else device
        available = getattr(device, "available", None)
        if available is None:
            available = not bool(getattr(device, "has_error", False))
        devices.append(
            {
                "id": str(getattr(device, "id", "")),
                "name": str(getattr(device, "name", "")),
                "type": backend,
                "use": bool(getattr(source, "use", False)),
                "live": True,
                "meets_driver_requirement": bool(available),
            }
        )

    backends = {
        device["type"]
        for device in devices
        if device["type"] in GPU_BACKENDS and device["meets_driver_requirement"]
    }
    active_devices = [
        device
        for device in devices
        if device["live"] and device["use"] and device["meets_driver_requirement"]
    ]
    return {
        "compute_device_type": str(getattr(preferences, "compute_device_type", "NONE")).upper(),
        "devices": devices,
        "available_backends": sorted(backends | {"CPU"}),
        "gpu_backends": sorted(backends),
        "active_devices": active_devices,
        "active_device_count": len(active_devices),
        "live_device_enumeration": live_enumeration,
    }


def _resolve_view_layer(scene: Any) -> Any | None:
    layers = getattr(scene, "view_layers", None)
    if layers is None:
        return None
    getter = getattr(layers, "get", None)
    if callable(getter):
        layer = getter("ViewLayer")
        if layer is not None:
            return layer
    try:
        return next(iter(layers), None)
    except TypeError:
        return None


def _profile_targets(scene: Any, values: dict) -> list[tuple[Any, str, Any, str]]:
    render = scene.render
    cycles = scene.cycles
    image_settings = render.image_settings
    view_settings = scene.view_settings
    layer = _resolve_view_layer(scene)

    targets = [
        (render, "engine", values["engine"], "scene.render.engine"),
        (render, "resolution_x", values["resolution_x"], "scene.render.resolution_x"),
        (render, "resolution_y", values["resolution_y"], "scene.render.resolution_y"),
        (render, "resolution_percentage", values["resolution_percentage"], "scene.render.resolution_percentage"),
        (render, "fps", values["fps"], "scene.render.fps"),
        (render, "fps_base", values["fps_base"], "scene.render.fps_base"),
        (render, "filter_size", values["render_filter_size"], "scene.render.filter_size"),
        (render, "use_motion_blur", values["motion_blur"], "scene.render.use_motion_blur"),
        (render, "motion_blur_shutter", values["motion_blur_shutter"], "scene.render.motion_blur_shutter"),
        (render, "motion_blur_position", values["motion_blur_position"], "scene.render.motion_blur_position"),
        (render, "use_persistent_data", values["persistent_data"], "scene.render.use_persistent_data"),
        (cycles, "samples", values["samples"], "scene.cycles.samples"),
        (cycles, "use_adaptive_sampling", values["adaptive_sampling"], "scene.cycles.use_adaptive_sampling"),
        (cycles, "adaptive_threshold", values["adaptive_threshold"], "scene.cycles.adaptive_threshold"),
        (cycles, "use_denoising", values["denoising"], "scene.cycles.use_denoising"),
        (cycles, "denoiser", values["denoiser"], "scene.cycles.denoiser"),
        (
            cycles,
            "denoising_input_passes",
            values["denoising_input_passes"],
            "scene.cycles.denoising_input_passes",
        ),
        (cycles, "denoising_prefilter", values["denoising_prefilter"], "scene.cycles.denoising_prefilter"),
        (cycles, "denoising_use_gpu", values["denoising_use_gpu"], "scene.cycles.denoising_use_gpu"),
        (cycles, "max_bounces", values["max_bounces"], "scene.cycles.max_bounces"),
        (cycles, "diffuse_bounces", values["diffuse_bounces"], "scene.cycles.diffuse_bounces"),
        (cycles, "glossy_bounces", values["glossy_bounces"], "scene.cycles.glossy_bounces"),
        (cycles, "transmission_bounces", values["transmission_bounces"], "scene.cycles.transmission_bounces"),
        (
            cycles,
            "transparent_max_bounces",
            values["transparent_max_bounces"],
            "scene.cycles.transparent_max_bounces",
        ),
        (cycles, "sample_clamp_direct", values["sample_clamp_direct"], "scene.cycles.sample_clamp_direct"),
        (cycles, "sample_clamp_indirect", values["sample_clamp_indirect"], "scene.cycles.sample_clamp_indirect"),
        (cycles, "caustics_reflective", values["caustics_reflective"], "scene.cycles.caustics_reflective"),
        (cycles, "caustics_refractive", values["caustics_refractive"], "scene.cycles.caustics_refractive"),
        (cycles, "blur_glossy", values["blur_glossy"], "scene.cycles.blur_glossy"),
        (cycles, "filter_width", values["filter_width"], "scene.cycles.filter_width"),
        (image_settings, "color_mode", values["color_mode"], "scene.render.image_settings.color_mode"),
        (image_settings, "color_depth", values["color_depth"], "scene.render.image_settings.color_depth"),
        (image_settings, "quality", values["quality"], "scene.render.image_settings.quality"),
        (view_settings, "view_transform", values["view_transform"], "scene.view_settings.view_transform"),
        (view_settings, "look", values["look"], "scene.view_settings.look"),
        (view_settings, "exposure", values["exposure"], "scene.view_settings.exposure"),
    ]
    if layer is not None and hasattr(getattr(layer, "cycles", None), "denoising_store_passes"):
        targets.append(
            (
                layer.cycles,
                "denoising_store_passes",
                values["denoising_store_passes"],
                "view_layer.cycles.denoising_store_passes",
            )
        )
    return targets


def _missing_targets(targets: Iterable[tuple[Any, str, Any, str]]) -> list[str]:
    return [path for owner, attribute, _value, path in targets if owner is None or not hasattr(owner, attribute)]


def _snapshot(targets: Iterable[tuple[Any, str, Any, str]], image_settings: Any) -> list[tuple[Any, str, Any]]:
    snapshot: list[tuple[Any, str, Any]] = []
    owners_seen: set[tuple[int, str]] = set()
    for owner, attribute, _value, _path in targets:
        if owner is None or (id(owner), attribute) in owners_seen:
            continue
        owners_seen.add((id(owner), attribute))
        snapshot.append((owner, attribute, getattr(owner, attribute)))
    if hasattr(image_settings, "file_format") and (id(image_settings), "file_format") not in owners_seen:
        snapshot.append((image_settings, "file_format", getattr(image_settings, "file_format")))
    if hasattr(image_settings, "media_type"):
        snapshot.append((image_settings, "media_type", getattr(image_settings, "media_type")))
    return snapshot


def _restore(snapshot: Iterable[tuple[Any, str, Any]], image_settings: Any) -> None:
    values = list(snapshot)
    for attribute in ("media_type", "file_format"):
        for owner, saved_attribute, value in values:
            if owner is not image_settings or saved_attribute != attribute:
                continue
            try:
                setattr(owner, saved_attribute, value)
            except Exception:
                pass
            break
    for owner, attribute, value in values:
        if owner is image_settings and attribute in {"file_format", "media_type"}:
            continue
        try:
            setattr(owner, attribute, value)
        except Exception:
            pass


def _current_values(scene: Any, layer: Any | None, inventory: dict) -> dict:
    render = scene.render
    cycles = scene.cycles
    image_settings = render.image_settings
    view_settings = scene.view_settings
    backend = inventory.get("compute_device_type") or "NONE"
    scene_device = str(getattr(cycles, "device", "CPU")).upper()
    if scene_device == "CPU":
        backend = "CPU"
    return {
        "engine": getattr(render, "engine", None),
        "resolution_x": getattr(render, "resolution_x", None),
        "resolution_y": getattr(render, "resolution_y", None),
        "resolution_percentage": getattr(render, "resolution_percentage", None),
        "fps": getattr(render, "fps", None),
        "fps_base": getattr(render, "fps_base", None),
        "render_filter_size": getattr(render, "filter_size", None),
        "motion_blur": getattr(render, "use_motion_blur", None),
        "motion_blur_shutter": getattr(render, "motion_blur_shutter", None),
        "motion_blur_position": getattr(render, "motion_blur_position", None),
        "persistent_data": getattr(render, "use_persistent_data", None),
        "samples": getattr(cycles, "samples", None),
        "adaptive_sampling": getattr(cycles, "use_adaptive_sampling", None),
        "adaptive_threshold": getattr(cycles, "adaptive_threshold", None),
        "denoising": getattr(cycles, "use_denoising", None),
        "denoiser": getattr(cycles, "denoiser", None),
        "denoising_input_passes": getattr(cycles, "denoising_input_passes", None),
        "denoising_prefilter": getattr(cycles, "denoising_prefilter", None),
        "denoising_use_gpu": getattr(cycles, "denoising_use_gpu", None),
        "denoising_store_passes": getattr(getattr(layer, "cycles", None), "denoising_store_passes", None),
        "max_bounces": getattr(cycles, "max_bounces", None),
        "diffuse_bounces": getattr(cycles, "diffuse_bounces", None),
        "glossy_bounces": getattr(cycles, "glossy_bounces", None),
        "transmission_bounces": getattr(cycles, "transmission_bounces", None),
        "transparent_max_bounces": getattr(cycles, "transparent_max_bounces", None),
        "sample_clamp_direct": getattr(cycles, "sample_clamp_direct", None),
        "sample_clamp_indirect": getattr(cycles, "sample_clamp_indirect", None),
        "caustics_reflective": getattr(cycles, "caustics_reflective", None),
        "caustics_refractive": getattr(cycles, "caustics_refractive", None),
        "blur_glossy": getattr(cycles, "blur_glossy", None),
        "filter_width": getattr(cycles, "filter_width", None),
        "file_format": getattr(image_settings, "file_format", None),
        "color_mode": getattr(image_settings, "color_mode", None),
        "color_depth": getattr(image_settings, "color_depth", None),
        "quality": getattr(image_settings, "quality", None),
        "view_transform": getattr(view_settings, "view_transform", None),
        "look": getattr(view_settings, "look", None),
        "exposure": getattr(view_settings, "exposure", None),
        "scene_device": scene_device,
        "device_backend": backend,
        "active_devices": inventory.get("active_devices", []),
        "active_device_count": inventory.get("active_device_count", 0),
        "live_device_enumeration": inventory.get("live_device_enumeration", False),
    }


def _values_match(actual: Any, expected: Any) -> bool:
    if isinstance(expected, float) or isinstance(actual, float):
        try:
            return math.isclose(float(actual), float(expected), rel_tol=1e-6, abs_tol=1e-6)
        except (TypeError, ValueError):
            return False
    return actual == expected


def _profile_issues(actual: dict, expected: dict, backend: str) -> list[dict]:
    issues = []
    for key, value in expected.items():
        if key not in actual:
            issues.append(
                {
                    "code": "RENDER_PROFILE_UNSUPPORTED",
                    "severity": "error",
                    "field": key,
                    "expected": value,
                    "actual": None,
                    "message": "The current Blender build did not expose this property.",
                }
            )
            continue
        if actual[key] is None:
            issues.append(
                {
                    "code": "RENDER_PROFILE_UNSUPPORTED",
                    "severity": "error",
                    "field": key,
                    "expected": value,
                    "actual": None,
                    "message": "The current Blender build did not expose this property.",
                }
            )
            continue
        if not _values_match(actual[key], value):
            issues.append(
                {
                    "code": "RENDER_PROFILE_MISMATCH",
                    "severity": "error",
                    "field": key,
                    "expected": value,
                    "actual": actual[key],
                }
            )
    if not _values_match(actual.get("device_backend"), backend):
        issues.append(
            {
                "code": "RENDER_DEVICE_MISMATCH",
                "severity": "error",
                "field": "device_backend",
                "expected": backend,
                "actual": actual.get("device_backend"),
            }
        )
    active_devices = [
        device for device in actual.get("active_devices", []) if device.get("type") == backend
    ]
    if backend in GPU_BACKENDS and not active_devices:
        issues.append(
            {
                "code": "RENDER_DEVICE_INACTIVE",
                "severity": "error",
                "field": "active_devices",
                "expected": "at least one enabled live device for {}".format(backend),
                "actual": active_devices,
                "message": "The selected GPU backend has no enabled live device.",
            }
        )
    return issues


def get_render_capabilities(scene_name: str | None = None) -> dict:
    """Report Blender, Cycles and available compute-device capabilities."""
    try:
        import bpy

        scene, error = _resolve_scene(bpy, scene_name)
        if error:
            return error
        cycles = getattr(scene, "cycles", None)
        if cycles is None:
            return skill_error("Cycles unavailable", "The target scene does not expose scene.cycles.")
        inventory = _device_inventory(_cycles_preferences(bpy))
        return skill_success(
            "Render capabilities retrieved",
            profile_version=_PROFILE_VERSION,
            blender_version=list(getattr(getattr(bpy, "app", None), "version", ())),
            blender_version_string=getattr(getattr(bpy, "app", None), "version_string", None),
            scene_name=getattr(scene, "name", scene_name),
            render_engine=getattr(getattr(scene, "render", None), "engine", None),
            scene_device=getattr(cycles, "device", None),
            **inventory,
            profiles={"preview": "25% / 32 samples", "final": "100% / 64 exterior or 112 interior samples"},
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to inspect render capabilities")


def get_render_profile(scene_name: str | None = None) -> dict:
    """Read the complete photographic render state from a scene."""
    try:
        import bpy

        scene, error = _resolve_scene(bpy, scene_name)
        if error:
            return error
        inventory = _device_inventory(_cycles_preferences(bpy))
        current = _current_values(scene, _resolve_view_layer(scene), inventory)
        return skill_success(
            "Render profile state retrieved",
            profile_version=_PROFILE_VERSION,
            scene_name=getattr(scene, "name", scene_name),
            current=current,
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to read render profile state")


def validate_render_profile(
    profile_name: str,
    scene_kind: str = "EXTERIOR",
    device_backend: str = "AUTO",
    samples: int | None = None,
    allow_cpu_fallback: bool = True,
    scene_name: str | None = None,
) -> dict:
    """Validate a scene against a named photographic render profile."""
    try:
        values = _profile_values(profile_name, scene_kind, samples)
    except ValueError as exc:
        return skill_error("Invalid render profile", str(exc))
    try:
        import bpy

        scene, error = _resolve_scene(bpy, scene_name)
        if error:
            return error
        inventory = _device_inventory(_cycles_preferences(bpy))
        try:
            backend, cpu_fallback = _resolve_device_backend(
                device_backend, inventory["available_backends"], allow_cpu_fallback
            )
        except ValueError as exc:
            return skill_success(
                "Render profile validation completed",
                valid=False,
                profile_name=str(profile_name).upper(),
                scene_kind=str(scene_kind).upper(),
                issues=[{"code": "RENDER_DEVICE_UNAVAILABLE", "severity": "error", "message": str(exc)}],
            )
        current = _current_values(scene, _resolve_view_layer(scene), inventory)
        issues = _profile_issues(current, values, backend)
        return skill_success(
            "Render profile validation completed",
            valid=not issues,
            profile_version=_PROFILE_VERSION,
            profile_name=str(profile_name).upper(),
            scene_kind=str(scene_kind).upper(),
            requested_device_backend=str(device_backend).upper(),
            resolved_device_backend=backend,
            cpu_fallback=cpu_fallback,
            issues=issues,
            expected=values,
            current=current,
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to validate render profile")


def apply_render_profile(
    profile_name: str,
    scene_kind: str = "EXTERIOR",
    device_backend: str = "AUTO",
    samples: int | None = None,
    allow_cpu_fallback: bool = True,
    scene_name: str | None = None,
) -> dict:
    """Apply a photographic Cycles profile atomically and verify readback."""
    try:
        values = _profile_values(profile_name, scene_kind, samples)
    except ValueError as exc:
        return skill_error("Invalid render profile", str(exc))

    try:
        import bpy

        scene, error = _resolve_scene(bpy, scene_name)
        if error:
            return error
        cycles = getattr(scene, "cycles", None)
        if cycles is None:
            return skill_error("Cycles unavailable", "The target scene does not expose scene.cycles.")
        preferences = _cycles_preferences(bpy)
        inventory = _device_inventory(preferences)
        try:
            backend, cpu_fallback = _resolve_device_backend(
                device_backend, inventory["available_backends"], allow_cpu_fallback
            )
        except ValueError as exc:
            return skill_error(
                "Render device unavailable", str(exc), available_backends=inventory["available_backends"]
            )

        targets = _profile_targets(scene, values)
        missing = _missing_targets(targets)
        if missing:
            return skill_error(
                "Render profile unavailable",
                "The Blender build does not expose: " + ", ".join(missing),
                unsupported_properties=missing,
            )
        if backend != "CPU" and preferences is None:
            return skill_error(
                "Cycles preferences unavailable", "GPU backend selection requires the Cycles preferences add-on."
            )
        if backend != "CPU" and (
            not hasattr(preferences, "compute_device_type")
            or not (hasattr(preferences, "devices") or callable(getattr(preferences, "get_devices_for_type", None)))
        ):
            return skill_error(
                "Cycles device API unavailable", "This Blender build does not expose compute device preferences."
            )

        render = scene.render
        image_settings = render.image_settings
        snapshot = _snapshot(targets, image_settings)
        if hasattr(cycles, "device"):
            snapshot.append((cycles, "device", getattr(cycles, "device")))
        preference_snapshot = []
        if preferences is not None:
            saved_devices, live_devices, _live_enumeration = _device_objects(preferences)
            device_objects = []
            seen_device_ids = set()
            for device in [*saved_devices, *live_devices]:
                if id(device) in seen_device_ids:
                    continue
                seen_device_ids.add(id(device))
                device_objects.append(device)
            preference_snapshot = [
                (preferences, "compute_device_type", getattr(preferences, "compute_device_type")),
                *[
                    (device, "use", getattr(device, "use"))
                    for device in device_objects
                    if hasattr(device, "use")
                ],
            ]
        try:
            set_image_format(image_settings, values["file_format"])
            for owner, attribute, value, _path in targets:
                setattr(owner, attribute, value)
            cycles.device = "CPU" if backend == "CPU" else "GPU"
            if preferences is not None:
                preferences.compute_device_type = "NONE" if backend == "CPU" else backend
                for device in device_objects:
                    if hasattr(device, "use"):
                        device.use = backend != "CPU" and str(getattr(device, "type", "")).upper() == backend
        except Exception as exc:
            _restore(snapshot, image_settings)
            for owner, attribute, value in reversed(preference_snapshot):
                try:
                    setattr(owner, attribute, value)
                except Exception:
                    pass
            return skill_error("Render profile application failed", str(exc), profile_name=str(profile_name).upper())

        inventory_after = _device_inventory(preferences)
        current = _current_values(scene, _resolve_view_layer(scene), inventory_after)
        issues = _profile_issues(current, values, backend)
        if issues:
            _restore(snapshot, image_settings)
            for owner, attribute, value in reversed(preference_snapshot):
                try:
                    setattr(owner, attribute, value)
                except Exception:
                    pass
            return skill_error(
                "Render profile readback mismatch",
                "Applied settings did not match the requested profile.",
                profile_name=str(profile_name).upper(),
                issues=issues,
                current=current,
            )

        return skill_success(
            "Render profile applied",
            profile_version=_PROFILE_VERSION,
            profile_name=str(profile_name).upper(),
            scene_kind=str(scene_kind).upper(),
            requested_device_backend=str(device_backend).upper(),
            resolved_device_backend=backend,
            cpu_fallback=cpu_fallback,
            expected=values,
            current=current,
            capabilities=inventory_after,
            prompt="Run validate_render_profile before submitting the final render job.",
        )
    except ImportError:
        return skill_error("Blender not available", "bpy could not be imported")
    except Exception as exc:
        return skill_exception(exc, message="Failed to apply render profile")
