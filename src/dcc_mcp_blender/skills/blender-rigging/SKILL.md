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
    tools: tools.yaml
---

# blender-rigging

Typed rigging tools for Blender armatures and character setup. Load this skill
when creating armatures or bones, binding meshes, adding constraints, creating
shape keys or drivers, or copying pose/action data between compatible rigs.

Prefer `blender-pose-library` for saving and loading reusable poses,
`blender-animation` for keyframe editing and baking, and `blender-scripting`
only after checking this typed surface.
