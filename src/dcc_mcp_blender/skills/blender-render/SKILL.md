---
name: blender-render
description: "Blender rendering — render scenes, capture viewport images, set render settings, manage cameras"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    version: "1.0.0"
    tags: [blender, render, viewport, camera]
    search-hint: "render, viewport screenshot, output, resolution, camera, cycles, eevee, render preview"
    search-aliases: [render scene, render preview, viewport capture, screenshot, set render resolution, render settings, cycles render, eevee render, image output, render engine]
    intent: "Configure render settings, render scenes, capture viewport images, and inspect render status in Blender."
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

Blender rendering skill.
