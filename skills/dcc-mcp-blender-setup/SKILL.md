---
name: dcc-mcp-blender-setup
description: |-
  Set up dcc-mcp-blender for an agent or operator: install Blender Python
  dependencies with Blender's bundled interpreter, generate MCP host
  configuration, guide the user through enabling the Blender add-on, and run a
  first live-tool smoke prompt.
license: MIT
allowed-tools: Bash Read
metadata:
  dcc-mcp:
    dcc: blender
    layer: operator
    stage: bootstrap
    version: 1.0.0
    tags:
    - blender
    - mcp
    - setup
    - addon
    - bootstrap
---
# dcc-mcp-blender setup

Use this skill when a user wants an agent to prepare a machine so any MCP
host can use `dcc-mcp-blender` with Blender.

This is an operator skill, not a Blender runtime skill. Do not load it through
the Blender MCP server. Run it from the repository checkout or copy its steps
into another agent's instructions.

If the user says "帮我参考 `dcc-mcp/dcc-mcp-blender/install.md` 去安装", read the
root `install.md` first, then follow this skill.

## Goal

End with:

- `dcc-mcp-blender` and its pip dependencies installed into the target Blender
  bundled-Python environment (or available via the add-on ZIP's isolated
  wheels).
- An MCP host config snippet that points to the Blender MCP server.
- The user guided to enable the **DCC MCP Blender** add-on so the embedded
  server starts.
- A live smoke prompt that proves the agent can discover and call Blender tools.

## Fast Path

From the repository root, run:

```bash
python skills/dcc-mcp-blender-setup/scripts/setup_dcc_mcp_blender.py
```

The script:

1. Finds Blender's bundled Python from `--blender-python` / `--python`,
   `BLENDER_PYTHON`, `DCC_MCP_BLENDER_PYTHON`, a `blender` launcher on `PATH`,
   or common install locations on Windows/macOS/Linux
   (`<blender>/<major.minor>/python/bin/python(.exe)`).
2. Installs this checkout into Blender's Python: `python -m pip install -e .`.
   `dcc-mcp-blender` ships no optional extras, so the package is installed
   plainly and `dcc-mcp-core` is resolved transitively.
3. Verifies `import dcc_mcp_blender`.
4. Writes a reusable MCP JSON snippet and smoke prompt under
   `.dcc-mcp/agent-setup/`.

Use PyPI instead of the local checkout when setting up an end-user machine:

```bash
python skills/dcc-mcp-blender-setup/scripts/setup_dcc_mcp_blender.py --source pypi
```

If discovery fails, ask the user for the full Blender Python path and re-run:

```bash
python skills/dcc-mcp-blender-setup/scripts/setup_dcc_mcp_blender.py --blender-python "C:\Program Files\Blender Foundation\Blender 4.2\4.2\python\bin\python.exe"
```

> Blender 4.2+ add-on installs (Option 1 in `README.md`) bundle the
> `dcc-mcp-core` wheel inside the extension's isolated environment, so a manual
> pip step into Blender's Python is only required for pip/CI scenarios or older
> Blender add-on layouts.

## MCP Configuration

Blender uses first-wins auto-gateway on port `8765`. Configure the MCP host
with:

```json
{
  "mcpServers": {
    "blender": {
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}
```

When multiple Blender instances run, the first to bind `8765` becomes the
gateway and later instances register behind it; point your host at `8765`.

When editing an existing MCP config, preserve unrelated servers. Merge only the
`blender` server entry unless the user asks for a different server name.

## User Hand-Off: Enable the Blender Add-on

After pip setup and MCP JSON generation, tell the user:

1. Open Blender (4.2+ recommended).
2. Go to `Edit > Preferences > Extensions > Install from Disk…`.
3. Select the release ZIP
   (`dcc_mcp_blender_addon_<platform>_vX.Y.Z.zip` from the Releases page).
4. Enable **DCC MCP Blender**.
5. The embedded MCP server starts automatically; use the top-bar
   `DCC MCP > Show Server URLs…` menu to confirm the URL.

The expected URL is `http://127.0.0.1:8765/mcp`.

For pip/CI installs without the add-on, start the server from Blender's Python
console instead:

```python
import dcc_mcp_blender
dcc_mcp_blender.start_server()
```

Or run headless:

```bash
blender --background --python src/dcc_mcp_blender/blender_bootstrap.py
```

## First Live Smoke Prompt

Ask the MCP host to run this prompt after Blender is open and the add-on is
enabled:

```text
Use the Blender MCP server. First call dcc_capability_manifest with loaded_only=false.
Then load the blender-geometry skill, create a sphere named mcp_setup_smoke_sphere
with radius 2, list scene objects, and tell me the MCP URL and created object name.
Use typed tools where available and avoid execute_python unless no typed tool fits.
```

Expected behavior:

- The agent discovers capabilities without dumping every schema.
- The agent loads `blender-geometry`.
- The agent calls `blender_geometry__create_sphere`.
- The new object appears in the Blender scene.
- `blender_scene__list_objects` or another scene query confirms it exists.

## Troubleshooting

- Blender Python not found: ask for the exact Blender version and the
  `<blender>/<major.minor>/python/bin/python(.exe)` path, then pass
  `--blender-python`.
- Pip bootstrap fails: run `<blender_python> -m ensurepip --upgrade`, then
  repeat the install.
- MCP connection refused: Blender is not running, the add-on is not enabled, or
  the embedded server has not started yet.
- Tool missing: call `dcc_capability_manifest` or `search_skills`, then
  `load_skill("<skill-name>")`.
- Add-on enabled but no server: check Blender's system console for
  `[DCC MCP Blender]` startup lines, and verify firewall/localhost rules.
