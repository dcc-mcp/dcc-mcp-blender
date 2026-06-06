---
name: blender-render-farm
description: |-
  Pipeline stage — render farm integration: validate scenes, write job
  configs, submit to Deadline or Flamenco, and query job status. Use for
  distributed render submission. Not for local renders (blender-render).
license: MIT
allowed-tools: Bash Read
metadata:
  dcc-mcp:
    dcc: blender
    layer: domain
    stage: pipeline
    version: 1.0.0
    tags:
    - blender
    - render
    - farm
    - deadline
    - flamenco
    - pipeline
    - submission
    search-hint: |-
      submit render job, distributed render, deadline queue, farm submission,
      validate scene for farm, render job spec, render job status, flamenco,
      cancel render, render farm status, list render jobs
    depends:
    - blender-render
    tools: tools.yaml
    groups: groups.yaml
---
# blender-render-farm (Pipeline stage)

Render farm submission. Layered on top of `blender-render` (which handles
*local* renders): this skill validates the scene for farm readiness, writes
a JSON job spec, and submits to Deadline (via ``deadlinecommand``) or
Flamenco (via REST API). Supports cooperative cancellation.

## Scripts

- `validate_scene_for_farm` — Check scene for missing files, render settings, camera
- `write_render_job` — Write a JSON render job spec for a render farm dispatcher
- `submit_render_job` — Submit the current scene to Deadline, Flamenco, or a generic farm
- `get_render_job_status` — Query the status of a submitted render job by job ID
- `list_render_jobs` — List recent render jobs from the farm manager
- `cancel_render_job` — Cancel a specific render job on the farm
- `cooperative_cancel` — Cancel the currently running farm operation cooperatively
- `render_farm_status` — Report the connected render farm health and worker status
