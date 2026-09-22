---
name: blender-physics
description: "Blender rigid body, soft body, cloth, collision, force fields, particle systems, constraints, and simulation cache tools"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    layer: domain
    stage: simulation
    version: "2.0.0"
    tags: [blender, physics, rigid-body, soft-body, cloth, collision, force-field, particle, hair, mantaflow, fluid, dynamic-paint, constraint, simulation, cache]
    search-hint: "rigid body, soft body, physics, cloth modifier, collision modifier, force field, particle system, rigid body constraint, simulation cache, bake, mass, friction, restitution, Mantaflow, fluid, smoke, fire, dynamic paint, canvas, brush, hair, children, instancing"
    search-aliases: [physics simulation, rigid body world, soft body, cloth sim, collision setup, point cache, bake physics, dynamics, nCloth, nParticle, force field wind, particle emitter, rigid constraint, mantaflow, liquid domain, smoke simulation, dynamic paint, wetmap, hair strands, child particles, particle instance]
    intent: "Configure and manage all Blender physics simulations — rigid bodies, soft bodies, cloth, collisions, force fields, particle systems, rigid body constraints, and point caches. Provides Maya nCloth/nParticle/dynamics parity."
    recall-context:
      app_type: blender
      domain: simulation
      workflow_stage: simulation
      task_category: mutate
    preconditions:
      - type: software
        name: blender
        version: ">=4.0"
      - type: scene_state
        predicate: has_open_scene
    side-effects:
      modifies: true
      creates: true
      targets: [rigid_body, soft_body, cloth_modifier, collision_modifier, force_field, particle_system, rigid_body_constraint, point_cache]
    produces: [simulation_state, cache_bake, modifier_list, constraint_list, force_field_list, particle_system_list]
    requires: []
    tools: tools.yaml
---

# blender-physics

Typed physics and dynamics tools for AI-assisted scene assembly. Host-specific
cache limitations are explicit; this is not a claim of complete API coverage.

## Capabilities

| Domain | Tools |
|---|---|
| **Rigid body** | `add_rigid_body`, `set_rigid_body_properties`, `remove_rigid_body`, `list_rigid_bodies`, `set_rigid_body_world_settings`, `bake_rigid_body_simulation`, `clear_rigid_body_bake` |
| **Rigid body constraints** | `add_rigid_body_constraint`, `remove_rigid_body_constraint`, `list_rigid_body_constraints` |
| **Soft body** | `add_soft_body_modifier`, `set_soft_body_settings` |
| **Cloth** | `add_cloth_modifier`, `set_cloth_settings` |
| **Collision** | `add_collision_modifier`, `set_collision_settings` |
| **Force fields** | `add_force_field`, `remove_force_field`, `list_force_fields` |
| **Particle systems** | `add_particle_system`, `set_particle_system_settings`, `list_particle_systems` |
| **Cache / bake** | `bake_simulation`, `clear_simulation_cache`, `get_simulation_status`, `list_simulation_modifiers` |

## Maya parity

| Maya | Blender equivalent |
|---|---|
| nCloth | `add_cloth_modifier` |
| nParticle | `add_particle_system` |
| nHair | `set_particle_hair` + `set_particle_children` |
| nParticle instancing | `set_particle_instance` |
| nConstraint | `add_rigid_body_constraint` |
| Bifrost fluid | `add_fluid_modifier` + `set_fluid_settings` |
| Paint effects / wetmaps | `add_dynamic_paint_modifier` + `add_dynamic_paint_surface` |
| Fields (gravity, wind, turbulence) | `add_force_field` |

## Mantaflow fluid and Dynamic Paint

`list_simulation_modifiers` already reported FLUID and DYNAMIC_PAINT modifiers,
but nothing could create or tune them. Use these tools to close that gap:

| Tool | Description |
|---|---|
| `add_fluid_modifier` | Add a Mantaflow DOMAIN, FLOW, or EFFECTOR modifier |
| `set_fluid_settings` | Tune modifier properties plus `domain_settings` (resolution, viscosity, noise) |
| `add_dynamic_paint_modifier` | Add a Dynamic Paint CANVAS (receives paint) or BRUSH (emits paint) |
| `set_dynamic_paint_settings` | Tune the canvas or brush settings block |
| `add_dynamic_paint_surface` | Add a PAINT, DISPLACE, WEIGHT, or WAVE surface to a canvas |
| `list_dynamic_paint_surfaces` | Inspect the surfaces configured on canvas modifiers |

