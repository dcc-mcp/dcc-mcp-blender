# Install dcc-mcp-blender

This runbook installs, verifies, upgrades, and removes the Blender adapter under
[DCC-MCP Adapter Install SOP v1](https://dcc-mcp.github.io/dcc-mcp-core/guide/adapter-install-sop).
The standard lifecycle host-enables a package that is already installed in the
selected Blender interpreter. It never controls Blender's UI.

## Requirements

- **Blender:** 3.6 or newer for the Python/startup-hook path. The Blender
  Extensions ZIP requires Blender 4.2 or newer.
- **Python:** Blender's selected bundled interpreter, Python 3.7 or newer.
- **dcc-mcp-core:** `>=0.20.0,<1.0.0` in that exact interpreter.
- **Platforms:** Windows, macOS, and Linux.
- **Permissions:** write access to the selected version's user `scripts/startup`
  directory and the user receipt directory.

Install the package into Blender's interpreter first. Do not substitute an
unrelated `python` from `PATH`:

```bash
<blender-python> -m pip install --upgrade "dcc-mcp-blender"
```

If the bundled environment is read-only, the legacy setup helper supports a
user-site install and prints the matching Blender launch command:

```bash
<blender-python> -m pip install --user --upgrade "dcc-mcp-blender"
python skills/dcc-mcp-blender-setup/scripts/setup_dcc_mcp_blender.py --source pypi --user
blender --python-use-system-env
```

## Supported versions

| Adapter | dcc-mcp-core | Blender | Python | Platforms |
|---|---|---|---|---|
| Current `0.2.x` | `>=0.20.0,<1.0.0` | `3.6+` startup hook; `4.2+` Extension ZIP | `3.7+` | Windows, macOS, Linux |

Preflight runs `<blender> --version`, rejects unsupported hosts, and binds the
matching versioned user profile. `--dcc-path` and `--python` always select the
exact host and interpreter recorded in the plan and receipt.

## Agent quick path

Inspect the Core catalog plan first. Its Blender entry already resolves this
repository's raw installation guide:

```bash
dcc-mcp-cli install --dcc-type blender
dcc-mcp-cli install --dcc-type blender --execute --json
```

Then inspect and execute the adapter-owned host-enablement plan:

```bash
dcc-mcp-blender install --dcc-path "<absolute-blender-path>" --python "<absolute-blender-python>" --json --dry-run
dcc-mcp-blender install --dcc-path "<absolute-blender-path>" --python "<absolute-blender-python>" --json --yes
```

The default invocation and `--dry-run` are non-mutating. All lifecycle verbs
accept the uniform flags `--json`, `--yes`, `--dry-run`, `--dcc-path`, and
`--python`. JSON output follows schema version 1 and includes executable
`next_steps`, the selected host/interpreter, plan type, receipt path, and
verification state.

Stable exit codes are:

| Exit | Meaning |
|---:|---|
| `0` | plan or operation completed |
| `10` | host, interpreter, version, receipt, or partial-state preflight failed |
| `20` | package acquisition or integrity failed |
| `30` | staging, commit, uninstall, or rollback failed |
| `40` | files are installed but verify-to-usable failed |
| `50` | a real loaded/locked artifact requires a Blender restart |

## Manual path

1. Locate the exact Blender application and its matching bundled Python.
2. Install `dcc-mcp-blender` and `dcc-mcp-core` into that interpreter.
3. Run `dcc-mcp-blender install ... --json --dry-run` and review every path.
4. Execute the same command with `--yes`.
5. Launch Blender only when the returned `next_steps` asks for it.
6. Run `dcc-mcp-blender verify ... --json`.

The lifecycle writes one adapter-owned
`scripts/startup/dcc_mcp_blender_startup.py` and a versioned receipt. It builds
the complete startup hook in staging, moves the previous receipted state to a
backup, atomically commits the new file and receipt, and performs rollback if a
commit fails. Unknown unreceipted startup files are preserved and fail closed.
Re-running the same desired version converges without duplicating hooks.

The release Extension ZIP is an alternative distribution for Blender 4.2+.
Because Blender physically owns its Extension enablement UI, install it with
`Edit > Preferences > Extensions > Install from Disk`, then enable **DCC MCP
Blender**. Do not combine the ZIP and startup-hook paths, and do not automate
that UI through a generic input fallback.

## Verify

Read the installed state without mutation:

```bash
dcc-mcp-blender status --dcc-path "<absolute-blender-path>" --python "<absolute-blender-python>" --json
```

Verify to usable:

```bash
dcc-mcp-blender verify --dcc-path "<absolute-blender-path>" --python "<absolute-blender-python>" --json
```

Verification checks the receipt binding, startup-file digest, exact target
interpreter imports and versions, captured bootstrap failures, one live Blender
registry row, and the typed `host.ping` probe. Only all-green evidence produces
`"directly_usable": true`. A closed Blender instance returns exit `40` and an
exact launch/verify command; it is never reported as ready or as requiring a
restart.

The installed hook wraps the complete import/start operation with Core
`capture_bootstrap_errors` and re-raises the original exception so Blender's
console remains fail-visible.

## Upgrade

Upgrade the distribution in the same Blender interpreter, inspect the host
plan, then execute it:

```bash
<blender-python> -m pip install --upgrade "dcc-mcp-blender"
dcc-mcp-blender upgrade --dcc-path "<absolute-blender-path>" --python "<absolute-blender-python>" --json --dry-run
dcc-mcp-blender upgrade --dcc-path "<absolute-blender-path>" --python "<absolute-blender-python>" --json --yes
```

`upgrade` requires an existing valid receipt and reuses the staged replacement
transaction. A commit failure restores the previous startup hook and receipt.

## Uninstall

Review and execute receipt-only host cleanup:

```bash
dcc-mcp-blender uninstall --dcc-path "<absolute-blender-path>" --python "<absolute-blender-python>" --json --dry-run
dcc-mcp-blender uninstall --dcc-path "<absolute-blender-path>" --python "<absolute-blender-python>" --json --yes
```

Only the file named and hashed in the receipt is removed. Modified or unknown
files are preserved, and a second uninstall is an idempotent success. After
host cleanup, remove the Python distribution explicitly if desired:

```bash
<blender-python> -m pip uninstall dcc-mcp-blender
```

For the Extension ZIP path, remove **DCC MCP Blender** through Blender's
Extensions preferences. The startup-hook lifecycle never deletes extension or
scene data it does not own.

## Troubleshooting

| Result | Diagnosis | Action |
|---|---|---|
| Exit `10`, `dcc_path_required` | Blender was not selected safely | Pass the exact executable or `.app` with `--dcc-path`. |
| Exit `10`, `unsupported_blender_version` | Host is older than Blender 3.6 | Install a supported Blender version. |
| Exit `10`, `python_mismatch` | Interpreter differs from the receipt | Use the exact receipted Blender Python or uninstall from the original target first. |
| Exit `10`, `unreceipted_startup_script` | Ownership cannot be proven | Inspect the reported file; do not delete or overwrite user content. |
| Exit `20` | Package acquisition/integrity failed | Reinstall only from the official pinned catalog or PyPI package. |
| Exit `30` | Transaction or rollback failed | Preserve the JSON result and previous receipt; resolve the reported filesystem failure. |
| Exit `40`, `target_import_failed` | Adapter/Core is absent from target Python | Install both packages into the exact `--python` interpreter. |
| Exit `40`, `bootstrap_error_captured` | Blender startup raised before MCP readiness | Inspect the receipt's `bootstrap_error_dir` and Blender console; fix the original error. |
| Exit `40`, `no_live_blender_instance` | Installed but Blender is closed or not registered | Execute the returned launch command, wait for startup, then rerun verify. |
| Exit `50` | Windows reports a loaded/locked adapter artifact | Save work, close only the reported Blender instance, then repeat the command. |

The catalog `instructions_url` is:

```text
https://raw.githubusercontent.com/dcc-mcp/dcc-mcp-blender/main/install.md
```
