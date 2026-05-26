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
    tools: tools.yaml
---

# blender-validation

Typed validation checks for Blender assets before export or publish.

Validation tools return structured reports with stable issue codes and
`info`/`warning`/`error` severities. Use these checks before interchange/export
tools or local publish preparation so agents can reason over machine-readable
failure causes instead of scraping arbitrary script output.
