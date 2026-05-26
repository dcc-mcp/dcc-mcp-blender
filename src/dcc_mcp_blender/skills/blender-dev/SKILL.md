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
    tools: tools.yaml
---

# blender-dev

Development-only diagnostics for Blender add-ons and adapter debugging.

Prefer typed domain skills for scene authoring. Use this skill when you need to
inspect add-on state, attach a checkout to `sys.path`, reload development
modules, run a named diagnostic check, inspect structured UI metadata, or start
an optional `debugpy` listener. Code execution helpers can run arbitrary Python
inside Blender and should be used only for explicit development or test flows.
