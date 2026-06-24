# CLAUDE.md — Claude Desktop / Anthropic API Integration Guide

> Claude-specific integration notes for `dcc-mcp-blender`.
> For the full project map, see [AGENTS.md](AGENTS.md).

---

## What This Project Does

`dcc-mcp-blender` embeds an MCP Streamable HTTP server directly inside Blender. Claude Desktop (or any Anthropic API client using MCP) can call 200+ Blender tools over HTTP without any external gateway process.

---

## Claude Desktop Configuration

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "blender": {
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}
```

**File locations:**
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Restart Claude Desktop after editing.

---

## Progressive Loading — Important for Claude

By default, `dcc-mcp-blender` starts with a minimal set of built-in tools active:
- `execute_python`, `execute_script_file`, `get_blender_info`
- `get_scene_info`, `get_session_info`, `list_objects`
- `search_tools`, `list_skills`, `load_skill`

**All other skills appear as `__skill__<name>` stubs.** When Claude needs a tool from an unloaded skill, it should:

1. Call `load_skill("blender-animation")` to expand the skill.
2. Then call the desired tool (e.g., `blender_animation__set_keyframe`).

This keeps the initial `tools/list` small and fast for Claude to parse.

---

## Claude-Specific Tips

- **Viewport feedback:** Ask Claude to call `capture_viewport` after geometry changes. The result is a base64-encoded PNG that Claude can "see" in the conversation.
- **Cancellation:** Claude can send `notifications/cancelled` for long renders. Skill scripts that poll `check_blender_cancelled()` will exit cleanly.
- **Code execution:** Prefer `search_skills` → `load_skill` → typed tools with `inputSchema`. Use `execute_python` only when no skill covers the task (bulk in-Blender loops, bpy API gaps, one-offs). Operators can refuse it with `DCC_MCP_BLENDER_DISABLE_EXECUTE_PYTHON=1` or `DCC_MCP_BLENDER_DISABLE_ARBITRARY_SCRIPT=1`.

---

## Quick Test Prompts

> "Create a red sphere in Blender"
> "List all cameras in the scene and set the active camera to Camera.001"
> "Capture the viewport so I can see the current state"
> "Load the blender-animation skill and set a keyframe on the sphere's location Z at frame 10"

---

## See Also

- [AGENTS.md](AGENTS.md) — Shared agent navigation map; keep common guidance single-sourced there
- [llms.txt](llms.txt) — One-page core reference
- [README.md](README.md) — Human-facing installation and overview
