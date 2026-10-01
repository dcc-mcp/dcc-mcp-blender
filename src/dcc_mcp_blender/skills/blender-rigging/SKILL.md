---
name: blender-rigging
description: >-
  Blender authoring skill for armatures, bones, constraints, armature binding,
  rest/pose inspection, bulk pose transforms, shape keys, drivers, and simple retargeting. Use this for character setup
  before falling back to blender-scripting.
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    layer: domain
    stage: authoring
    version: "1.1.0"
    tags: [blender, rigging, armature, pose, constraints, drivers, shape-keys, retargeting]
    search-hint: >-
      rigging, armature, bones, create bone, constraints, skinning, armature
      modifier, inspect armature, bone hierarchy, pose bone transforms, skin weights,
      shape keys, drivers, retarget animation
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

## Inspect and pose an existing rig

Use `inspect_armature` to read the hierarchy, armature-space rest data, current
local channels, evaluated armature-space pose matrices, and bounded constraint
summaries. `max_bones` limits the returned bones. For a specific subset, pass
`bone_names`. Skin summaries require explicit `mesh_names` with an Armature
modifier targeting that rig; the deterministic vertex-index prefix is a sample
unless `scan_complete` is true. The summary covers deform-bone vertex groups,
not envelope deformation or a proof of animation quality.

`set_pose_bone_transforms` applies a batch of absolute, rest-relative local
RNA channels. Location uses scene units, Euler angles use radians, and unit
quaternions use `[w, x, y, z]`. Euler order defaults to `XYZ`; quaternion input
selects `QUATERNION`. Omitted channels remain unchanged. Euler and quaternion
inputs are mutually exclusive. Each scale component must have absolute value
at least `1e-6`; all numeric components must be finite with absolute value at
most `1e6`. Every bone and input is validated before mutation.

The update uses data APIs without changing selection, mode, frame, constraints,
or keyframes, and supports headless Blender. Leave armature Edit mode first.
After dependency evaluation it checks channel readback against the requested
values or their exact 32-bit float representation and returns actual values and
evaluated matrices. Constraints can make the evaluated pose differ from the
requested local channels. Drivers that overwrite channels cause failure.
An application or readback failure attempts to restore all original channels;
the error explicitly reports `rolled_back` and `rollback_errors`. Inspect the
rig before retrying. Use `blender-animation` separately for keyframes.