Domain options live on `modifier.domain_settings`, so `set_fluid_settings`
takes a separate `domain_settings` object; only a DOMAIN modifier exposes it.
Use `resolution_max` for domain resolution — `resolution_divisions` was removed
in Blender 2.82 and exists on no supported version. The domain, flow, and
effector settings blocks are all `None` while `fluid_type` is `NONE`; they
appear once the matching type is set.

**Settings that do not take effect are named in `message`, not just in the
response context.** A wrong or version-specific property name is skipped rather
than rejected, so a response can be a success without having done everything
asked. Those names go into the message (for example "Not applied (unsupported
by Blender 4.5.13): resolution_divisions") and into the `not_applied` field; `skipped`
is kept as an alias. Check `not_applied` after any call that passes a settings
dict. The property lists stay a pass-through deliberately: a hard-coded
allowlist would break the moment Blender renames or adds a property.

**Fluid and Dynamic Paint baking is not exposed by these tools.**
`bake_simulation` only targets cloth, soft-body, and particle point caches and
rejects anything else, so it cannot bake a fluid or paint cache. Bake those
from the Blender UI or through `bpy.ops` via `blender-scripting`.

Mantaflow has no `OBSTACLE`, `INFLOW`, or `OUTFLOW` fluid type. Set
`fluid_type` to `FLOW` and configure `modifier.flow_settings.flow_behavior`
(`INFLOW` / `OUTFLOW` / `GEOMETRY`) and `modifier.flow_settings.flow_type`
(`SMOKE` / `FIRE` / `BOTH` / `LIQUID`); obstacles are `EFFECTOR` with
`modifier.effector_settings.effector_type = 'COLLISION'`. Passing one of the
legacy names returns exactly which property to set instead of failing blind.

`add_dynamic_paint_surface` needs `canvas_surfaces.new()`, which some Blender
builds do not expose. When it is missing the tool says so explicitly; add the
surface with `bpy.ops.dpaint.surface_slot_add()` instead.

## Particle hair, children, and instancing

| Tool | Description |
|---|---|
| `set_particle_hair` | Switch a system between EMITTER and HAIR and set hair properties |
| `set_particle_children` | Set child type and the rendered child count |
| `set_particle_instance` | Instance a scene object per particle and control emitter visibility |
| `bake_particle_system` | Bake or free the point cache of one particle system |

`add_particle_system` already accepted `instance_object_name` and
`show_emitter`; use `set_particle_instance` to change them later or to set
`render_type` and `particle_size`.

Use `rendered_child_count` for the number of children to render: live RNA
confirms it on every version from 3.6.5 to 5.2.1. `child_nbr` is the **display**
amount, a different knob, and Blender 4.x removed it — passing it there fails
with a message naming the replacement rather than writing to a different
property. Point caches live on `particle_system`, not on the modifier.

Baking and cache-clearing tools mutate scene state; pass `dry_run=true` when
you only need target discovery and frame-range validation.

`bake_simulation` and `clear_simulation_cache` operate on matching cloth,
soft-body, and particle point caches in the current scene only. Use both exact
object and modifier names to narrow the target. With no names, all supported
matching caches are selected; any unsupported target aborts preflight before
mutation. Collision-only, fluid, and dynamic-paint caches require their own
host-specific workflows and never trigger a global cache fallback.

Dry runs do not change cache ranges, scene frames, selection, or baked state.
Actual operations require Blender's `context.temp_override` and per-cache
operator support, retain the scene range and selection, and return before/after
cache state. Clear an already baked target explicitly before rebaking it.
Native baking is monolithic: no mid-call cancellation is promised. On failure,
inspect `targets`, `completed_count`, and `mutation_state` through the response
and `get_simulation_status` before considering a retry.

The distinction between per-cache and scene-wide operators follows Blender's
[official point-cache API](https://docs.blender.org/api/5.2/bpy.ops.ptcache.html).
