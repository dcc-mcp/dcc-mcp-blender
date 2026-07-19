---
name: blender-light-rig
description: "Blender reusable light rigs, HDRI/world setup and rotation animation, light grouping, and render-view controls"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    version: "1.1.0"
    tags: [blender, lighting, light-rig, hdri, world, lookdev, animation]
    search-hint: "three point light rig, softbox, hdri world, animate hdri rotation, rotating lookdev lighting, group lights, view transform, lighting summary"
    search-aliases: [light setup, studio lighting, key light, fill light, rim light, environment map, HDRI background, light grouping, lookdev lighting, rotating environment, light rotation, ACES, Filmic]
    intent: "Create and manage reusable light rigs, HDRI/world setups, fixed-camera HDRI rotation animation, light grouping, and render view-transform coordination."
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
    produces: [light_rig, hdri_setup, hdri_rotation_animation, view_transform_config]
    requires: []
    tools: tools.yaml
---

# blender-light-rig

Rig-oriented lighting helpers for repeatable Blender look-development setups.

Use this skill when a scene needs grouped lights, reusable three-point rigs,
HDRI/world setup, fixed-camera rotating-environment LookDev, light aiming, or
render view-transform coordination. Create the world with `create_hdri_world`,
then use `animate_hdri_rotation` for a repeatable lighting sweep. Single light
creation and basic property edits remain in `blender-lighting`.
