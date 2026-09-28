# AGENTS.md — dcc-mcp-blender

> Navigation map for AI agents. Detailed API lives in `README.md` and `llms.txt`.
> This file is a **map**, not an encyclopedia — follow the links for depth.

## Build & test

```bash
vx just setup              # install dev deps + verify imports
vx just check              # ruff lint + quick tests
vx just prek               # pre-commit gate: autofix, format, lint, quick tests
vx just ci                 # lint-all + coverage (local CI simulation)
```

Host-side helpers (verify recipe names in `justfile` before inventing new ones):

```bash
vx just blender-link           # symlink src/dcc_mcp_blender into Blender's addons dir
vx just blender-link-win       # same, PowerShell (native Windows)
vx just blender-addon-zip      # build the installable extension ZIP into dist_addon/
vx just test file=tests/test_api.py   # run one test file
```

## Agent control path

AI agent runtimes default to the shared gateway through the `dcc-mcp` skill and
`dcc-mcp-cli` REST commands:

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

`update apply` stages the latest CLI for the next launch; it does not replace a
running server.

## Quick start

```python
import dcc_mcp_blender
handle = dcc_mcp_blender.start_server()
# MCP client connects through http://127.0.0.1:9765/mcp
```

Or install the Blender extension (ZIP) and the server starts automatically.

## Quick facts

- **Target host:** Blender **4.5+** (4.5.13 LTS and 5.2.1 are the CI targets on
  Windows/Linux/macOS). 4.5 is the minimum supported host; acceptance boundaries
  are documented in `README.md`.
- **Python:** use Blender's bundled interpreter — Blender 4.5 ships 3.11, 5.2
  ships 3.13.
- **Core dependency:** `dcc-mcp-core>=0.20.0,<0.21.0`; entry point declared in
  `pyproject.toml` under `[project.entry-points."dcc_mcp.adapters"]`.
- **Do not assume:** an external gateway or subprocess bridge is required — the
  MCP Streamable HTTP server runs inside Blender.

## Skills-first workflow

```
search_skills(query="render")  → find a typed skill
load_skill("blender-animation") → expand its tools
call blender_animation__set_keyframe
execute_python only when no typed skill fits
```

## Repo layout

| Path | Role |
|---|---|
| `src/dcc_mcp_blender/server.py` | `BlenderMcpServer` composition root, metrics, jobs |
| `src/dcc_mcp_blender/dispatcher/` | GUI + headless thread-affinity dispatchers |
| `src/dcc_mcp_blender/host.py` | Host adapter abstracting Blender's main thread |
| `src/dcc_mcp_blender/api.py` | Skill authoring helpers (`blender_success`, `with_main_thread`) |
| `src/dcc_mcp_blender/context_snapshot.py` | Scene / selection / frame context provider |
| `src/dcc_mcp_blender/skills/` | 25+ bundled skill packages (200+ typed MCP tools) |
| `src/dcc_mcp_blender/skills/SKILLS_INDEX.md` | Authoritative skill + tool index, staged loading |
| `tests/` | Unit, contract, packaging and e2e tests |
| `tools/` | Skill linter, version probe, Windows dev-link helpers |
| `packaging/` | Addon ZIP assembly (`assemble_zip.py`) + release smoke checklist |
| `docs/` | Capability coverage, protocol compatibility, vendor integrations |

## Reference material (follow, do not inline)

- **Bundled skill + tool inventory:** `src/dcc_mcp_blender/skills/SKILLS_INDEX.md`
- **Capability coverage:** [docs/capability-coverage.md](docs/capability-coverage.md)
- **Environment variables:** `README.md` (full `DCC_MCP_BLENDER_*` table)
- **One-page core reference:** `llms.txt`
- **Agent-facing install:** `install.md`
- **Setup skill:** `skills/dcc-mcp-blender-setup/SKILL.md`
- **Geometry pitfalls:** `skills/dcc-blender-assembly-pitfalls/SKILL.md`

## Vendor integration notes

- [docs/integrations/claude.md](docs/integrations/claude.md) — Claude Desktop
  config, progressive loading, viewport + cancellation tips.
- [docs/integrations/gemini.md](docs/integrations/gemini.md) — Gemini / Vertex
  setup, code-first skill generation, structured result parsing.

## Release

- release-please drives versioning from Conventional Commits on `main`.
- Whether a release is cut at all is a changelog question, not a prefix question: if every
  commit in the batch lands in a `hidden: true` section the changelog entry is empty, and
  release-please skips the whole batch — no release pull request, **no version bump**
  (`strategies/base.ts` logs “No user facing commits found since … - skipping” when
  `changelogEmpty()` finds only the heading line).
- This repo overrides `changelog-sections` in `release-please-config.json`: `feat:`, `fix:`, 
  `perf:`, `refactor:` and `docs:` are **visible**; `style:`, `chore:`, `test:`, `ci:` and
  `build:` are `hidden: true`. A visible `refactor:` therefore cuts a release.
- Only once a release *is* cut does the prefix choose the bump. This repo is pre-1.0 and sets
  `bump-minor-pre-major` and `bump-patch-for-minor-pre-major`, so on `0.x`: breaking → minor
  and `feat:` → **patch** — not major/minor. Anything else → patch.
- Use `chore:` when the batch should **not** cut a release; use `docs:` when doc-only work
  should cut a patch release.

## Do / Don't

- **Do** single-source agent instructions here. This is the only agent contract
  file at the repo root.
- **Do** keep this file a navigation map — long reference material belongs in
  `docs/` or the skill index.
- **Don't** add `CLAUDE.md` / `GEMINI.md` / `CURSOR.md` / `ANTHROPIC.md` /
  `OPENAI.md` / `COPILOT.md` / `CODEBUDDY.md` / `.cursorrules` / `.clinerules` /
  `.windsurfrules` at the root. Vendor-specific notes live under
  `docs/integrations/`, linked from here.
- **Don't** hardcode an exact version in tests (`assert __version__ == "X.Y.Z"`)
  — release-please bumps will break it. Use `>=` or read package metadata.
- **Don't** commit build artifacts to the repo root (`*.o`, `coverage.json`,
  `audit-result.json`, `clippy_check.txt`, `commit_msg.txt`).
