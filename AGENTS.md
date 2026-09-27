# AGENTS.md — dcc-mcp-blender Agent Navigation Map

> Progressive disclosure: this file is a **map**, not an encyclopedia.
> Follow the links for depth. Stay here for breadth.

## Agent Control Path

AI agent runtimes default to the shared gateway through the
`dcc-mcp` skill and `dcc-mcp-cli` REST commands:

```bash
dcc-mcp-cli search --query "<task>" --dcc-type blender
dcc-mcp-cli describe <tool-slug>
dcc-mcp-cli call <tool-slug> --json '{"key":"value"}'
```

Use `dcc-mcp-cli list` for live instances and `dcc-mcp-cli dcc-types` for
release-catalog support. IDE users may continue to configure the gateway MCP
endpoint; adapter-local Python start APIs are for host bootstrap and tests.

### CLI availability and updates

If `dcc-mcp-cli` is missing, obtain user consent before using the official
install commands in the README Agent workflow. Keep an official build current
with:

```bash
dcc-mcp-cli update check
dcc-mcp-cli update apply
```

`update apply` stages the latest CLI for the next launch; it does not replace
a running server.

---

## 30-Second Summary

`dcc-mcp-blender` embeds a standards-compliant MCP Streamable HTTP server directly inside Blender. It exposes 200+ Blender operations as MCP tools that any AI agent (Claude, Gemini, Cursor, etc.) can call over HTTP — no external gateway, no subprocess bridge.

**Current version:** 0.2.3 <!-- x-release-please-version -->
**Core dependency:** `dcc-mcp-core>=0.20.0,<0.21.0`
**Python:** Use Blender's bundled interpreter; Blender 4.5 uses 3.11, 5.2 uses 3.13.
**Blender CI targets:** 4.5.13 LTS and 5.2.1 on Windows/Linux/macOS; 4.5 is the
minimum supported host and acceptance boundaries are documented in README.md.
**Coverage:** See [docs/capability-coverage.md](docs/capability-coverage.md).

---

## Quick Start (3 Lines)

```python
import dcc_mcp_blender
handle = dcc_mcp_blender.start_server()
# MCP client connects through http://127.0.0.1:9765/mcp
```

Or install the Blender extension (ZIP) and the server starts automatically.

---

## Information Layers — Pick Your Depth

### Layer 1 — You Are a User / Operator
*Goal: Install, configure, and connect an MCP host.*

- **README.md** — Installation, quick start, environment variables, bundled tools list.
- **install.md** — Agent-facing setup entry: install pip dependencies, guide Blender add-on loading, and run a first smoke prompt.
- **skills/dcc-mcp-blender-setup/SKILL.md** — Setup skill reference, one-command install script.
- **skills/dcc-blender-assembly-pitfalls/SKILL.md** — Failure-mode skill: read before creating, sizing, orienting, or joining geometry through MCP.
- **src/dcc_mcp_blender/skills/SKILLS_INDEX.md** — Staged loading guidance, task-to-skill chains, side-effect profiles for all bundled skills.

### Layer 2 — You Are a Skill Author
*Goal: Write new Blender automation skills and register them as MCP tools.*

- **src/dcc_mcp_blender/api.py** — `@with_main_thread` decorator, `blender_success` / `blender_error` helpers, context snapshot wrappers.
- **src/dcc_mcp_blender/capabilities.py** — Capability manifest builder; each skill registers its action list so agents can discover tools without loading the full catalog.
- **src/dcc_mcp_blender/_scene_ops.py**, **src/dcc_mcp_blender/_mesh_ops.py**, etc. — Reference implementations for each domain skill.
- **pyproject.toml** — `[project.entry-points."dcc_mcp.adapters"]` declares `blender = "dcc_mcp_blender:BlenderMcpServer"`.

Create a new skill package under `src/dcc_mcp_blender/skills/<your-skill>/` with:
1. `SKILL.md` — metadata, dependencies, tools yaml path
2. `tools.yaml` — tool definitions (name, description, inputSchema)
3. `scripts/*.py` — implementation scripts (one file per tool or group)

### Layer 3 — You Are a Core Developer
*Goal: Understand the server lifecycle, dispatcher architecture, and integration points.*

