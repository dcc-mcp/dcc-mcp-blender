---
name: blender-objects
description: "Blender object manipulation — create, delete, move, rotate, scale and duplicate objects"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    version: "1.0.0"
    tags: [blender, objects, transform]
    search-hint: "create object, delete, move, rotate, scale, duplicate, select, rename, parent, hide, bounds"
    search-aliases: [add object, transform object, remove object, duplicate object, select object, find object, rename object, parent object, hide object, object bounds]
    intent: "Create, transform, select, duplicate, parent, rename, hide, and delete objects in the Blender scene."
    recall-context:
      app_type: blender
      domain: scene
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
      targets: [scene_node]
    produces: [scene_node, transform, selection_state]
    requires: []
    tools: tools.yaml
---

# blender-objects

Blender object manipulation skill.
