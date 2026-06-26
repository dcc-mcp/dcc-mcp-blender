# GEMINI.md — Google Gemini / Vertex AI Integration Guide

> Gemini-specific integration notes for `dcc-mcp-blender`.
> For the full project map, see [AGENTS.md](AGENTS.md).

---

## What This Project Does

`dcc-mcp-blender` embeds an MCP Streamable HTTP server directly inside Blender. Gemini (via an MCP-compatible client or custom integration) can discover and invoke 200+ Blender tools over HTTP.

---

## Gemini-Specific Strengths

Gemini excels at **code generation** and **structured output parsing**. Leverage these when working with `dcc-mcp-blender`:

### 1. Skill Script Generation
Ask Gemini to generate new Blender skill scripts using the `dcc_mcp_blender.api` helpers:

```python
from dcc_mcp_blender.api import blender_success, blender_error

def batch_rename(prefix: str) -> dict:
    """Rename selected objects with prefix."""
    import bpy
    selected = bpy.context.selected_objects or []
    renamed = []
    for obj in selected:
        obj.name = f"{prefix}{obj.name}"
        renamed.append(obj.name)
    return blender_success("Renamed objects", renamed=renamed, count=len(renamed))
```

### 2. Structured Tool Results
Gemini handles nested JSON well. Parse `blender_success` / `blender_error` results directly:

```json
{
  "success": true,
  "message": "Created sphere",
  "context": {
    "object_name": "Sphere",
    "radius": 1.0
  }
}
```

### 3. Skill Search & Discovery
Use Gemini's search capability with the built-in discovery tools:
- `search_skills("render batch")` → returns matching skills with descriptions
- `search_tools(query="bake", tags=["texture"])` → filtered search

---

## Integration Setup

If your Gemini client supports MCP over HTTP, configure:

```
Endpoint: http://127.0.0.1:8765/mcp
Protocol: MCP Streamable HTTP (2025-03-26 spec)
```

---

## Gemini-Specific Tips

- **Code-first workflows:** Gemini can write complete skill packages. Generate `SKILL.md`, `tools.yaml`, and `scripts/*.py` in one shot, then place them in a directory listed in `DCC_MCP_BLENDER_SKILL_PATHS`.
- **Image understanding:** Feed `capture_viewport` base64 PNGs back to Gemini for visual state verification.

---

## See Also

- [AGENTS.md](AGENTS.md) — Shared agent navigation map; keep common guidance single-sourced there
- [llms.txt](llms.txt) — One-page core reference
- [README.md](README.md) — Human-facing installation and overview
