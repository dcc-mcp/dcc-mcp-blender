---
name: blender-data-geometry
description: Create bounded native meshes, editable poly curves and built-in-font text from explicit data. Use for GIS contours, scientific interchange, native typography and procedural authoring before raw scripting.
license: MIT
metadata:
  dcc-mcp:
    dcc: blender
    layer: domain
    stage: authoring
    version: "1.0.0"
    tags: [blender, geometry, data, curve, mesh, text, typography, interchange]
    search-hint: create mesh vertices faces curve poly splines GIS contour scientific data bounded native geometry editable text typography built-in font
    tools: tools.yaml
---

# Bounded data geometry

Use an unused name in an owned scene. Inputs are explicit finite XYZ and face-index data, never code or file paths. Existing data is never overwritten. The tools preserve selection and read back native float32 positions and topology or spline controls. Mesh payloads are limited to 30,000 vertices, 50,000 faces, 200,000 indices and 2 MB JSON. Curves allow 1,024 splines and 30,000 total controls. Coordinates are within ±1,000,000 scene units. These are resource bounds, not a sandbox or proof of valid engineering geometry.

2D curves must lie at local Z=0. Use existing object transforms to position them. Each ring is a separate closed POLY spline; preserve the source's exterior/interior orientation and visually verify filled holes. `extrude` is Blender's per-side depth, so a flat filled curve's body thickness is twice that value before bevel. No smoothing, triangulation, rig, UV or material is invented. Follow with typed material, transform, save and reopen operations.

Text creation and inspection accept 1–160 printable ASCII characters over at most three lines, size 0.001–10, extrusion 0–0.1, and LEFT/CENTER/RIGHT alignment. Regular and styled font slots must use local built-in fonts; an unassigned style slot falls back to the regular font. Use an existing named material when requested. Inspection reads native text and transforms without changing an existing object.
