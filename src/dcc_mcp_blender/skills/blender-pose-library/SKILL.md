---
name: blender-pose-library
description: >-
  Blender pose library skill for listing, saving, loading, and mirroring
  reusable armature poses stored on Blender armature objects.
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    layer: domain
    stage: authoring
    version: "1.0.0"
    tags: [blender, pose, pose-library, armature, animation, retargeting]
    search-hint: >-
      pose library, save pose, load pose, list poses, mirror pose, armature pose,
      character animation handoff
    search-aliases: [character pose, pose preset, animation pose, save armature pose, load character pose, pose snapshot, retarget pose, mirror armature pose]
    intent: "Save, load, list, and mirror reusable armature poses stored as JSON on armature objects."
    recall-context:
      app_type: blender
      domain: animation
      workflow_stage: posing
      task_category: mutate
    preconditions:
      - type: software
        name: blender
        version: ">=4.0"
      - type: scene_state
        predicate: has_open_scene
    side-effects:
      modifies: true
      targets: [armature, pose_data]
    produces: [pose_snapshot, pose_list]
    requires: []
    tools: tools.yaml
---

# blender-pose-library

Typed pose capture and playback tools for Blender armatures. Poses are stored
as JSON in armature custom properties, so they work without third-party rigging
addons and travel with the `.blend` file.

Prefer `blender-rigging` for armature construction and `blender-animation` for
keyframes, baking, and timeline edits.
