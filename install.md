# dcc-mcp-blender Agent Install

Use this page when an agent is asked to install or configure
`dcc-mcp/dcc-mcp-blender` for Blender.

## Agent Instruction

If the user says "帮我参考 dcc-mcp/dcc-mcp-blender/install.md 去安装",
do this:

1. Read `skills/dcc-mcp-blender-setup/SKILL.md`.
2. Run the setup script from the repository root.
3. Open Blender so the installed startup script can start the server.
4. Configure the MCP host with the generated Streamable HTTP JSON.
5. Run the smoke prompt to prove the connection works.

## One Command

From the repository root:

```bash
python skills/dcc-mcp-blender-setup/scripts/setup_dcc_mcp_blender.py
```

For an end-user install from PyPI instead of this checkout:

```bash
python skills/dcc-mcp-blender-setup/scripts/setup_dcc_mcp_blender.py --source pypi
```

If Blender's bundled Python is not auto-detected:

```bash
python skills/dcc-mcp-blender-setup/scripts/setup_dcc_mcp_blender.py --blender-python "C:\Program Files\Blender Foundation\Blender 4.2\4.2\python\bin\python.exe"
```

Blender ships its own Python at `<blender>/<major.minor>/python/bin/python(.exe)`.
The script discovers it via env vars (`BLENDER_PYTHON`, `DCC_MCP_BLENDER_PYTHON`),
the `--blender-python` / `--python` argument, a `blender` launcher on `PATH`, or
common install locations, then runs `<blender_python> -m pip install ...`. It
also writes `dcc_mcp_blender_startup.py` under Blender's per-user
`scripts/startup` directory. The startup bridge exposes Blender 5.x-compatible
`register()` / `unregister()` hooks and starts the server once Blender loads it.

## Read-only Blender Python fallback

If Blender's bundled `site-packages` is not writable, install to the user site:

```bash
<blender-python> -m pip install --user --upgrade dcc-mcp-blender
python skills/dcc-mcp-blender-setup/scripts/setup_dcc_mcp_blender.py --source pypi --user
```

The `--user` fallback must be paired with Blender's system-environment flag so
Blender includes the user site-packages directory:

```bash
blender --python-use-system-env
```

The setup script prints this launch command whenever `--user` is selected.

## Blender Extension alternative

The release ZIP is an alternative to the pip/startup-script path above. It
bundles the matching `dcc-mcp-core` wheel in Blender's isolated extension
environment, so do not run the manual pip setup when using the ZIP:

1. Open Blender (4.2+ required).
2. Go to `Edit > Preferences > Extensions > Install from Disk…`.
   (Not `Add-ons > Install` — this ZIP uses the Blender 4.2+ Extension
   format; the legacy add-on path is unsupported.)
3. Select the release ZIP (`dcc_mcp_blender_addon_<platform>_vX.Y.Z.zip`).
4. Enable **DCC MCP Blender** — the embedded server starts automatically.

Blender instances use OS-assigned ports and register with the stable gateway:

```text
http://127.0.0.1:9765/mcp
```

## MCP Config

Use this JSON for Cursor, Claude Desktop, or any MCP Streamable HTTP host:

```json
{
  "mcpServers": {
    "blender": {
      "url": "http://127.0.0.1:9765/mcp"
    }
  }
}
```

The setup script also writes the config snippet and a smoke prompt under:

```text
.dcc-mcp/agent-setup/
```
