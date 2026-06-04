---
name: blender-mesh
description: "Blender mesh operations — modifiers, subdivision, and mesh editing"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    version: "1.0.0"
    tags: [blender, mesh, modifier, geometry]
    search-hint: "modifier, subdivision, smooth, apply modifier, mesh edit, list modifiers, mesh info"
    search-aliases: [add modifier, apply modifier, list modifiers, mesh info, subdivision surface, bevel modifier, smooth modifier, geometry info]
    intent: "Add, apply, list, and inspect Blender modifiers on mesh objects for non-destructive editing."
    recall-context:
      app_type: blender
      domain: modeling
      workflow_stage: authoring
      task_category: mutate
    preconditions:
      - type: software
        name: blender
        version: ">=4.0"
      - type: selection
        kind: mesh_object
        min: 1
    side-effects:
      modifies: true
      creates: true
      targets: [modifier, mesh_data]
    produces: [modifier, mesh_info, modified_geometry]
    requires: []
    tools: tools.yaml
---

# blender-mesh

Blender mesh editing and modifier skill.
