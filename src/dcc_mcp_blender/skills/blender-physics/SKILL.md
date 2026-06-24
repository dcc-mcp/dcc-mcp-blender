---
name: blender-physics
description: "Blender rigid body, soft body, cloth, collision, force fields, particle systems, constraints, and simulation cache tools"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    version: "2.0.0"
    tags: [blender, physics, rigid-body, soft-body, cloth, collision, force-field, particle, constraint, simulation, cache]
    search-hint: "rigid body, soft body, physics, cloth modifier, collision modifier, force field, particle system, rigid body constraint, simulation cache, bake, mass, friction, restitution"
    search-aliases: [physics simulation, rigid body world, soft body, cloth sim, collision setup, point cache, bake physics, dynamics, nCloth, nParticle, force field wind, particle emitter, rigid constraint]
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

Full-coverage physics and dynamics skill for AI-assisted scene assembly.

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
| nHair | `add_particle_system` (hair physics type) |
| nConstraint | `add_rigid_body_constraint` |
| Bifrost fluid | `add_simulation_modifier` (FLUID) |
| Fields (gravity, wind, turbulence) | `add_force_field` |

Baking and cache-clearing tools mutate scene state; pass `dry_run=true` when
you only need target discovery and frame-range validation.