- **src/dcc_mcp_blender/server.py** — `BlenderMcpServer`, builtin action registration, metrics, jobs
- **src/dcc_mcp_blender/dispatcher/** — `BlenderUiDispatcher` (GUI mode) and `BlenderHost` (headless) dispatcher implementations
- **src/dcc_mcp_blender/host.py** — Host adapter that abstracts Blender's main thread from MCP request threads
- **src/dcc_mcp_blender/blender_bootstrap.py** — Headless CI/automation bootstrap entry point
- **src/dcc_mcp_blender/context_snapshot.py** — Scene context provider (selection, frame, scene name, version)
- **src/dcc_mcp_blender/_readiness.py** — Three-state readiness probe (process, dispatcher, dcc)

---

## Agent Contract Files

`AGENTS.md` is the **only** agent contract file at the repository root. It is the
native instruction file for Codex, OpenCode, Cursor, GitHub Copilot, Windsurf,
Cline, Roo Code, Kiro, Trae, and Augment, and Claude Code falls back to it when
no `CLAUDE.md` exists. Guidance that used to live in `CLAUDE.md` and `GEMINI.md` has been folded
into [**Client Integration Notes**](#client-integration-notes) below.

**Gemini CLI exception:** Gemini CLI defaults its context file to `GEMINI.md`. To
make it read `AGENTS.md`, set `context.fileName` once in `~/.gemini/settings.json`:

```json
{
  "context": {
    "fileName": ["AGENTS.md", "GEMINI.md"]
  }
}
```


---

## Client Integration Notes

All MCP clients use the same endpoint — `http://127.0.0.1:9765/mcp` (MCP
Streamable HTTP, spec `2025-03-26`).

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "blender": {
      "url": "http://127.0.0.1:9765/mcp"
    }
  }
}
```

File locations:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Restart Claude Desktop after editing.

**Progressive loading.** By default the server starts with a minimal set of
built-in tools active:

- `execute_python`, `execute_script_file`, `get_blender_info`
- `get_scene_info`, `get_session_info`, `list_objects`
- `search_tools`, `list_skills`, `load_skill`

**All other skills appear as `__skill__<name>` stubs.** When a tool from an
unloaded skill is needed:

1. Call `load_skill("blender-animation")` to expand the skill.
2. Then call the desired tool (e.g. `blender_animation__set_keyframe`).

**Claude-specific tips.**

- **Viewport feedback:** ask the model to call `capture_viewport` after geometry changes — the result is a base64-encoded PNG it can "see" in the conversation.
- **Cancellation:** the client can send `notifications/cancelled` for long renders; skill scripts that poll `check_blender_cancelled()` exit cleanly.
- **Code execution:** prefer `search_skills` → `load_skill` → typed tools with `inputSchema`. Use `execute_python` only when no skill covers the task (bulk in-Blender loops, bpy API gaps, one-offs). Operators can refuse it with `DCC_MCP_BLENDER_DISABLE_EXECUTE_PYTHON=1` or `DCC_MCP_BLENDER_DISABLE_ARBITRARY_SCRIPT=1`.

### Gemini

Gemini is strong at generating whole skill packages. Author scripts against
`dcc_mcp_blender.api`:

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

Results are nested JSON that Gemini parses directly:

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

Discover capabilities with `search_skills("render batch")` and
`search_tools(query="bake", tags=["texture"])`, then generate `SKILL.md`,
`tools.yaml`, and `scripts/*.py` into a directory listed in
`DCC_MCP_BLENDER_SKILL_PATHS`. Feed `capture_viewport` base64 PNGs back to Gemini
for visual state verification.

---

## ## Key Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DCC_MCP_BLENDER_SEMANTIC_INDEX` | `0` | Enable hybrid BM25 + vector skill search (opt-in) |
| `DCC_MCP_BLENDER_METRICS` | `false` | Enable Prometheus `/metrics` |
| `DCC_MCP_BLENDER_DISABLE_EXECUTE_PYTHON` | `false` | Restrict arbitrary Python execution |
| `DCC_MCP_BLENDER_SKILL_PATHS` | — | Additional skill search paths |
| `DCC_MCP_BLENDER_PROJECT_TOOLS` | — | Set to `0` to opt out of project tools |
| `DCC_MCP_BLENDER_RESOURCES` | — | Set to `0` to opt out of MCP resource publishing |

See **README.md** for the full env var table.

---

## Key Files

| File | Purpose |
|------|---------|
| `src/dcc_mcp_blender/server.py` | `BlenderMcpServer`, builtin skill discovery, metrics, jobs |
| `src/dcc_mcp_blender/dispatcher/__init__.py` | Thread-affinity dispatchers for GUI and headless modes |
| `src/dcc_mcp_blender/host.py` | Host adapter (abstracts Blender main thread) |
| `src/dcc_mcp_blender/api.py` | Skill authoring helpers |
| `src/dcc_mcp_blender/context_snapshot.py` | Scene / selection / frame context provider |
| `src/dcc_mcp_blender/skills/` | 25+ built-in skill packages (200+ typed MCP tools) |
| `src/dcc_mcp_blender/skills/SKILLS_INDEX.md` | Staged loading guide and task-to-skill maps |
| `README.md` | Human overview |
| `llms.txt` | One-page core reference for AI agents |

---

## See Also

- [README.md](README.md) — Installation, features, all env vars
- [Client Integration Notes](#client-integration-notes) — Claude Desktop config, progressive loading, Gemini skill generation
- [llms.txt](llms.txt) — One-page core reference for AI agents
- [install.md](install.md) — Agent-facing setup workflow
