---
name: blender-scene
description: "Blender scene management — create, open, save, list and inspect scene objects"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    layer: domain
    stage: bootstrap
    version: "1.0.1"
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


## Verified saves

`save_scene` uses Save As when `filepath` is provided, or saves the current file
when it is omitted. Blender-relative `//` paths are resolved against the scene
before saving; relative/absolute spellings and legitimate symlink paths are
accepted. Blender may append `.blend` to an extensionless destination.

Success retains `context.filepath`, now reporting Blender's actual absolute
saved path, with `requested_filepath`, `file_size_bytes` and `operator_result`.
`postcondition.verified: true` means the operator returned exactly `{"FINISHED"}` (mixed statuses are rejected), the native
scene path matches the requested destination, and the reported destination is a
nonempty regular file. This does not claim content integrity or successful
reopening. Reopen and inspect separately for deliverable acceptance.

A cancelled/nonfinished operator never succeeds merely because a previous file
exists. On operator or readback failure, `context.error_code` explains the check
and `save_attempted` records whether the operator was invoked. When it was,
`mutation_applied: null` means possible file/scene side effects are not known;
there is no automatic retry, deletion or rollback. Inspect before continuing.
This tool preserves its existing overwrite behavior; it does not create a new
backup/overwrite workflow or add extra save calls.
