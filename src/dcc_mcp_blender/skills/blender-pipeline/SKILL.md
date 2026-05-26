---
name: blender-pipeline
description: "Blender local asset metadata, project context, publish manifests, and package prep"
license: "MIT"
allowed-tools: ["Bash", "Read"]
metadata:
  dcc-mcp:
    dcc: blender
    version: "1.0.0"
    tags: [blender, pipeline, metadata, publish, manifest, asset]
    search-hint: "asset metadata, project context, publish manifest, prepare publish package, local pipeline"
    tools: tools.yaml
---

# blender-pipeline

Local-only pipeline helpers for asset metadata and publish preparation.

This first version writes manifests and lightweight package directories on the
local filesystem only. It deliberately avoids studio-specific paths, service
names, hostnames, or external publishing integrations.
