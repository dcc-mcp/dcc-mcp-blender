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
    tools: tools.yaml
---

# blender-animation

Blender animation keyframe and timeline skill. Use it for frame ranges,
current-frame changes, inserting keys, inspecting f-curves, deleting keyframes,
and baking transform samples. Prefer `blender-rigging` for rig construction and
`blender-pose-library` for reusable armature poses.
