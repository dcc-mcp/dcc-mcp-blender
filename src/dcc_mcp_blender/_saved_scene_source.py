"""Bounded source checks for saved-scene jobs; also run standalone in Blender.

Only standard-library imports: detached workers need neither Core nor an
installed adapter. These observations detect changes, not a race-free snapshot.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import stat
from pathlib import Path

_BLEND_HEADER = re.compile(rb"BLENDER[_-][vV][0-9]{3}")
_ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"


def reject_source_output_alias(source_filepath, output_filepath):
    """Reject ordinary/symlink/hardlink output aliases before writing the source.

    This is a point-in-time check, not a lock against subsequent path changes.
    Resolving here only compares identities; the source load path is unchanged.
    """
    source = Path(source_filepath)
    output = Path(output_filepath)
    if source.resolve() == output.resolve():
        raise ValueError("Render output aliases the saved source: {}".format(output))
    try:
        aliases = os.path.samefile(str(source), str(output))
    except FileNotFoundError:
        aliases = False
    if aliases:
        raise ValueError("Render output aliases the saved source: {}".format(output))


def _check_output_aliases(receipt, source_filepath):
    settings = receipt["launch_settings"]
    pattern = settings["output_pattern"]
    suffix = settings["output_suffix"]
    for frame in range(settings["start_frame"], settings["end_frame"] + 1, settings["step"]):
        value = re.sub(r"#+", lambda match: str(frame).zfill(len(match.group())), pattern)
        path = Path(value)
        output = path if path.suffix.lower() == suffix else Path(value + suffix)
        reject_source_output_alias(source_filepath, output)


def source_fingerprint(filepath):
    """Hash a regular .blend without loading it or relocating relative assets.

    Raw and gzip headers are checked. Zstd container magic is accepted because
    Python bundled with Blender 4.5 has no stdlib zstd decoder; Blender remains
    responsible for validating the full file, including compressed containers.
    """
    path = Path(filepath)
    if not path.is_absolute() or path.suffix.lower() != ".blend":
        raise ValueError("source_filepath must be an absolute .blend filepath")
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("source_filepath must be a regular file")
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("source_filepath must be a regular file")
        header = stream.read(12)
        if header.startswith(b"\x1f\x8b"):
            stream.seek(0)
            with gzip.GzipFile(fileobj=stream) as compressed:
                header = compressed.read(12)
        if not _BLEND_HEADER.fullmatch(header) and not header.startswith(_ZSTD_MAGIC):
            raise ValueError("source_filepath has no supported .blend header")
        stream.seek(0)
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
        after = os.fstat(stream.fileno())
        current = path.stat()
    if any(
        getattr(before, field) != getattr(after, field)
        for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    ) or any(
        getattr(after, field) != getattr(current, field) for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    ):
        raise ValueError("Saved source changed while hashing")
    return {"sha256": digest.hexdigest(), "size_bytes": after.st_size, "mtime_ns": after.st_mtime_ns}


def write_source_receipt(filepath, receipt):
    path = Path(filepath)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(str(temporary), str(path))


def read_source_receipt(filepath, job_id):
    path = Path(filepath)
    if path.is_symlink() or path.stat().st_size > 65536:
        raise ValueError("Invalid saved source receipt")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(receipt, dict) or receipt.get("job_id") != job_id:
        raise ValueError("Saved source receipt job identity mismatch")
    return receipt


def check_source(receipt_path, job_id, source_filepath, expected_sha256, expected_size, phase):
    """Persist a fingerprint just before load, after load, or after rendering.

    A mismatch raises under --python-exit-code before later CLI render actions.
    The source is never written. The receipt is evidence, not a recovery API.
    """
    receipt = read_source_receipt(receipt_path, job_id)
    try:
        observed = source_fingerprint(source_filepath)
        receipt.setdefault("observations", {})[phase] = observed
        if observed["sha256"] != expected_sha256 or observed["size_bytes"] != expected_size:
            raise ValueError("Saved source fingerprint mismatch at {}".format(phase))
        if phase in ("before_load", "after_load"):
            _check_output_aliases(receipt, source_filepath)
        if phase == "after_load":
            import bpy

            # A failed native load must not render the startup/default scene.
            if os.path.abspath(bpy.data.filepath) != os.path.abspath(source_filepath):
                raise ValueError("Worker did not load the requested saved source")
        receipt["phase"] = phase
    except Exception as exc:
        receipt["phase"] = "failed"
        receipt["error"] = str(exc)
        write_source_receipt(receipt_path, receipt)
        raise
    write_source_receipt(receipt_path, receipt)


def source_check_expression(receipt_path, job_id, source_filepath, expected_sha256, expected_size, phase):
    """Literal-only worker arguments; no caller-supplied executable source."""
    return ("import runpy; runpy.run_path({!r})['check_source']({!r}, {!r}, {!r}, {!r}, {!r}, {!r})").format(
        str(Path(__file__).absolute()),
        str(receipt_path),
        job_id,
        source_filepath,
        expected_sha256,
        expected_size,
        phase,
    )
