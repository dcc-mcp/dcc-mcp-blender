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
    tools: tools.yaml
---

# blender-pose-library

Typed pose capture and playback tools for Blender armatures. Poses are stored
as JSON in armature custom properties, so they work without third-party rigging
addons and travel with the `.blend` file.

Prefer `blender-rigging` for armature construction and `blender-animation` for
keyframes, baking, and timeline edits.
