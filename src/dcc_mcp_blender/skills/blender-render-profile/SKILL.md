---
name: blender-render-profile
description: "Blender 5 photographic Cycles profiles, GPU capability detection, and render-profile validation"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    layer: domain
    stage: render
    version: "1.0.0"
    tags: [blender, render, cycles, gpu, optix, metal, profile, preview, final, validation]
    search-hint: "Cycles render profile, Blender 5 render settings, GPU capability, OptiX, Metal, preview render, final render, render validation"
    search-aliases: [render preset, render profile, photographic render, cycles quality, gpu detection, render settings validation, preview profile, final profile]
    intent: "Apply and validate deterministic Blender 5 Cycles render profiles for photographic preview and final output."
    recall-context:
      app_type: blender
      domain: rendering
      workflow_stage: render
      task_category: mutate
    preconditions:
      - type: software
        name: blender
        version: ">=5.0,<5.3"
      - type: scene_state
        predicate: has_open_scene
    side-effects:
      modifies: true
      creates: false
      targets: [render_settings, cycles_settings, device_preferences]
    produces: [render_profile, render_capabilities, validation_report]
    requires: []
    tools: tools.yaml
---

# blender-render-profile

This skill provides two deterministic photographic Cycles profiles.

- `PREVIEW` uses 25% resolution and 32 samples for fast look checks.
- `FINAL` uses 100% resolution, exactly 64 samples for sunny exteriors, and 112 to 176 samples for interiors.

`PREVIEW` is fixed at 32 samples. Sample overrides are rejected when they fall
outside the prompt's contract so a successful profile validation is meaningful.

Both profiles configure the complete Cycles quality contract, including
adaptive sampling, OIDN denoising, light paths, clamps, caustics, motion blur,
persistent data, JPEG output quality, and AgX color management.

Use `get_render_capabilities` before selecting a backend. `AUTO` prefers a
usable GPU backend. The photographic preview tool rejects CPU fallback unless
the caller explicitly enables `allow_cpu_fallback`.
Explicit GPU requests fail before scene mutation when the backend is absent.

Call `validate_render_profile` after applying a profile and before submitting a
long render job.

Use `render_photographic_test_still` for the required 25% / 32-sample JPEG
inspection. It temporarily applies the preview profile, renders one frame,
writes a `.photographic.json` evidence sidecar, and restores the previous
render settings and current frame afterward. Pass its output path to
`analyze_photographic_test_still` before changing light energy or starting the
final render.
