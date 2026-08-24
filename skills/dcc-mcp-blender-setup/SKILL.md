---
name: dcc-mcp-blender-setup
description: |-
  Set up dcc-mcp-blender for an agent or operator: install Blender Python
  dependencies with Blender's bundled interpreter, install a startup bridge,
  generate MCP host configuration, and run a first live-tool smoke prompt.
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
  bundled-Python environment.
- An MCP host config snippet that points to the Blender MCP server.
- A Blender 5.x-compatible startup bridge that starts the embedded server.
- A live smoke prompt that proves the agent can discover and call Blender tools.

## Fast Path

Use the installed adapter lifecycle as the canonical agent path. First resolve
the exact Blender executable/application and its target Python interpreter,
then inspect the non-mutating plan:

```bash
dcc-mcp-blender install --json --dry-run --dcc-path <absolute-blender-path> --python <absolute-python-path>
```

Review the resolved host, version, profile, interpreter, file steps, and
machine-executable `next_steps`. If they are correct, execute the same plan and
verify typed readiness:

```bash
dcc-mcp-blender install --json --yes --dcc-path <absolute-blender-path> --python <absolute-python-path>
dcc-mcp-blender verify --json --dcc-path <absolute-blender-path> --python <absolute-python-path>
```

Exit `40` after install means the staged, receipted host integration was
written but `host.ping` could not yet prove a live Blender instance. Follow the
returned `next_steps`; do not report the adapter as directly usable yet.

The lifecycle command:

1. Probes Blender 3.6+ and the exact target Python before writing.
2. Resolves the per-user Blender scripts profile without changing the host
   installation directory.
3. Stages and atomically replaces the owned startup script with rollback.
4. Writes an ownership receipt used by `status`, `verify`, `upgrade`, and
   receipt-only `uninstall`.
5. Captures bootstrap failures and verifies a live instance with typed
   `host.ping` rather than a process or port-only check.

See the repository root `install.md` for all platforms, stable exit codes, and
repair/troubleshooting flows.

## Legacy compatibility path

The checkout-local script remains available for operators that still need the
pre-SOP pip/setup flow:

```bash
python skills/dcc-mcp-blender-setup/scripts/setup_dcc_mcp_blender.py
```

This compatibility script:

1. Finds Blender's bundled Python from `--blender-python` / `--python`,
   `BLENDER_PYTHON`, `DCC_MCP_BLENDER_PYTHON`, a `blender` launcher on `PATH`,
   or common install locations on Windows/macOS/Linux
   (`<blender>/<major.minor>/python/bin/python(.exe)`).
2. Installs this checkout into Blender's Python: `python -m pip install -e .`.
   `dcc-mcp-blender` ships no optional extras, so the package is installed
   plainly and `dcc-mcp-core` is resolved transitively.
3. Verifies `import dcc_mcp_blender`.
4. Writes a Blender 5.x-compatible `dcc_mcp_blender_startup.py` with
   `register()` / `unregister()` hooks into the per-user `scripts/startup`
   directory.
5. Writes a reusable MCP JSON snippet and smoke prompt under
   `.dcc-mcp/agent-setup/`.

Use PyPI instead of the local checkout with that legacy path:

```bash
python skills/dcc-mcp-blender-setup/scripts/setup_dcc_mcp_blender.py --source pypi
```

If discovery fails, ask the user for the full Blender Python path and re-run:

```bash
python skills/dcc-mcp-blender-setup/scripts/setup_dcc_mcp_blender.py --blender-python "C:\Program Files\Blender Foundation\Blender 4.2\4.2\python\bin\python.exe"
```

If Blender's bundled `site-packages` is read-only, select the user-site fallback:

```bash
python skills/dcc-mcp-blender-setup/scripts/setup_dcc_mcp_blender.py --source pypi --user
```

Then launch Blender with the required matching flag:

```bash
blender --python-use-system-env
```

Do not omit `--python-use-system-env`: Blender otherwise ignores packages
installed by pip with `--user`.

> Blender 4.2+ Extension ZIP installs (Option 1 in `README.md`) are an
> alternative path. They bundle `dcc-mcp-core` in an isolated environment and
> must not be combined with this pip/startup-script setup.

## MCP Configuration

Blender instances use OS-assigned ports. Configure the MCP host with the stable
local gateway:

```json
{
  "mcpServers": {
    "blender": {
      "url": "http://127.0.0.1:9765/mcp"
    }
  }
}
```

Multiple Blender instances register their exact endpoints automatically; use
`dcc-mcp-cli list` when a direct URL is required.

When editing an existing MCP config, preserve unrelated servers. Merge only the
`blender` server entry unless the user asks for a different server name.

## User Hand-Off: Start Blender

After pip setup and MCP JSON generation, tell the user:

1. Open Blender with the launch command printed by the setup script.
2. The installed `dcc_mcp_blender_startup.py` starts the server automatically.
3. Use `dcc-mcp-cli list` to confirm the Blender instance and exact URL.

The stable gateway URL is `http://127.0.0.1:9765/mcp`.

For a manual troubleshooting start from Blender's Python console:

```python
import dcc_mcp_blender
dcc_mcp_blender.start_server()
```

Or run headless:

```bash
blender --background --python src/dcc_mcp_blender/blender_bootstrap.py
```

## First Live Smoke Prompt

Ask the MCP host to run this prompt after Blender is open and registered:

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
- No server after launch: verify the startup script under the per-user
  `scripts/startup` directory, check Blender's system console, and verify
  firewall/localhost rules.
