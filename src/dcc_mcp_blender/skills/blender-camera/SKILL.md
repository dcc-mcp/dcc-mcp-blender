---
name: blender-camera
description: "Blender camera management — create, configure, animate optics and set active cameras"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    layer: domain
    stage: scene
    version: "1.0.1"
    tags: [blender, camera, viewport]
    search-hint: "camera, lens, focal length, active camera, perspective, create camera, list cameras"
    search-aliases: [create camera, set active camera, camera properties, lens, focal length, list cameras, camera framing, shot setup, camera zoom animation, lens keyframe]
    intent: "Create cameras, set the active camera, edit camera properties, and list cameras in Blender for view and shot framing."
    recall-context:
      app_type: blender
      domain: shot
      workflow_stage: authoring
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
      targets: [camera, scene_node]
    produces: [camera, camera_settings]
    requires: []
    tools: tools.yaml
---

# blender-camera

Blender camera management skill.

Use `set_camera_properties` with `lens` in millimetres for perspective focal
length, and `ortho_scale` in scene units for orthographic framing. Changing
`lens` does not change the orthographic view width. `list_cameras` reports
both values and the clipping range for readback.

Camera requests validate numeric values and the effective clipping range
before changing camera properties. Invalid requests leave those properties
unchanged. Discover the explicit tool schemas and call examples before use.

## Animated optics

For a real zoom, set `lens` with `set_camera_properties`, then call
`set_camera_keyframe` at the intended frame. For orthographic framing animate
`ortho_scale` instead. This bounded tool keys camera data, while the animation
skill's `set_keyframe` keys object transforms. Use both when the shot requires
camera movement and changing optics; do not substitute subject scaling for zoom.

The default interpolation is LINEAR. The playhead is left unchanged, and the
current camera value is inserted without evaluating the scene first. Use
`set_current_frame` followed by `list_cameras` to verify endpoints and intermediate
frames. A shared camera data-block means all its camera objects share the keys;
inspect the returned data-block name and user count. Lens changes do not alter
orthographic framing. This tool does not animate focus or manage shot cuts.
NLA tweak mode is rejected before mutation because it remaps scene time into
action time. Exit tweak mode before using this bounded tool.
