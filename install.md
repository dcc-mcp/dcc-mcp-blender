# dcc-mcp-blender Agent Install

Use this page when an agent is asked to install or configure
`loonghao/dcc-mcp-blender` for Blender.

## Agent Instruction

If the user says "帮我参考 loonghao/dcc-mcp-blender/install.md 去安装",
do this:

1. Read `skills/dcc-mcp-blender-setup/SKILL.md`.
2. Run the setup script from the repository root.
3. Help the user enable the Blender add-on (or start the server in Blender).
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
common install locations, then runs `<blender_python> -m pip install ...`.

## Blender Add-on Step

After the script finishes, the user must enable the add-on in Blender:

1. Open Blender (4.2+ recommended).
2. Go to `Edit > Preferences > Extensions > Install from Disk…`.
3. Select the release ZIP (`dcc_mcp_blender_addon_<platform>_vX.Y.Z.zip`).
4. Enable **DCC MCP Blender** — the embedded server starts automatically.

The Blender 4.2+ add-on ZIP bundles the matching `dcc-mcp-core` wheel inside the
extension's isolated environment, so the manual pip step is only needed for
pip / CI scenarios. For those, start the server from Blender's Python console:

```python
import dcc_mcp_blender
dcc_mcp_blender.start_server()
```

Blender uses first-wins auto-gateway on port `8765`, so the MCP server is
exposed at:

```text
http://127.0.0.1:8765/mcp
```

## MCP Config

Use this JSON for Cursor, Claude Desktop, or any MCP Streamable HTTP host:

```json
{
  "mcpServers": {
    "blender": {
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}
```

The setup script also writes the config snippet and a smoke prompt under:

```text
.dcc-mcp/agent-setup/
```
