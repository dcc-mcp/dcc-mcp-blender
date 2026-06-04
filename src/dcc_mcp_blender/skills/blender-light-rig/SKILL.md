---
name: blender-light-rig
description: "Blender reusable light rigs, HDRI/world setup, light grouping, and render-view controls"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    version: "1.0.0"
    tags: [blender, lighting, light-rig, hdri, world, lookdev]
    search-hint: "three point light rig, softbox, hdri world, group lights, view transform, lighting summary"
    search-aliases: [light setup, studio lighting, key light, fill light, rim light, environment map, HDRI background, light grouping, lookdev lighting, ACES, Filmic]
    intent: "Create and manage reusable light rigs, HDRI/world setups, light grouping, and render view-transform coordination."
    recall-context:
      app_type: blender
      domain: lookdev
      workflow_stage: lighting
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
      targets: [light, world, hdri, render_view]
    produces: [light_rig, hdri_setup, view_transform_config]
    requires: []
    tools: tools.yaml
---

# blender-light-rig

Rig-oriented lighting helpers for repeatable Blender look-development setups.

Use this skill when a scene needs grouped lights, reusable three-point rigs,
HDRI/world setup, light aiming, or render view-transform coordination. Single
light creation and basic property edits remain in `blender-lighting`.
