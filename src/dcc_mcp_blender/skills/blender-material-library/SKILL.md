---
name: blender-material-library
description: "Blender material presets, shader assignments, texture images, and color-management helpers"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    version: "1.0.0"
    tags: [blender, material, lookdev, texture, color-management, preset]
    search-hint: "material presets, assign texture, material connections, shader assignment, color management, images"
    search-aliases: [material library, lookdev, PBR preset, texture assignment, color space, image texture, shader connections, material template, reusable material]
    intent: "Manage reusable material presets, texture image assignments, shader connections, and color-management settings."
    recall-context:
      app_type: blender
      domain: lookdev
      workflow_stage: lookdev
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
      targets: [material, texture, shader_node]
    produces: [material_preset, texture_assignment, color_config]
    requires: []
    tools: tools.yaml
---

# blender-material-library

Reusable look-development helpers for Blender scenes.

Material presets use the portable `dcc-mcp-blender.material-preset.v1` JSON
shape stored on the scene, and texture helpers operate on explicit local image
paths only. No private asset-library paths, services, or hostnames are assumed.
