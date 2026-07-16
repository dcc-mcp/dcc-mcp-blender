---
name: blender-render
description: "Blender rendering — render scenes, run observable background animation jobs, capture viewport images, and configure output"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    version: "1.0.0"
    tags: [blender, render, viewport, camera]
    search-hint: "render, viewport screenshot, output, resolution, camera, cycles, eevee, render preview"
    search-aliases: [render scene, render preview, viewport capture, screenshot, set render resolution, render settings, cycles render, eevee render, image output, render engine]
    intent: "Configure render settings, render scenes, submit/query/cancel isolated animation jobs, and capture viewport images."
    recall-context:
      app_type: blender
      domain: rendering
      workflow_stage: render
      task_category: mutate
    preconditions:
      - type: software
        name: blender
        version: ">=4.0"
      - type: scene_state
        predicate: has_open_scene
      - type: scene_state
        predicate: has_active_camera
    side-effects:
      file_output: true
      render: true
      targets: [file:image, render_result]
    produces: [file:image, render_result, render_settings]
    requires: []
    tools: tools.yaml
---

# blender-render

Use `render_scene` for short stills. Use `start_render_job` for animation or
multi-layer EXR output so the interactive Blender process remains responsive;
poll with `get_render_job` and cancel only through the returned job id.
