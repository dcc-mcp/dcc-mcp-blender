# Blender MCP vs dcc-mcp-blender

This page answers one question: **which Blender MCP server should I connect my
agent to?**

There are two common answers, and they optimize for different things. Read the
[at-a-glance table](#at-a-glance), then jump to
[when to choose which](#when-to-choose-which).

> **Facts on this page were verified against upstream sources on 2026-09-23.**
> Third-party projects move fast; re-check the linked sources before making a
> long-term decision.

---

## Is there an "official" Blender MCP?

**No. As of 2026-09-23 there is no MCP server published by the Blender project.**

This matters because the phrase "official Blender MCP" circulates widely. The
evidence:

- The `blender` GitHub organization publishes 21 public repositories
  ([list](https://github.com/orgs/blender/repositories)); none of them is an
  MCP server.
- The Blender source tree (`blender/blender`) and the bundled add-on tree
  (`blender/blender-addons`) contain no MCP-related paths.
- The most widely used Blender MCP — [`ahujasid/mcp-for-blender`][mcp-for-blender],
  formerly `blender-mcp` — states in its own README:

  > **Disclaimer:** This is a third-party integration and not made by Blender

So "official Blender MCP" is a misnomer for a community project. This page
compares dcc-mcp-blender against **that** project, because it is what people
actually mean when they say "Blender MCP".

[mcp-for-blender]: https://github.com/ahujasid/mcp-for-blender

---

## At a glance

| Dimension | `mcp-for-blender` (formerly `blender-mcp`) | `dcc-mcp-blender` |
|---|---|---|
| Maintainer | Third-party, single maintainer (`ahujasid`) | `dcc-mcp` organization |
| Made by Blender? | **No** — README disclaims it explicitly | No (third-party, same as any adapter) |
| License | MIT | MIT |
| Minimum Blender | 3.0 or newer | 4.2+ for the extension ZIP; CI targets 5.2.1 LTS (Python 3.13) and 4.5.13 LTS (Python 3.11), with legacy coverage for 3.6.5 / 4.2.0 / 4.3.2 / 4.4.3 |
| Architecture | Blender add-on opens a **socket server**; a **separate** MCP process speaks stdio to the client and relays over TCP (default port `9876`) | MCP server runs **embedded** inside Blender's Python interpreter — no external process |
| Transport | stdio (client to server), TCP socket (server to Blender) | Streamable HTTP, `POST /mcp` (endpoint returned by `BlenderMcpServer.mcp_url`) |
| MCP protocol | Implements MCP; version matrix not published in the README | `2025-03-26` and `2025-06-18` (see [protocol compatibility](protocol-compatibility.md)) |
| Tool surface | Focused set: objects, materials, scene inspection, code execution, plus built-in generative-3D and asset integrations | 200+ typed tools across 25+ skill packages, loaded progressively |
| Skill loading | Not applicable | Staged (`search_skills` to `load_skill` to call); see `src/dcc_mcp_blender/skills/SKILLS_INDEX.md` |
| Arbitrary Python | **On by default** — the AI can run any Python in Blender | Typed tools are the intended path; `execute_python` and `execute_script_file` are escape hatches |
| Execution guardrails | Opt-in `BLENDER_MCP_SAFE_MODE=1` — pre-checks scripts and blocks file, subprocess, network and persistence calls | Opt-out `DCC_MCP_BLENDER_DISABLE_ARBITRARY_SCRIPT` / `DCC_MCP_BLENDER_DISABLE_EXECUTE_PYTHON` — both escape hatches refuse to run while either is set |
| Network exposure | Add-on socket has **no authentication or encryption**; anyone who can reach the port can run Python inside Blender | Loopback HTTP endpoint; see the Configuration section of the README for the execution opt-outs |
| Cross-DCC scope | Blender only | Shares the `dcc-mcp` gateway and `dcc-mcp-cli` surface with Maya, Houdini, USD, 3ds Max and others |
| Generative 3D / assets | Bundled: Poly Haven, Sketchfab, Poly Pizza, Hyper3D Rodin, Hunyuan3D | Installed on demand from the marketplace — see [extending with marketplace skills](#extending-with-marketplace-skills) |

---

## When to choose which

### Choose `mcp-for-blender` when

- You want the **shortest path** from "I have Blender" to "an LLM is moving cubes".
- Your work is **exploratory**: prompt-assisted modeling, scene inspection, one-off
  lookdev experiments.
- You need **Blender 3.x** support, which predates dcc-mcp-blender's extension ZIP
  requirement.
- You want generative-3D and asset integrations working **out of the box** rather
  than installing them separately.

### Choose `dcc-mcp-blender` when

- You are wiring Blender into a **production pipeline**: validation, publish
  manifests, render-farm submission, export presets, asset metadata.
- You want **typed, schema-validated tools** instead of free-form code execution.
  Typed tools fail loudly and are testable; generated `bpy` scripts are not.
- You want to **restrict arbitrary code execution** for fleet or unattended runs.
- You work **across several DCCs** and want one gateway, one CLI, and one skill
  convention for Blender, Maya, Houdini, USD and 3ds Max.
- You need **headless / CI** operation, including background Blender tests and
  separate-process MCP smoke tests.

### Use both

The two are not mutually exclusive: `mcp-for-blender` exposes its socket on a
configurable port, and dcc-mcp-blender registers its own instance. If you run
both, keep their ports distinct and remember that neither is a security boundary
on a shared or untrusted network.

---

## Extending with marketplace skills

dcc-mcp-blender deliberately does **not** bundle third-party models or asset
libraries into the adapter core. Those arrive as marketplace skills, installed on
demand:

```bash
# Discover what is available
dcc-mcp-cli marketplace search

# Install an integration
dcc-mcp-cli marketplace install dcc-asset-polyhaven
dcc-mcp-cli marketplace install dcc-ai-hunyuan3d
```

Generative-3D and asset integrations that exist as marketplace skills include:

| Marketplace entry | What it provides | DCCs |
|---|---|---|
| `dcc-ai-hunyuan3d` | Hunyuan3D generative 3D | Maya, Blender, Houdini, 3ds Max |
| `dcc-ai-tripo3d` | Tripo3D generative 3D | Maya, Blender, Houdini, 3ds Max |
| `dcc-asset-polyhaven` | Poly Haven HDRIs, textures and models | Maya, Blender, Houdini, 3ds Max, Photoshop |
| `dcc-asset-sketchfab` | Sketchfab model search | Maya, Blender, Houdini, 3ds Max |
| `dcc-asset-poly-pizza` | Poly Pizza low-poly models | Any |
| `dcc-asset-ambientcg` | ambientCG PBR materials | Maya, Blender, Houdini, 3ds Max |

Catalog contents on 2026-09-23: 41 entries, every one reporting
`policy.installation: available`. Run `dcc-mcp-cli marketplace search` for the
current list — the catalog is the source of truth, not this page.

Because the same skill entries declare multiple DCCs, one install can serve a
Blender session and a Maya session through the same gateway.

---

## Sources

Verified on 2026-09-23:

- [`ahujasid/mcp-for-blender`][mcp-for-blender] — features, prerequisites
  (Blender 3.0+, Python 3.10+, `uv`), two-component architecture,
  `BLENDER_MCP_SAFE_MODE`, and the socket security note.
- [Blender GitHub organization](https://github.com/orgs/blender/repositories) —
  21 public repositories, none an MCP server.
- `blender/blender` and `blender/blender-addons` source trees — no MCP paths.
- This repository's `README.md`, `llms.txt`, and
  [protocol compatibility](protocol-compatibility.md) — dcc-mcp-blender facts.
- `dcc-mcp-cli marketplace search` — marketplace catalog contents.
