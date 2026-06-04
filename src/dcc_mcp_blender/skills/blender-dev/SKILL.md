---
name: blender-dev
description: "Blender add-on development diagnostics, reloads, UI metadata, and environment checks"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    version: "1.0.0"
    tags: [blender, development, diagnostics, addon, reload, ui, debug]
    search-hint: "addon diagnostics, reload modules, run check, development, debug server, UI snapshot, Python environment"
    search-aliases: [developer tools, debug addon, module reload, sys.path, diagnostic check, UI inspector, debugpy, addon state, dev environment]
    intent: "Development-only diagnostics for Blender add-on debugging — inspect state, reload modules, attach debugger, and query environment."
    recall-context:
      app_type: blender
      domain: diagnostics
      workflow_stage: diagnostics
      task_category: query
    preconditions:
      - type: software
        name: blender
        version: ">=4.0"
    side-effects:
      modifies: true
      imports: true
      targets: [addon_state, sys.path, module_cache]
    produces: [diagnostic_report, ui_snapshot, environment_info]
    requires: []
    tools: tools.yaml
---

# blender-dev

Development-only diagnostics for Blender add-ons and adapter debugging.

Prefer typed domain skills for scene authoring. Use this skill when you need to
inspect add-on state, attach a checkout to `sys.path`, reload development
modules, run a named diagnostic check, inspect structured UI metadata, or start
an optional `debugpy` listener. Code execution helpers can run arbitrary Python
inside Blender and should be used only for explicit development or test flows.
