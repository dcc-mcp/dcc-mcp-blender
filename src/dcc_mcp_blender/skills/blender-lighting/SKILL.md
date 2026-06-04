---
name: blender-lighting
description: "Blender lighting — create, configure and manage lights and world background"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    version: "1.0.0"
    tags: [blender, lighting, lights, world]
    search-hint: "create light, point, sun, area, spot, energy, color, world background, environment lighting, list lights"
    search-aliases: [create light, point light, sun light, area light, spot light, set light color, light energy, world color, environment lighting, list lights]
    intent: "Create lights, edit light properties, list lights, and set world background in Blender for scene illumination."
    recall-context:
      app_type: blender
      domain: lookdev
      workflow_stage: authoring
      task_category: mutate
    preconditions:
      - type: software
        name: blender
        version: ">=4.0"
      - type: scene_state
        predicate: has_open_scene
    side-effects:
      creates: true
      modifies: true
      targets: [light, world_background]
    produces: [light, world_background, lighting_setup]
    requires: []
    tools: tools.yaml
---

# blender-lighting

Blender lighting management skill.
