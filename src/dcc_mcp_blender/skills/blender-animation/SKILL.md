---
name: blender-animation
description: "Blender animation — keyframes, frame ranges, curve inspection, key deletion, and baking"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    version: "1.0.0"
    tags: [blender, animation, keyframes, curves, baking, timeline]
    search-hint: "keyframe, animation, frame range, action, timeline, fcurve, delete keyframes, bake animation"
    search-aliases: [animate, set keyframe, keyframe editor, f-curve, action editor, delete animation, bake to keyframes, timeline scrubbing]
    intent: "Manage Blender animation — inspect keyframes, insert/delete keys, adjust frame ranges, and bake animation samples."
    recall-context:
      app_type: blender
      domain: animation
      workflow_stage: animation
      task_category: mutate
    preconditions:
      - type: software
        name: blender
        version: ">=4.0"
      - type: scene_state
        predicate: has_open_scene
    side-effects:
      modifies: true
      targets: [action, fcurve, keyframe, scene_frame]
    produces: [action, fcurve_data, keyframe_list]
    requires: []
    tools: tools.yaml
---

# blender-animation

Blender animation keyframe and timeline skill. Use it for frame ranges,
current-frame changes, inserting keys, inspecting f-curves, deleting keyframes,
and baking transform samples. Prefer `blender-rigging` for rig construction and
`blender-pose-library` for reusable armature poses.
