---
name: blender-photographic-delivery
description: "Configure and validate H.264 delivery and encode a photographic Blender frame sequence"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    layer: domain
    stage: pipeline
    version: "1.0.0"
    tags: [blender, delivery, ffmpeg, h264, crf, yuv420p, bt709, video]
    search-hint: "H.264 delivery, CRF 15, yuv420p, BT.709, 24 fps, FFmpeg, encode frame sequence, video output"
    search-aliases: [video encode, photographic video, mp4 delivery, final movie, frame sequence encode]
    intent: "Prepare Blender output and encode a photographic render sequence with exact delivery metadata."
    recall-context:
      app_type: blender
      domain: delivery
      workflow_stage: publish
      task_category: mutate
    preconditions:
      - type: software
        name: blender
        version: ">=5.0"
      - type: scene_state
        predicate: has_open_scene
    side-effects:
      modifies: true
      file_output: true
      targets: [render_output, video_file]
    produces: [video_output, delivery_validation_report]
    requires: [blender-render-profile]
    tools: tools.yaml
---

# blender-photographic-delivery

This skill configures Blender's native video output to 24 fps, MPEG-4, H.264,
and custom CRF 15. Blender's FFmpeg RNA does not expose every encoder option
consistently across releases, so `encode_photographic_video` applies the final
`yuv420p` and BT.709 flags explicitly through the FFmpeg executable.

Render the JPEG frame sequence with quality 96 from the photographic render
profile, validate the native output settings, then encode the numbered frames.

