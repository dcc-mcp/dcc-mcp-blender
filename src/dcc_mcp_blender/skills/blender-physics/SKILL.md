---
name: blender-physics
description: "Blender rigid body, cloth, collision, and simulation cache tools"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    version: "1.0.0"
    tags: [blender, physics, rigid-body, cloth, collision, simulation, cache]
    search-hint: "rigid body, physics, cloth modifier, collision modifier, simulation cache, bake, mass, friction, restitution"
    search-aliases: [physics simulation, rigid body world, soft body, cloth sim, collision setup, point cache, bake physics, dynamics]
    intent: "Configure and manage Blender physics simulations — rigid bodies, cloth, collisions, and point caches."
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
      targets: [rigid_body, cloth_modifier, collision_modifier, point_cache]
    produces: [simulation_state, cache_bake, modifier_list]
    requires: []
    tools: tools.yaml
---

# blender-physics

Physics and simulation setup tools for AI-assisted scene assembly.

Use this skill to add or tune rigid bodies, configure the scene rigid-body
world, attach cloth and collision modifiers, inspect simulation modifiers, and
prepare or clear point-cache bakes. Baking and cache-clearing tools mutate scene
state and can take longer than normal setup calls; pass `dry_run=true` on the
simulation cache tools when you only need target discovery and frame-range
validation.
