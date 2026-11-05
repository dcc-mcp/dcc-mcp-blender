"""Plain-CPython orchestrator for reproduce_native_mixdown.py.

Runs one Blender background subprocess per case. A native SIGABRT inside
FFMPEGWriter kills only that child; the harness survives and records the
abnormal termination together with enough evidence (exit status, stdout/stderr
tails, and post-run output-file state) to attribute every verdict. This is
harness plumbing for observation only -- it is NOT a fix, not isolation, and
not an audio-quality claim.

Usage:
    python run_matrix.py --blender <blender.exe> --script <repro.py> \
        --out-dir <dir> [--cases cases.json]

The case list defaults to ``cases.json`` next to this script (the exact 58-case
set behind the committed results.json / results.md); override with --cases.

Writes <out-dir>/results.json (machine-readable) and <out-dir>/results.md
(compact table), in the same schema as the committed evidence files.
"""

import argparse
import json
import os
import subprocess
import sys
from collections import Counter

MARKER_START = "RESULT_JSON_START"
MARKER_END = "RESULT_JSON_END"
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CASES = os.path.join(HERE, "cases.json")
TAIL_CHARS = 400

BOUNDS = (
    "These are measurements, not a fix, not isolation, and not a "
    "listening/quality certification. No subjective/MP3 acceptance is claimed. "
    "The native encoder is not repaired by anything in this directory. A CRASH "
    "verdict records an abnormal termination, not proof of the output file's "
    "size; the per-case file_exists / output_bytes / output_state fields are the "
    "authoritative output-file evidence."
)
FORMULAS = {
    "requested_samples": "(end_frame - start_frame + 1) * rate / fps",
    "surplus_is": "the final FFMPEGWriter::write() chunk, encoded a second time by ~FFMPEGWriter",
    "surplus_samples": "requested % accuracy, or accuracy when requested % accuracy == 0",
}
SOURCE_COMMIT = {
    "files": [
        "extern/audaspace/plugins/ffmpeg/FFMPEGWriter.cpp",
        "source/blender/editors/sound/sound_ops.cc",
    ],
    "label": "Blender 4.5.13 LTS (daeeeca98fb0)",
    "repo": "blender/blender",
    "sha": "daeeeca98fb0b6f0994b374d0069893186197a44",
}
PURPOSE = (
    "Standalone, MCP-free reproduction of native Blender "
    "bpy.ops.sound.mixdown PCM surplus and accuracy-dependent ffmpeg abort."
)
FIELDS = {
    "crash_class": (
        "Neutral classification of a run that produced no usable result: "
        "no_result_exit_0 (likely a script-level exception), "
        "no_result_nonzero_exit (abnormal termination, e.g. a native fast-fail), "
        "bad_result_json (marker printed but JSON unparseable), timeout. "
        "null for runs with a valid result."
    ),
    "exit_signature": "Human-readable decode of returncode (e.g. 0xC0000409 fast-fail).",
    "file_exists": "Whether the output path existed after the child exited (post-run stat, all cases).",
    "file_bytes": "Output size measured by the reproducer; null when it printed no result.",
    "output_bytes": "Authoritative post-run size of the output path in bytes; null when missing (all cases).",
    "output_state": "missing | zero_byte | nonzero, derived from file_exists / output_bytes.",
    "stdout_tail": "Last %d chars of child stdout (every case)." % TAIL_CHARS,
    "stderr_tail": "Last %d chars of child stderr (every case)." % TAIL_CHARS,
}
ATTRIBUTION = (
    "Every case removes any stale output before launching its child and stats "
    "the output path after the child exits, so a leftover file cannot be "
    "attributed to a case and missing / zero-byte / partial outputs are "
    "distinguishable. --python-exit-code 1 makes an uncaught Python exception "
    "surface as a nonzero exit, so it is not silently filed as a native abort; "
    "crash_class stays neutral and exit_signature + stderr_tail + file state "
    "carry the concrete attribution."
)
ABNORMAL_VERDICTS = ("CRASH", "TIMEOUT", "NO_RESULT")


