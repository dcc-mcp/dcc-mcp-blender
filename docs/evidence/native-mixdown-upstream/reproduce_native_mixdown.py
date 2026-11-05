"""Standalone reproducer for Blender's native ``bpy.ops.sound.mixdown`` PCM
surplus and accuracy-dependent ffmpeg crash.

This script has NO dependency on MCP, dcc-mcp-blender, add-ons or external
sound files. An empty scene mixes down to digital silence of the requested
inclusive frame length; both defects live in the native PCM encoder, not in
any source material.

Run (one case per invocation, so a hard crash is directly observable):

    blender --background --factory-startup --python reproduce_native_mixdown.py -- \
        --out out.wav --frames 1-100 --accuracy 480 --format S24 \
        --channels STEREO --mixrate 48000 --fps 24 --container WAV --codec PCM

The script prints exactly one JSON object between RESULT_JSON_START / _END
markers. A SIGABRT inside the encoder kills Blender before the marker is
printed; the companion ``run_matrix.py`` records that as the crash case.

Verdicts: SURPLUS (decoded > requested), EXACT (decoded == requested),
SHORT (decoded < requested), NO_OUTPUT (no file produced). A SHORT or
NO_OUTPUT result is never reported as an EXACT control.
"""

import argparse
import json
import os
import struct
import sys

import bpy


def parse_args(argv):
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    p.add_argument("--frames", required=True, help="inclusive frame range, e.g. 1-100")
    p.add_argument("--accuracy", type=int, required=True)
    p.add_argument("--format", default="S24")
    p.add_argument("--channels", default="STEREO")
    p.add_argument("--mixrate", type=int, default=48000)
    p.add_argument("--fps", type=float, default=24.0)
    p.add_argument("--container", default="WAV")
    p.add_argument("--codec", default="PCM")
    return p.parse_args(argv)


def riff_pcm_info(path):
    """Dependency-free WAV/PCM inspection. Returns decoded sample count and the
    raw PCM payload, or None when the file is not a plain RIFF/WAVE PCM file."""
    with open(path, "rb") as f:
        buf = f.read()
    if len(buf) < 12 or buf[0:4] != b"RIFF" or buf[8:12] != b"WAVE":
        return None
    fmt = None
    data = None
    pos = 12
    while pos + 8 <= len(buf):
        cid = buf[pos : pos + 4]
        size = struct.unpack_from("<I", buf, pos + 4)[0]
        body = pos + 8
        if cid == b"fmt " and size >= 16:
            fmt = {
                "audio_format": struct.unpack_from("<H", buf, body)[0],
                "channels": struct.unpack_from("<H", buf, body + 2)[0],
                "rate": struct.unpack_from("<I", buf, body + 4)[0],
                "byte_rate": struct.unpack_from("<I", buf, body + 8)[0],
                "block_align": struct.unpack_from("<H", buf, body + 12)[0],
                "bits": struct.unpack_from("<H", buf, body + 14)[0],
            }
        elif cid == b"data":
            data = buf[body : body + size]
        pos = body + size + (size & 1)
        if cid == b"data":
            break
    if fmt is None or data is None or not fmt["block_align"]:
        return None
    return {
        "fmt": fmt,
        "nframes": len(data) // fmt["block_align"],
        "data": data,
        "file_bytes": len(buf),
    }


def flac_total_samples(path):
    """Read total sample count from a FLAC STREAMINFO block (compressed-codec
    control case, where FFMPEGWriter uses the buffered/frame_size branch)."""
    with open(path, "rb") as f:
        buf = f.read()
    if buf[:4] != b"fLaC":
        return None
    pos = 4
    while pos + 4 <= len(buf):
        header = buf[pos]
        block_type = header & 0x7F
        length = int.from_bytes(buf[pos + 1 : pos + 4], "big")
        body = pos + 4
        if block_type == 0 and length >= 18:  # STREAMINFO
            packed = int.from_bytes(buf[body + 10 : body + 18], "big")
            return packed & 0xFFFFFFFFF  # low 36 bits = total samples
        pos = body + length
        if header & 0x80:
            break
    return None


