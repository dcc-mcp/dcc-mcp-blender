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
multi-layer EXR or display-ready PNG output so the interactive Blender process
remains responsive; poll with `get_render_job` and cancel only through the
returned job id.

Use `start_multiview_render_job` for a bounded camera list (up to 8) and
`beauty`/`wire` PNG deliverables. It saves an isolated copy of the current
scene without changing the live filename, selection, materials, or settings.
The worker uses factory startup with automatic scripts disabled. External
assets must remain accessible; add-on-generated render dependencies are not
loaded. Beauty uses the saved render engine (Cycles uses CPU) but bypasses compositor and
sequencer to contain file output. Resolution is explicit and border rendering
is disabled. Cameras render the current saved frame; camera animation markers
are not used to select views.

Wire shows original mesh edges as physical tubes over the same unmodified
mesh surfaces. Modifiers and shape keys are disabled, non-mesh geometry is omitted, and
hidden render objects remain hidden. This is source topology, not evaluated
modifier topology or a screen-space overlay. Radius is in local object units
and scales with the object. The wire pass uses Cycles CPU. Requests exceeding the explicit max_source_edges budget (default 100,000; maximum 500,000) are
rejected. Each PNG is decoded by Blender, dimension checked, and hashed;
status reads verify the entire file hash. Failed images retain individual
errors and do not make the batch successful.

Poll using the existing `get_render_job(job_id)` and retain `job_directory`.
After an adapter restart, `get_render_job(job_id, job_directory)` recovers
terminal receipts; a nonterminal receipt returns `unknown` with its last
recorded state because no live process handle has been observed. No PID from
a disk file is trusted. Multiview cancellation writes an owned marker and
is cooperative between images; it cannot interrupt an in-progress render.
`cancel_render_job` accepts `job_directory` for the same recovery case.
