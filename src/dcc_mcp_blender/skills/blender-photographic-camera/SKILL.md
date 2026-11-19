---
name: blender-photographic-camera
description: "Physical Blender camera setup and continuous toy-shot motion validation"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    layer: domain
    stage: render
    version: "1.0.0"
    tags: [blender, camera, photography, depth-of-field, motion-blur, toy, shot]
    search-hint: "physical camera, 36 mm sensor, toy camera, ground-level camera, depth of field, focus eyes, continuous camera move, eased camera animation"
    search-aliases: [photographic camera, toy shot, character camera, camera on floor, focus eyes, round aperture, camera move, no camera shake, motion blur camera]
    intent: "Configure and validate a physical ground-level camera for photographically rendered toy shots."
    recall-context:
      app_type: blender
      domain: shot
      workflow_stage: render
      task_category: mutate
    preconditions:
      - type: software
        name: blender
        version: ">=4.0"
      - type: scene_state
        predicate: has_open_scene
    side-effects:
      creates: false
      modifies: true
      targets: [camera_data, camera_transform, camera_animation]
    produces: [photographic_camera, camera_motion, camera_validation_report]
    requires: [blender-camera, blender-animation]
    tools: tools.yaml
---

# blender-photographic-camera

This skill packages the physical camera contract for real-toy shots.

- `configure_photographic_camera` uses a 36 mm sensor, a 24–85 mm perspective
  lens, a 1–8 cm floor offset, depth of field, a round aperture, and a focus
  object such as the character's eye target.
- Character shots use f/2.8–f/5.6. Wide establishing shots use f/11.
- `animate_photographic_camera` writes BEZIER eased location and rotation keys one
  frame past both shot ends. Rotation endpoints are numerically unwrapped so a
  cut cannot introduce an Euler flip through motion blur.
- `validate_photographic_camera` is read-only and reports missing physical
  settings, focus, endpoint extension, or rotation animation.

The tools preserve the current playhead. They do not add camera shake or use
`hide_render` for shot changes.
