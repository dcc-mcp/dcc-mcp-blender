---
name: blender-scene
description: "Blender scene management — create, open, save, list and inspect scene objects"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    version: "1.0.0"
    tags: [blender, scene, hierarchy]
    search-hint: "new scene, open, save, list objects, hierarchy, scene info, session, diagnostics"
    search-aliases: [scene summary, session info, get scene, new blend file, open blend, save blend, inspect scene, list objects]
    intent: "Inspect and manage Blender scene lifecycle — create, open, save scenes, list objects, and retrieve session diagnostics."
    recall-context:
      app_type: blender
      domain: scene
      workflow_stage: bootstrap
      task_category: query
    preconditions:
      - type: software
        name: blender
        version: ">=4.0"
    side-effects:
      creates: true
      modifies: true
      file_output: true
      targets: [scene, file:blend]
    produces: [scene_info, session_info, file:blend, object_list]
    requires: []
    tools: tools.yaml
---

# blender-scene

Blender scene management skill — create, open, save and inspect scenes.
