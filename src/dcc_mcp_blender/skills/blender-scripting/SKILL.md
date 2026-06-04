---
name: blender-scripting
description: "Execute Python code or scripts inside Blender's Python interpreter"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    layer: infrastructure
    stage: diagnostics
    version: "1.0.0"
    tags: [blender, scripting, python, automation, escape-hatch]
    search-hint: "execute python, run script, blender python, bpy, custom logic"
    search-aliases: [python, script, custom, escape hatch, blender info, execute code, run python, arbitrary python, bpy eval]
    intent: "Execute arbitrary Python code or script files inside Blender's Python interpreter — use only as a last-resort escape hatch after typed skills are exhausted."
    recall-context:
      app_type: blender
      domain: diagnostics
      workflow_stage: diagnostics
      task_category: mutate
    preconditions:
      - type: software
        name: blender
        version: ">=4.0"
      - type: other
        description: "Should only be invoked after checking that no typed skill covers the requested operation."
    side-effects:
      modifies: true
      creates: true
      deletes: true
      file_output: true
      render: true
      ui_mutation: true
      targets: [arbitrary]
    produces: [arbitrary]
    requires: []
    tools: tools.yaml
---

# blender-scripting

Execute arbitrary Python code inside Blender's Python interpreter.
