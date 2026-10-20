"""Blender-only audio worker; never imports the adapter or starts an MCP server."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path


def digest(path):
    checksum = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def _load_pcm_repair():
    # Blender's isolated script runner can omit the package root and PYTHONPATH.
    # Load only this installed worker's fixed sibling, never cwd/user search paths.
    helper = Path(__file__).resolve().with_name("_audio_pcm_repair.py")
    spec = importlib.util.spec_from_file_location("_dcc_owned_audio_pcm_repair", helper)
    if spec is None or spec.loader is None:
        raise RuntimeError("Installed PCM correction helper is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.remove_verified_duplicate_final_block


def _sound_dependencies(bpy):
    actual = {}
    for sound in bpy.data.sounds:
        if sound.library is not None:
            raise ValueError("Linked sound libraries are not supported by the saved snapshot contract")
        if sound.packed_file is not None:
            continue  # Packed bytes are already bound by the saved blend hash.
        path = str(Path(bpy.path.abspath(sound.filepath, library=sound.library)).resolve())
        actual[path] = digest(path)
    return [{"path": path, "sha256": actual[path]} for path in sorted(actual)]


def run(directory):
    import aud
    import bpy
    import numpy as np

    directory = Path(directory).resolve()
    request = json.loads((directory / "request.json").read_text(encoding="utf-8"))
    source = Path(request["scene_path"])
    if digest(source) != request["scene_sha256"]:
        raise ValueError("Saved scene changed after submission")
    # Keep original .blend-relative dependency semantics. No save or live editor mutation.
    opened = bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=False, use_scripts=False)
    if opened != {"FINISHED"} or Path(bpy.data.filepath).resolve() != source.resolve():
        raise RuntimeError("Worker failed to open the exact saved source scene")
    scene = bpy.context.scene
    if not bpy.data.sounds:
        raise ValueError("Saved snapshot contains no sound sources")
    dependencies = _sound_dependencies(bpy)
    if dependencies != request["dependencies"]:
        raise ValueError("Saved snapshot external sounds do not exactly match declared input_files")
    fps = scene.render.fps / scene.render.fps_base
    duration = (request["end_frame"] - request["start_frame"] + 1) / fps
    if not math.isfinite(duration) or not 0 < duration <= 60:
        raise ValueError("Saved snapshot export duration must be in (0, 60] seconds")
    scene.frame_start = request["start_frame"]
    scene.frame_end = request["end_frame"]
    destination = directory / "audio.wav"
    if destination.exists():
        raise FileExistsError("Refusing to overwrite an audio output")
    result = bpy.ops.sound.mixdown(
        filepath=str(destination),
        container="WAV",
        codec="PCM",
        format=request["sample_format"],
        mixrate=request["sample_rate"],
        channels="STEREO",
        split_channels=False,
        accuracy=request["accuracy"],
    )
    if result != {"FINISHED"}:
        raise RuntimeError("Native mixdown did not finish")
    sound = aud.Sound(str(destination))
    samples = sound.data()
    if sound.specs != (request["sample_rate"], 2):
        raise ValueError("Decoded audio rate or channel count mismatch")
    if samples.ndim != 2 or samples.shape[1] != 2 or not np.isfinite(samples).all():
        raise ValueError("Decoded audio contains invalid samples")
    native_hash = digest(destination)
    correction = None
    # Do not hide padding or lost content by truncating/retiming output.
    fps = scene.render.fps / scene.render.fps_base
    target = (request["end_frame"] - request["start_frame"] + 1) * request["sample_rate"] / fps
    if not math.isclose(target, round(target), rel_tol=0, abs_tol=1e-6):
        raise ValueError("Requested interval is not an integral sample count")
    if len(samples) != round(target):
        if request.get("correct_duplicate_final_pcm_block") is not True:
            raise ValueError(f"Decoded sample count {len(samples)} differs from expected {round(target)}")
        remove_verified_duplicate_final_block = _load_pcm_repair()

        corrected_bytes, correction = remove_verified_duplicate_final_block(
            destination.read_bytes(), round(target), request["accuracy"]
        )
        corrected = directory / "audio-corrected.wav"
        with corrected.open("xb") as stream:
            stream.write(corrected_bytes)
        verified = aud.Sound(str(corrected))
        corrected_samples = verified.data()
        if verified.specs != sound.specs or len(corrected_samples) != round(target):
            raise ValueError("Corrected native decode format or length mismatch")
        if not np.array_equal(corrected_samples, samples[: round(target)]):
            raise ValueError("Correction changed decoded prefix samples")
        if digest(destination) != native_hash:
            raise ValueError("Preserved original native output changed during correction")
        destination = corrected
        samples = corrected_samples
    if digest(source) != request["scene_sha256"]:
        raise ValueError("Saved source scene changed during export")
    for dependency in dependencies:
        if "path" in dependency and digest(dependency["path"]) != dependency["sha256"]:
            raise ValueError("Source audio changed during export")
    receipt = {
        "job_id": request["job_id"],
        "status": "completed",
        "scene_sha256": request["scene_sha256"],
        "request_sha256": digest(directory / "request.json"),
        "output_sha256": digest(destination),
        "output_name": destination.name,
        "native_output_sha256": native_hash,
        "correction": correction,
        "frames": len(samples),
        "sample_rate": request["sample_rate"],
        "channels": 2,
        "peak": float(np.abs(samples).max()) if len(samples) else 0.0,
        "full_decode": True,
        "content_fidelity": "not established; independent reference/listening acceptance required",
    }
    temporary = directory / "result.tmp"
    temporary.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    temporary.replace(directory / "result.json")


if __name__ == "__main__":
    run(sys.argv[sys.argv.index("--") + 1])