def main(argv):
    args = parse_args(argv)
    start_s, end_s = args.frames.split("-", 1)
    start_frame, end_frame = int(start_s), int(end_s)

    fps_int = int(args.fps)
    if args.fps <= 0 or fps_int <= 0:
        raise SystemExit("error: --fps must be >= 1 (got %r)" % (args.fps,))

    scene = bpy.context.scene
    scene.frame_start = start_frame
    scene.frame_end = end_frame
    # Blender's effective frame rate is fps / fps_base. Set fps_base so the
    # effective rate equals --fps exactly, including fractional rates (e.g.
    # 23.976): fps_int / (fps_int / fps) == fps. The original
    # fps / int(fps) form made the effective rate int(fps)**2 / fps, which
    # would mismatch the requested duration for non-integer frame rates.
    scene.render.fps = fps_int
    scene.render.fps_base = fps_int / args.fps

    # Mirrors sound_mixdown_exec: (end_frame - start_frame + 1) * rate / fps.
    requested = int((end_frame - start_frame + 1) * args.mixrate / args.fps)

    out = os.path.abspath(args.out)
    if os.path.exists(out):
        os.remove(out)

    result = {
        "blender_version": bpy.app.version_string,
        "blender_build_hash": (
            bpy.app.build_hash.decode(errors="replace") if bpy.app.build_hash else ""
        ),
        "params": {
            "frames": args.frames,
            "accuracy": args.accuracy,
            "format": args.format,
            "channels": args.channels,
            "mixrate": args.mixrate,
            "fps": args.fps,
            "container": args.container,
            "codec": args.codec,
        },
        "requested_samples": requested,
        "out": out,
    }

    try:
        op = bpy.ops.sound.mixdown(
            filepath=out,
            accuracy=args.accuracy,
            container=args.container,
            codec=args.codec,
            format=args.format,
            channels=args.channels,
            mixrate=args.mixrate,
            check_existing=False,
        )
        result["operator_return"] = str(op)
    except Exception as exc:  # noqa: BLE001 - report native operator failure verbatim
        result["operator_return"] = "EXCEPTION"
        result["operator_exception"] = "%s: %s" % (type(exc).__name__, exc)

    if os.path.exists(out):
        result["file_exists"] = True
        result["file_bytes"] = os.path.getsize(out)
        if args.codec == "PCM":
            info = riff_pcm_info(out)
            if info is None:
                result["decoder"] = "unparseable WAV"
            else:
                nframes = info["nframes"]
                result["wav_fmt"] = info["fmt"]
                result["decoded_samples"] = nframes
                extra = nframes - requested
                result["surplus_samples"] = extra
                if extra > 0:
                    fa = info["fmt"]["block_align"]
                    payload = info["data"]
                    tail = payload[-2 * extra * fa :]
                    if len(tail) == 2 * extra * fa:
                        prev_block = tail[: extra * fa]
                        last_block = tail[extra * fa :]
                        result["surplus_is_exact_duplicate_of_final_block"] = (
                            prev_block == last_block
                        )
                result["verdict"] = (
                    "SURPLUS" if extra > 0 else ("SHORT" if extra < 0 else "EXACT")
                )
        else:
            total = flac_total_samples(out)
            result["flac_total_samples"] = total
            if total is not None:
                result["surplus_samples"] = total - requested
                result["verdict"] = (
                    "SURPLUS" if total > requested else ("SHORT" if total < requested else "EXACT")
                )
    else:
        result["file_exists"] = False
        result["verdict"] = "NO_OUTPUT"

    print("RESULT_JSON_START")
    print(json.dumps(result, indent=2, sort_keys=True))
    print("RESULT_JSON_END")


if __name__ == "__main__":
    dash = sys.argv.index("--") if "--" in sys.argv else len(sys.argv)
    main(sys.argv[dash + 1 :])
