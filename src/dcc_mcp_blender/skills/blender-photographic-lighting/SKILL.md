---
name: blender-photographic-lighting
description: "Motivated toy-shot lighting, outdoor HDRI plus sun, AgX color safety, and contrast validation"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    layer: domain
    stage: lookdev
    version: "1.0.0"
    tags: [blender, lighting, motivated, hdri, sun, agx, toy, color]
    search-hint: "motivated light, sun through window, lamp, screen light, outdoor HDRI, Poly Haven, sun angle, AgX, saturated color, hero background contrast"
    search-aliases: [photographic lighting, motivated source, window sun, lamp key, screen glow, outdoor sky, hdri sun, warm clipping, color safety]
    intent: "Configure and validate the motivated lighting and color-management contract for photographically rendered toy shots."
    recall-context:
      app_type: blender
      domain: lookdev
      workflow_stage: lighting
      task_category: mutate
    preconditions:
      - type: software
        name: blender
        version: ">=4.0"
      - type: scene_state
        predicate: has_open_scene
    side-effects:
      creates: true
      modifies: true
      targets: [light, world, hdri, render_view]
    produces: [motivated_light, outdoor_hdri_setup, agx_color_setup, lighting_validation_report]
    requires: [blender-lighting, blender-light-rig]
    tools: tools.yaml
---

# blender-photographic-lighting

This skill packages the motivated-lighting contract for real-toy shots.

- `configure_motivated_lighting` creates one owned source for a window sun, lamp, or screen. Outdoor shots use a local HDRI plus a Sun with a 1.2 degree angle.
- The setup applies AgX, the Medium High Contrast look, and exposure zero. Saturated-color safety remains a preview-render check so the key energy can be lowered without changing material color.
- `validate_motivated_lighting` is read-only and reports source type, HDRI, sun angle, AgX state, and whether the hero sits in front of a darker or cooler background.

Pass a local downloaded Poly Haven HDRI path explicitly when using `OUTDOOR_HDRI`.
