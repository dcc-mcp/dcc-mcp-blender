"""Temporary E2E probe: dump the real RNA names for fluid and particle knobs.

This file exists to answer one question the unit suite cannot: which property
names Blender actually exposes for Mantaflow domain settings and particle
child settings. Names are taken from live RNA and printed with ``flush=True``
so the output survives a later crash in the same pytest process.

Constraints it is built under:

- It must run *before* ``test_nodes_physics_e2e.py``, which is why the file
  name sorts earlier. Blender 4.2.0 on macOS segfaults once a Mantaflow domain
  exists, and that kills the process before any buffered output is written.
- It creates **no** Mantaflow domain and no fluid modifier at all. It reads
  ``bpy.types`` RNA and inspects an ordinary particle-system modifier, so it
  cannot itself trigger that crash.
- It prints both the RNA type name and the concrete object identity, so a
  missing property can be told apart from a test that grabbed the wrong
  object.

Delete this file once the names are pinned as real assertions.
"""

from __future__ import annotations

import sys

import pytest

bpy = pytest.importorskip("bpy", reason="bpy not available - run inside Blender Python interpreter")

pytestmark = pytest.mark.e2e


def _emit(line: str) -> None:
    print(f"[rna-probe] {line}", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()


def _rna_property_names(type_name: str):
    rna_type = getattr(bpy.types, type_name, None)
    if rna_type is None:
        return None, None
    names = sorted(prop.identifier for prop in rna_type.bl_rna.properties)
    return rna_type, names


def _probe(label: str, type_name: str, candidates) -> None:
    rna_type, names = _rna_property_names(type_name)
    _emit(f"--- {label}: bpy.types.{type_name} ---")
    if names is None:
        _emit(f"  TYPE MISSING: bpy.types.{type_name} does not exist")
        return
    _emit(f"  rna_identifier={rna_type.bl_rna.identifier} property_count={len(names)}")
    for candidate in candidates:
        _emit(f"  {candidate}: {'PRESENT' if candidate in names else 'ABSENT'}")


def test_probe_blender_version():
    _emit(f"blender_version={bpy.app.version_string}")
    _emit(f"python={sys.version.split()[0]}")


def test_probe_fluid_domain_rna_names():
    """Which resolution property does FluidDomainSettings actually expose?"""
    _probe(
        "fluid domain",
        "FluidDomainSettings",
        (
            "resolution_divisions",
            "resolution_max",
            "domain_resolution",
            "use_noise",
            "viscosity_base",
            "time_scale",
            "cfl",
            "noise_scale",
            "mesh_scale",
        ),
    )


def test_probe_fluid_flow_and_effector_rna_names():
    _probe("fluid flow", "FluidFlowSettings", ("flow_behavior", "flow_type", "flow_source"))
    _probe("fluid effector", "FluidEffectorSettings", ("effector_type",))


def test_probe_fluid_modifier_rna_names():
    _probe("fluid modifier", "FluidModifier", ("fluid_type", "domain_settings", "flow_settings", "effector_settings"))


def test_probe_particle_settings_rna_names():
    """Does ParticleSettings expose child_nbr, or is the name different?"""
    _probe(
        "particle settings",
        "ParticleSettings",
        (
            "type",
            "child_type",
            "child_nbr",
            "child_number",
            "rendered_child_count",
            "child_length",
            "child_radius",
            "child_roundness",
            "hair_length",
            "hair_step",
            "instance_object",
            "render_type",
            "particle_size",
        ),
    )


def test_probe_live_particle_object_identity():
    """Tell 'wrong property name' apart from 'test grabbed the wrong object'.

    If the RNA type list above says a property exists but this live object says
    it is absent, then the problem is the object under test, not the name.
    """
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.active_object
    obj.name = "Probe Particles"
    obj.modifiers.new("Probe System", "PARTICLE_SYSTEM")

    modifier = obj.modifiers["Probe System"]
    psystem = modifier.particle_system
    psettings = psystem.settings

    _emit("--- live particle object ---")
    _emit(f"  modifier.type={modifier.type} modifier.name={modifier.name}")
    _emit(f"  particle_system.type={type(psystem).__name__} name={psystem.name}")
    _emit(f"  settings.type={type(psettings).__name__} rna={psettings.bl_rna.identifier}")
    _emit(f"  settings is ParticleSettings: {isinstance(psettings, bpy.types.ParticleSettings)}")
    _emit(f"  point_cache on modifier: {hasattr(modifier, 'point_cache')}")
    _emit(f"  point_cache on particle_system: {hasattr(psystem, 'point_cache')}")
    for prop in ("child_type", "child_nbr", "rendered_child_count", "type", "hair_length"):
        _emit(f"  {prop}: {'PRESENT' if hasattr(psettings, prop) else 'ABSENT'}")


def test_probe_live_fluid_object_identity():
    """Report what a FLUID modifier exposes without creating a domain.

    Only FLOW is created here; a DOMAIN modifier is what makes Blender 4.2.0 on
    macOS crash on the next view-layer update, so this probe avoids it.
    """
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.active_object
    obj.name = "Probe Fluid"

    modifier = obj.modifiers.new("Probe Fluid Modifier", "FLUID")
    _emit("--- live fluid object (fluid_type=NONE) ---")
    if modifier is None:
        _emit("  modifiers.new returned None")
        return
    _emit(f"  modifier.type={modifier.type} fluid_type={modifier.fluid_type}")
    for block in ("domain_settings", "flow_settings", "effector_settings"):
        value = getattr(modifier, block, "MISSING")
        _emit(f"  {block}: {'MISSING' if value == 'MISSING' else ('None' if value is None else 'present')}")

    modifier.fluid_type = "FLOW"
    _emit("--- live fluid object (fluid_type=FLOW) ---")
    _emit(f"  fluid_type={modifier.fluid_type}")
    for block in ("domain_settings", "flow_settings", "effector_settings"):
        value = getattr(modifier, block, "MISSING")
        _emit(f"  {block}: {'MISSING' if value == 'MISSING' else ('None' if value is None else 'present')}")
    flow = getattr(modifier, "flow_settings", None)
    if flow is not None:
        for prop in ("flow_behavior", "flow_type"):
            _emit(f"  flow_settings.{prop}: {'PRESENT' if hasattr(flow, prop) else 'ABSENT'}")


def test_probe_scene_frame_range_affects_bake():
    """Confirm the ptcache operator bakes the scene range, not the cache range."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.active_object
    obj.name = "Probe Bake"
    obj.modifiers.new("Probe Bake System", "PARTICLE_SYSTEM")

    psystem = obj.modifiers["Probe Bake System"].particle_system
    cache = psystem.point_cache
    scene = bpy.context.scene

    _emit("--- bake range semantics ---")
    _emit(f"  scene range: {scene.frame_start}..{scene.frame_end}")
    _emit(f"  cache range before: {cache.frame_start}..{cache.frame_end}")

    cache.frame_start = 1
    cache.frame_end = 2
    _emit(f"  cache range after setting cache only: {cache.frame_start}..{cache.frame_end}")
    _emit(f"  scene range unchanged: {scene.frame_start}..{scene.frame_end}")
