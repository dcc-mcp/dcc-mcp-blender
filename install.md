# Install dcc-mcp-blender

This runbook installs, verifies, upgrades, and removes the Blender adapter under
[DCC-MCP Adapter Install SOP v1](https://dcc-mcp.github.io/dcc-mcp-core/guide/adapter-install-sop).
The standard lifecycle host-enables a package that is already installed in the
selected Blender interpreter. It never controls Blender's UI.

## Requirements

- **Blender:** 3.6 or newer for the Python/startup-hook path. The Blender
  Extensions ZIP requires Blender 4.2 or newer.
- **Python:** Blender's selected bundled interpreter, Python 3.7 or newer.
- **dcc-mcp-core:** `>=0.20.0,<0.21.0` in that exact interpreter.
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
| Current `0.2.x` | `>=0.20.0,<0.21.0` | `3.6+` startup hook; `4.2+` Extension ZIP | `3.7+` | Windows, macOS, Linux |

The adapter declares no upper Python bound: it runs on Python 3.13 (Blender
5.x) as long as its dependencies are visible to the interpreter. Newer
interpreters are reported as beyond the tested maximum, not rejected.

## Host support boundary

Blender 5.x starts its bundled interpreter in isolated mode, so `PYTHONPATH` and
user-site entries never reach `sys.path` and `import dcc_mcp_blender` fails with
`ModuleNotFoundError`. Run the preflight in the target interpreter to get the
declared boundary, the detected mode, and the matching fix instead:

```bash
blender --background --python <site-packages>/dcc_mcp_blender/_host_support.py -- --json
```

Run it **inside the host** (`blender --python`), not with a bare interpreter: only
the host interpreter reproduces the isolation flags that hide `PYTHONPATH`, so a
bare `<blender-python>` run reports `isolated=0` and can print `supported` for a
host that cannot import the adapter. Script arguments go after `--`; Blender's own
arguments are ignored. The standalone run always checks both `dcc_mcp_blender` and
`dcc_mcp_core`; `--require MODULE` adds to that set, it never replaces it.

It imports no adapter modules, exits `0` when the host is supported and `1` when
it is not, and names the missing distributions plus the fix that matches the
detected mode: `--python-use-system-env` for an isolated interpreter, or the
Extension ZIP that bundles the `dcc-mcp-core` wheel. Hosts that reach the
adapter itself raise the same `HostSupportError` at import time.

Preflight runs `<blender> --version`, rejects unsupported hosts, and binds the
matching versioned user profile. `--dcc-path` and `--python` always select the
exact host and interpreter recorded in the plan and receipt.
The lifecycle never assumes its own CLI interpreter belongs to Blender:
`--python` is required unless `DCC_MCP_INSTALL_PYTHON` explicitly selects the
target, and JSON reports which of those two sources was used.

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

## Stale user-level copies shadow the installed package

Blender loads user-level extension copies (`bl_ext.<repository>.dcc_mcp_blender`)
**before** any package environment or startup hook runs. A copy left behind by an
earlier install therefore keeps answering `import dcc_mcp_blender` even when a
package manager resolved a different copy for that session. That stale copy
satisfies its own, older compatibility gate, starts an MCP server, and reports an
old version **without raising anything** — every capability captured from that host
then silently describes the wrong runtime.

The lifecycle defends against this in two places:

1. The generated startup hook compares the origin of `dcc_mcp_blender` and
   `dcc_mcp_core` against the expected package root, and fails closed when the
   adapter came from somewhere else.
2. The add-on entry runs the same check plus the `min_core_version` gate in
   `register()`, before any operator class is registered, and it hands the runtime
   over to a resolved distribution that is at least as new as the bundled copy.

Declare the authoritative package root for a session to make the check strict:

```bash
# one root, or several separated by the platform path separator
export DCC_MCP_BLENDER_PACKAGE_ROOT="/studio/resolve/site-packages"
```

A declared root replaces the site-packages directory the startup hook was
installed with, so a package manager that resolves the runtime per session (rez,
for example) is never judged against a stale install-time directory. Write it as
the directory that **holds** the package — the `sys.path` entry, such as
`/studio/resolve/site-packages` — or as the package directory itself
(`/studio/resolve/site-packages/dcc_mcp_blender`); both are accepted.

Set `DCC_MCP_BLENDER_STRICT_ORIGIN=0` to downgrade a violation from an error to a
warning on a machine you cannot clean yet. Never leave it set in a farm
environment: it is the switch that turns a visible failure back into a silent one.

To find and remove a stale copy:

```bash
dcc-mcp-blender status --dcc-path "<absolute-blender-path>" --python "<absolute-blender-python>" --json
```

Inside the host, compare what the interpreter really imported:

```python
import dcc_mcp_blender, dcc_mcp_core
print(dcc_mcp_blender.__version__, dcc_mcp_blender.__file__)
print(dcc_mcp_core.__version__, dcc_mcp_core.__file__)
```

Both paths must sit inside the directory the resolve supplied. If either points at
a Blender user extension or add-ons directory, remove that copy (Blender
`Edit > Preferences > Extensions`, or delete the matching
`bl_ext.<repository>.dcc_mcp_blender` directory) and restart Blender.

## Troubleshooting

| Result | Diagnosis | Action |
|---|---|---|
| Exit `10`, `dcc_path_required` | Blender was not selected safely | Pass the exact executable or `.app` with `--dcc-path`. |
| Exit `10`, `python_required` | Blender's target interpreter was not selected | Pass its exact interpreter with `--python` or `DCC_MCP_INSTALL_PYTHON`. |
| Exit `10`, `unsupported_blender_version` | Host is older than Blender 3.6 | Install a supported Blender version. |
| Exit `10`, `python_mismatch` | Interpreter differs from the receipt | Use the exact receipted Blender Python or uninstall from the original target first. |
| Exit `10`, `unreceipted_startup_script` | Ownership cannot be proven | Inspect the reported file; do not delete or overwrite user content. |
| Exit `20` | Package acquisition/integrity failed | Reinstall only from the official pinned catalog or PyPI package. |
| Exit `30` | Transaction or rollback failed | Preserve the JSON result and previous receipt; resolve the reported filesystem failure. |
| Exit `40`, `target_import_failed` | Adapter/Core is absent from target Python | Install both packages into the exact `--python` interpreter. |
| Exit `40`, `bootstrap_error_captured` | Blender startup raised before MCP readiness | Inspect the receipt's `bootstrap_error_dir` and Blender console; fix the original error. |
| Startup error, `resolved outside <site-packages>` | A stale user-level copy shadowed the installed package | Remove that copy (see [Stale user-level copies](#stale-user-level-copies-shadow-the-installed-package)) and restart Blender. |
| Exit `40`, `no_live_blender_instance` | Installed but Blender is closed or not registered | Execute the returned launch command, wait for startup, then rerun verify. |
| Exit `50` | Windows reports a loaded/locked adapter artifact | Save work, close only the reported Blender instance, then repeat the command. |

The catalog `instructions_url` is:

```text
https://raw.githubusercontent.com/dcc-mcp/dcc-mcp-blender/main/install.md
```
