# AGENTS.md — dcc-mcp-blender Agent Navigation Map

> Progressive disclosure: this file is a **map**, not an encyclopedia.
> Follow the links for depth. Stay here for breadth.

---

## 30-Second Summary

`dcc-mcp-blender` embeds a standards-compliant MCP Streamable HTTP server directly inside Blender. It exposes 200+ Blender operations as MCP tools that any AI agent (Claude, Gemini, Cursor, etc.) can call over HTTP — no external gateway, no subprocess bridge.

**Current version:** 0.1.20 <!-- x-release-please-version -->
**Core dependency:** `dcc-mcp-core>=0.19.9,<1.0.0`
**Python:** 3.10+ (bundled with Blender)
**Blender:** 3.6 LTS, 4.2 LTS, 4.3, 4.4

---

## Quick Start (3 Lines)

```python
import dcc_mcp_blender
handle = dcc_mcp_blender.start_server(port=8765)
# MCP client connects to http://127.0.0.1:8765/mcp
```

Or install the Blender extension (ZIP) and the server starts automatically.

---

## Information Layers — Pick Your Depth

### Layer 1 — You Are a User / Operator
*Goal: Install, configure, and connect an MCP host.*

- **README.md** — Installation, quick start, environment variables, bundled tools list.
- **install.md** — Agent-facing setup entry: install pip dependencies, guide Blender add-on loading, and run a first smoke prompt.
- **skills/dcc-mcp-blender-setup/SKILL.md** — Setup skill reference, one-command install script.
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

## Key Environment Variables

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
- [CLAUDE.md](CLAUDE.md) — Claude Desktop-specific integration
- [GEMINI.md](GEMINI.md) — Gemini-specific integration
- [llms.txt](llms.txt) — One-page core reference for AI agents
- [install.md](install.md) — Agent-facing setup workflow
