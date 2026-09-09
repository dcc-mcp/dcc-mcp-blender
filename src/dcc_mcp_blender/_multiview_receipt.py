"""Durable receipts shared by the isolated multiview worker and job queries."""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

TERMINAL = {"completed", "failed", "cancelled"}


def write_receipt(directory, receipt):
    path = Path(directory) / "result.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(receipt), encoding="utf-8")
    temporary.replace(path)


def read_receipt(directory, job_id):
    if not Path(directory).is_absolute():
        raise ValueError("job_directory must be absolute")
    path = Path(directory) / "result.json"
    if path.stat().st_size > 1_000_000:
        raise ValueError("Render receipt exceeds the size limit")
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict) or result.get("job_id") != job_id or result.get("kind") != "multiview":
        raise ValueError("Render receipt does not match this multiview job")
    items = result.get("items")
    if (
        not isinstance(result.get("status"), str)
        or result["status"] not in TERMINAL | {"running"}
        or not isinstance(items, list)
        or not 1 <= len(items) <= 16
    ):
        raise ValueError("Invalid multiview receipt state")
    for item in items:
        if (
            not isinstance(item, dict)
            or item.get("pass") not in ("beauty", "wire")
            or not isinstance(item.get("status"), str)
            or item.get("status") not in TERMINAL | {"pending", "running"}
        ):
            raise ValueError("Invalid multiview item")
    if result["status"] == "completed" and any(item["status"] != "completed" for item in items):
        raise ValueError("Completed receipt contains unfinished images")
    return result


def png_evidence(path):
    """Hash the complete PNG; the worker separately verifies host decoding."""
    path = Path(path)
    if path.stat().st_size > 100_000_000:
        raise ValueError("PNG output exceeds the bounded image size")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        header = stream.read(24)
        if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
            raise ValueError("Output is not a PNG image")
        width, height = struct.unpack(">II", header[16:24])
        digest.update(header)
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {"sha256": digest.hexdigest(), "width": width, "height": height, "size_bytes": path.stat().st_size}


def multiview_context(job):
    directory = Path(job["job_directory"])
    result = read_receipt(directory, job["job_id"])
    process = job.get("process")
    return_code = process.poll() if process is not None else None
    if result["status"] not in TERMINAL:
        if process is None:
            result["last_recorded_status"] = result["status"]
            result["status"] = "unknown"
        elif return_code is not None:
            result["status"] = "failed"
            result["error"] = "Worker exited before a terminal receipt (code {})".format(return_code)
            for item in result["items"]:
                if item["status"] not in TERMINAL:
                    item["status"] = "failed"
                    item["error"] = "Worker exited before completing this image"
            write_receipt(directory, result)
    if result["status"] == "completed" and process is not None and return_code not in (None, 0):
        result["status"] = "failed"
        result["error"] = "Worker exited unsuccessfully after writing its receipt"
        write_receipt(directory, result)
    for index, item in enumerate(result["items"]):
        if item["status"] != "completed":
            continue
        try:
            # Never trust paths embedded in a recovered receipt.
            filename = "{:02d}_{}.png".format(index, item["pass"])
            if item["pass"] not in ("beauty", "wire") or png_evidence(directory / filename) != item["image"]:
                raise ValueError("Image differs from the decoded worker output")
        except (OSError, ValueError, KeyError) as exc:
            item["status"] = "failed"
            item["error"] = str(exc)
            if result["status"] in TERMINAL:
                result["status"] = "failed"
    result["job_directory"] = str(directory)
    result["stdout_path"] = str(directory / "stdout.log")
    result["stderr_path"] = str(directory / "stderr.log")
    result["cancellation_requested"] = (directory / "cancel").exists()
    result["process_observed"] = process is not None
    result["pid"] = process.pid if process is not None else None
    result["progress"] = sum(item["status"] in TERMINAL for item in result["items"]) / len(result["items"])
    job["status"] = result["status"]
    return result
