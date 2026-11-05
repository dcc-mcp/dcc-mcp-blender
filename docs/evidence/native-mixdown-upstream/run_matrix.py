"""Plain-CPython orchestrator for reproduce_native_mixdown.py.

Runs one Blender background subprocess per case. A native SIGABRT inside
FFMPEGWriter kills only that child; the harness survives and records the
abnormal termination. This is harness plumbing for observation only -- it is
NOT a fix, not isolation, and not an audio-quality claim.

Usage:
    python run_matrix.py --blender <blender.exe> --script <repro.py> \
        --out-dir <dir> [--cases cases.json]

Writes <out-dir>/native-mixdown-results.json (machine-readable) and
<out-dir>/native-mixdown-results.md (compact table).
"""

import argparse
import json
import os
import subprocess
import sys

MARKER_START = "RESULT_JSON_START"
MARKER_END = "RESULT_JSON_END"


def default_cases():
    base = dict(channels="STEREO", mixrate=48000, fps=24, container="WAV", codec="PCM")
    cases = []

    def add(name, **kw):
        c = dict(base)
        c.update(kw)
        c["name"] = name
        cases.append(c)

    # --- surplus confirmation across frame ranges / bit depths / accuracy ---
    add("surplus_s24_100f_a480", frames="1-100", accuracy=480, format="S24")
    add("surplus_s24_1f_a480", frames="1-1", accuracy=480, format="S24")
    add("surplus_s16_100f_a480", frames="1-100", accuracy=480, format="S16")
    add("surplus_s24_100f_a1024", frames="1-100", accuracy=1024, format="S24")
    add("surplus_s24_1f_a4096_gt_requested", frames="1-1", accuracy=4096, format="S24")
    add("surplus_s24_1f_a2000_eq_requested", frames="1-1", accuracy=2000, format="S24")

    # --- S24 accuracy sweep at frames 1-1 (crash boundary) ---
    for acc in (1, 64, 240, 480, 1024, 2000):
        add("s24_1f_a%d" % acc, frames="1-1", accuracy=acc, format="S24")

    # --- format sweep at the documented bad accuracy ---
    for fmt in ("U8", "S16", "S24", "S32", "F32", "F64"):
        add("fmt_%s_1f_a240" % fmt, frames="1-1", accuracy=240, format=fmt)

    # --- compressed-codec control: FFMPEGWriter uses frame_size branch,
    #     which resets m_input_samples and should NOT double-encode ---
    add(
        "control_flac_100f_a480",
        frames="1-100",
        accuracy=480,
        format="S16",
        container="FLAC",
        codec="FLAC",
    )
    return cases


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blender", required=True)
    ap.add_argument("--script", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--cases")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    cases = json.load(open(args.cases, "r", encoding="utf-8")) if args.cases else default_cases()

    results = []
    for i, c in enumerate(cases, 1):
        name = c["name"]
        out_path = os.path.join(args.out_dir, name + "." + ("flac" if c["codec"] == "FLAC" else "wav"))
        cmd = [
            args.blender, "--background", "--factory-startup",
            "--python", os.path.abspath(args.script), "--",
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
        rec = {"name": name, "params": c,
               "requested_samples": int(
                   (int(c["frames"].split("-")[1]) - int(c["frames"].split("-")[0]) + 1)
                   * c["mixrate"] / c["fps"])}
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            rec["returncode"] = p.returncode
            stdout = p.stdout or ""
            stderr = p.stderr or ""
            rec["stderr_tail"] = stderr.strip()[-400:]
            if MARKER_START in stdout:
                block = stdout.split(MARKER_START, 1)[1].split(MARKER_END, 1)[0].strip()
                try:
                    rec["result"] = json.loads(block)
                except json.JSONDecodeError:
                    rec["result"] = None
                    rec["stdout_tail"] = stdout.strip()[-400:]
                rec["abnormal"] = False
            else:
                rec["result"] = None
                rec["abnormal"] = True
                rec["stdout_tail"] = stdout.strip()[-400:]
                rec["crash_class"] = "native_abort_no_result"
        except subprocess.TimeoutExpired:
            rec["returncode"] = None
            rec["result"] = None
            rec["abnormal"] = True
            rec["crash_class"] = "timeout"

        r = rec.get("result") or {}
        rec["verdict"] = r.get("verdict", "CRASH" if rec.get("abnormal") else "UNKNOWN")
        rec["surplus_samples"] = r.get("surplus_samples")
        rec["decoded_samples"] = r.get("decoded_samples", r.get("flac_total_samples"))
        rec["file_bytes"] = r.get("file_bytes")
        rec["duplicate_final_block"] = r.get("surplus_is_exact_duplicate_of_final_block")
        results.append(rec)
        print("[%02d/%02d] %-38s verdict=%-8s surplus=%s exit=%s"
              % (i, len(cases), name, rec["verdict"], rec["surplus_samples"],
                 rec.get("returncode")), flush=True)

    meta = {
        "harness": "run_matrix.py + reproduce_native_mixdown.py",
        "blender": results[0].get("result", {}).get("blender_version")
        if results and results[0].get("result") else None,
        "note": (
            "Empty scene mixes down to silence. One Blender subprocess per case; "
            "abnormal termination is a child-only native abort. Not a fix, "
            "not isolation, not a listening/quality claim."
        ),
        "cases": results,
    }
    with open(os.path.join(args.out_dir, "native-mixdown-results.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, sort_keys=True)

    lines = [
        "| case | frames | accuracy | format | codec | requested | decoded | surplus | dup-final | exit | verdict |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for rec in results:
        c = rec["params"]
        lines.append(
            "| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |"
            % (rec["name"], c["frames"], c["accuracy"], c["format"], c["codec"],
               rec["requested_samples"],
               rec["decoded_samples"] if rec["decoded_samples"] is not None else "-",
               rec["surplus_samples"] if rec["surplus_samples"] is not None else "-",
               rec["duplicate_final_block"] if rec["duplicate_final_block"] is not None else "-",
               rec.get("returncode"), rec["verdict"])
        )
    with open(os.path.join(args.out_dir, "native-mixdown-results.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("WROTE", os.path.join(args.out_dir, "native-mixdown-results.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
