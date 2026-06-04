---
name: blender-rigging
description: >-
  Blender authoring skill for armatures, bones, constraints, armature binding,
  shape keys, drivers, and simple retargeting. Use this for character setup
  before falling back to blender-scripting.
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    layer: domain
    stage: authoring
    version: "1.0.0"
    tags: [blender, rigging, armature, pose, constraints, drivers, shape-keys, retargeting]
    search-hint: >-
      rigging, armature, bones, create bone, constraints, skinning, armature
      modifier, shape keys, drivers, retarget animation
    search-aliases: [character rig, skeleton, bone setup, IK constraint, copy rotation, limit distance, driver setup, blend shape, morpher, corrective shape, animation retarget]
    intent: "Create and edit armatures, bones, constraints, shape keys, and drivers for character rigging and deformation."
    recall-context:
      app_type: blender
      domain: authoring
      workflow_stage: rigging
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
      targets: [armature, bone, constraint, shape_key, driver, modifier]
    produces: [armature, bone_hierarchy, constraint_list, shape_key_list]
    requires: []
    tools: tools.yaml
---

# blender-rigging

Typed rigging tools for Blender armatures and character setup. Load this skill
when creating armatures or bones, binding meshes, adding constraints, creating
shape keys or drivers, or copying pose/action data between compatible rigs.

Prefer `blender-pose-library` for saving and loading reusable poses,
`blender-animation` for keyframe editing and baking, and `blender-scripting`
only after checking this typed surface.
