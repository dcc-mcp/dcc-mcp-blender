---
name: blender-validation
description: "Blender scene, mesh, material, animation, and export readiness validation"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
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
