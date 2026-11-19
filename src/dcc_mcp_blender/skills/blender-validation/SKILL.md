---
name: blender-validation
description: "Blender scene, mesh, material, animation, and export readiness validation"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    layer: domain
    stage: validation
    version: "1.0.0"
    tags: [blender, validation, pipeline, scene-checks, export-readiness]
    search-hint: "validate scene, validate mesh, material validation, animation validation, export readiness, severity report"
    search-aliases: [scene check, mesh check, validation report, pre-export check, diagnostic, issue scan, sanity check, quality check, lint scene]
    intent: "Run structured validation checks on Blender scenes — detect issues before export or publish with severity-coded reports."
    recall-context:
      app_type: blender
      domain: diagnostics
      workflow_stage: validation
      task_category: query
    preconditions:
      - type: software
        name: blender
        version: ">=4.0"
      - type: scene_state
        predicate: has_open_scene
    side-effects:
      modifies: false
      creates: false
      targets: [validation_report]
    produces: [validation_report, issue_list]
    requires: []
    tools: tools.yaml
---

# blender-validation

Typed validation checks for Blender assets before export or publish.

Validation tools return structured reports with stable issue codes and
`info`/`warning`/`error` severities. Use these checks before interchange/export
tools or local publish preparation so agents can reason over machine-readable
failure causes instead of scraping arbitrary script output.

`validate_photographic_shot` checks the complete real-toy contract before a
render. Supply the hero, eye-focus target, background, floor, wall, and
motivated source references. The active scene camera remains the default when
`camera_name` is omitted. The report covers metric scene scale, Poly Haven PBR
maps with object-space box projection on the hero, supplied toy parts,
background, floor, and wall, life-size environment dimensions, physical camera
limits, continuous camera animation and endpoint extensions, bevels on every
supplied toy part, animated `hide_render`, the selected Cycles profile with an
OptiX or Metal backend, motivated lighting, required preview color safety for
final shots, and the photographic compositor finish. FINAL validation also
checks the preview evidence sidecar produced by
`render_photographic_test_still`.