def load_cases(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def exit_signature(rc):
    """Decode a subprocess return code into a human-readable signature."""
    if rc is None:
        return "timeout (killed by harness)"
    if rc == 0:
        return "0 (clean)"
    u = rc & 0xFFFFFFFF
    if 0xC0000000 <= u <= 0xC0000FFF:
        return "0x%08X (Windows native fast-fail / abort)" % u
    if u > 0x7FFFFFFF:
        return "0x%08X (abnormal)" % u
    return "%d (nonzero)" % rc


def output_state(file_exists, output_bytes):
    if not file_exists:
        return "missing"
    return "zero_byte" if output_bytes == 0 else "nonzero"


def _as_text(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value or ""


def run_case(blender, script, c, out_dir):
    """Run one case and return a fully-attributed record."""
    name = c["name"]
    ext = "flac" if c["codec"] == "FLAC" else "wav"
    out_path = os.path.join(out_dir, name + "." + ext)
    cmd = [
        blender, "--background", "--factory-startup",
        "--python-exit-code", "1",
        "--python", os.path.abspath(script), "--",
        "--out", os.path.abspath(out_path),
        "--frames", c["frames"],
        "--accuracy", str(c["accuracy"]),
        "--format", c["format"],
        "--channels", c["channels"],
        "--mixrate", str(c["mixrate"]),
        "--fps", str(c["fps"]),
        "--container", c["container"],
        "--codec", c["codec"],
    ]
    rec = {
        "name": name,
        "params": c,
        "sweep": c.get("sweep", "matrix"),
        "requested_samples": int(
            (int(c["frames"].split("-")[1]) - int(c["frames"].split("-")[0]) + 1)
            * c["mixrate"] / c["fps"]
        ),
    }

    # Remove any stale output so a leftover file can never be attributed to
    # this case. The reproducer also removes it defensively.
    if os.path.exists(out_path):
        os.remove(out_path)

    verdict = "UNKNOWN"
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
            encoding="utf-8", errors="replace",
        )
        stdout = _as_text(p.stdout)
        stderr = _as_text(p.stderr)
        rec["returncode"] = p.returncode
        rec["exit_signature"] = exit_signature(p.returncode)
        rec["stdout_tail"] = stdout.strip()[-TAIL_CHARS:]
        rec["stderr_tail"] = stderr.strip()[-TAIL_CHARS:]
        if MARKER_START in stdout:
            block = stdout.split(MARKER_START, 1)[1].split(MARKER_END, 1)[0].strip()
            try:
                rec["result"] = json.loads(block)
                rec["abnormal"] = False
                rec["crash_class"] = None
                verdict = rec["result"].get("verdict", "UNKNOWN")
            except (json.JSONDecodeError, ValueError):
                rec["result"] = None
                rec["abnormal"] = False
                rec["crash_class"] = "bad_result_json"
                verdict = "NO_RESULT"
        else:
            rec["result"] = None
            rec["abnormal"] = True
            if p.returncode == 0:
                # A marker-less, exit-0 run is most likely an uncaught Python
                # exception in the reproducer, NOT a native encoder abort.
                rec["crash_class"] = "no_result_exit_0"
                verdict = "NO_RESULT"
            else:
                rec["crash_class"] = "no_result_nonzero_exit"
                verdict = "CRASH"
    except subprocess.TimeoutExpired as exc:
        rec["returncode"] = None
        rec["exit_signature"] = exit_signature(None)
        rec["stdout_tail"] = _as_text(exc.stdout).strip()[-TAIL_CHARS:]
        rec["stderr_tail"] = _as_text(exc.stderr).strip()[-TAIL_CHARS:]
        rec["result"] = None
        rec["abnormal"] = True
        rec["crash_class"] = "timeout"
        verdict = "TIMEOUT"

    # Authoritative post-run output-file state, recorded for every case
    # (including crashes and timeouts).
    if os.path.exists(out_path):
        rec["file_exists"] = True
        rec["output_bytes"] = os.path.getsize(out_path)
    else:
        rec["file_exists"] = False
        rec["output_bytes"] = None
    rec["output_state"] = output_state(rec["file_exists"], rec["output_bytes"])

    r = rec.get("result") or {}
    rec["verdict"] = verdict
    rec["surplus_samples"] = r.get("surplus_samples")
    rec["decoded_samples"] = r.get("decoded_samples", r.get("flac_total_samples"))
    rec["duplicate_final_block"] = r.get("surplus_is_exact_duplicate_of_final_block")
    rec["file_bytes"] = r.get("file_bytes")
    rec["wav_fmt"] = r.get("wav_fmt")
    rec["blender_version"] = r.get("blender_version")
    rec["blender_build_hash"] = r.get("blender_build_hash")
    rec["operator_return"] = r.get("operator_return")
    return rec


def write_results(meta, results, out_dir):
    """Write results.json and results.md in the committed evidence schema."""
    with open(os.path.join(out_dir, "results.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, sort_keys=True)

    vcounts = Counter(r["verdict"] for r in results)
    abnormal_states = Counter(
        r["output_state"] for r in results if r["verdict"] in ABNORMAL_VERDICTS
    )
    other = ", ".join(
        "%s=%d" % kv for kv in sorted(vcounts.items())
        if kv[0] not in ("SURPLUS", "EXACT", "CRASH")
    ) or "none"
    crash_states = ", ".join(
        "%s=%d" % kv for kv in sorted(abnormal_states.items())
    ) or "none"
    lines = [
        "# Native mixdown measurements",
        "",
        "Regenerated by `run_matrix.py` from `cases.json` on Blender %s (`%s`), "
        "Windows 11 x64, empty scene, 48 kHz stereo, fps 24."
        % (meta["blender_under_test"]["version"] or "?", meta["blender_under_test"]["build_hash"] or "?"),
        "",
        "Cases: **%d** total — %d SURPLUS (exact duplicate of the final block), "
        "%d EXACT (compressed-codec controls), %d CRASH (abnormal native "
        "termination), other: %s."
        % (len(results), vcounts.get("SURPLUS", 0), vcounts.get("EXACT", 0),
           vcounts.get("CRASH", 0), other),
        "",
        "Requested samples = `(end_frame - start_frame + 1) * rate / fps`. "
        "Surplus = `requested % accuracy`, or `accuracy` when the remainder is zero.",
        "",
        "For abnormal-termination cases the `out` / `out_bytes` columns record the "
        "**post-run output-file state**, so missing, 0-byte and partial files are "
        "distinguishable (CRASH/TIMEOUT/NO_RESULT states: %s). `crash_class` is a "
        "neutral exit-status classification; full `exit_signature`, `stdout_tail`, "
        "`stderr_tail` and `output_state` are in `results.json`." % crash_states,
        "",
        "| case | sweep | frames | accuracy | format | codec | requested | decoded | surplus | dup-final | out | out_bytes | exit | crash_class | verdict |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for rec in results:
        c = rec["params"]
        if not rec["file_exists"]:
            out_cell = "missing"
        elif rec["output_bytes"] == 0:
            out_cell = "0B"
        else:
            out_cell = "%dB" % rec["output_bytes"]
        lines.append(
            "| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |"
            % (
                rec["name"], rec["sweep"], c["frames"], c["accuracy"], c["format"],
                c["codec"], rec["requested_samples"],
                rec["decoded_samples"] if rec["decoded_samples"] is not None else "-",
                rec["surplus_samples"] if rec["surplus_samples"] is not None else "-",
                rec["duplicate_final_block"] if rec["duplicate_final_block"] is not None else "-",
                out_cell,
                rec["output_bytes"] if rec["output_bytes"] is not None else "-",
                rec.get("returncode") if rec.get("returncode") is not None else "-",
                rec.get("crash_class") or "-",
                rec["verdict"],
            )
        )
    with open(os.path.join(out_dir, "results.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blender", required=True)
    ap.add_argument("--script", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--cases", default=DEFAULT_CASES)
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    cases = load_cases(args.cases)

    results = []
    for i, c in enumerate(cases, 1):
        rec = run_case(args.blender, args.script, c, args.out_dir)
        results.append(rec)
        print(
            "[%02d/%02d] %-38s verdict=%-9s out=%-9s exit=%s"
            % (i, len(cases), rec["name"], rec["verdict"], rec["output_state"],
               rec.get("returncode")),
            flush=True,
        )

    first = next((r.get("result") or {} for r in results if r.get("result")), {})
    meta = {
        "attribution": ATTRIBUTION,
        "blender_under_test": {
            "build_hash": first.get("blender_build_hash"),
            "note": (
                "4.5.13 LTS (daeeeca98fb0) is the version reported in the "
                "originating issue; 5.1.1 was the locally available build and "
                "is used to show the defects are still present in a later major "
                "release. Source analysis below is pinned to the exact 4.5.13 commit."
            ),
            "platform": "Windows 11 x64",
            "version": first.get("blender_version"),
        },
        "bounds": BOUNDS,
        "fields": FIELDS,
        "formulas": FORMULAS,
        "harness": {
            "cases_file": os.path.basename(args.cases),
            "case_count": len(cases),
            "decoder": "dependency-free RIFF/WAVE chunk walker (no numpy / no external decoder)",
            "method": "one Blender background subprocess per case; empty scene mixes down to silence",
            "orchestrator": "run_matrix.py",
            "python_exit_code_flag": "--python-exit-code 1",
            "reproducer": "reproduce_native_mixdown.py",
        },
        "purpose": PURPOSE,
        "schema_version": 2,
        "source_commit": SOURCE_COMMIT,
        "cases": results,
    }
    write_results(meta, results, args.out_dir)
    print("WROTE", os.path.join(args.out_dir, "results.json"))
    print("WROTE", os.path.join(args.out_dir, "results.md"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
