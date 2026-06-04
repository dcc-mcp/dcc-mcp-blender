---
name: blender-materials
description: "Blender material system — create, assign, modify and list materials"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    version: "1.0.0"
    tags: [blender, materials, shading]
    search-hint: "create material, assign, color, shader, PBR, list materials, delete material"
    search-aliases: [create material, new material, assign material, set material color, list materials, remove material, material slots, shader base]
    intent: "Create, assign, edit, list, and delete materials in the Blender scene with color and shader property control."
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
      deletes: true
      targets: [material, material_slot]
    produces: [material, material_slot, color_assignment]
    requires: []
    tools: tools.yaml
---

# blender-materials

Blender material management skill.
