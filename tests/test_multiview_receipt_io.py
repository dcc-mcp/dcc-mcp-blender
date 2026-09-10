"""Receipt I/O contracts under bounded Windows file-sharing conflicts."""

import errno
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from dcc_mcp_blender import _multiview_receipt as receipts
from dcc_mcp_blender._multiview_receipt import read_receipt, write_receipt
from tests.conftest import load_skill_script


def _receipt(status="running"):
    return dict(
        job_id="test",
        kind="multiview",
        status=status,
        items=[{"camera": "Camera", "pass": "beauty", "status": "pending" if status == "running" else status}],
    )


def _sharing_error(code=5):
    error = PermissionError(errno.EACCES, "Receipt sharing conflict")
    if code is not None:
        error.winerror = code
    return error


def test_writer_recovers_from_sharing_conflict_without_replacing_old_receipt_early(tmp_path, monkeypatch):
    original = _receipt()
    write_receipt(tmp_path, original)
    updated = _receipt("failed")
    replace = Path.replace
    conflicted = False

    def replace_after_conflict(path, target):
        nonlocal conflicted
        if not conflicted:
            conflicted = True
            assert read_receipt(tmp_path, "test") == original
            raise _sharing_error()
        return replace(path, target)

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(Path, "replace", replace_after_conflict)
    write_receipt(tmp_path, updated)

    assert read_receipt(tmp_path, "test") == updated
    assert list(tmp_path.iterdir()) == [tmp_path / "result.json"]


@pytest.mark.parametrize("boundary", ["open", "stat"])
@pytest.mark.parametrize("winerror", [5, 32, 33, None])
def test_public_poll_recovers_from_transient_windows_read_error(tmp_path, monkeypatch, boundary, winerror):
    write_receipt(tmp_path, _receipt())
    original = getattr(Path, boundary)
    conflicted = False

    def open_after_conflict(path, *args, **kwargs):
        nonlocal conflicted
        if path == tmp_path / "result.json" and not conflicted:
            conflicted = True
            raise _sharing_error(winerror)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(Path, boundary, open_after_conflict)
    result = load_skill_script("blender-render", "get_render_job").main(job_id="test", job_directory=str(tmp_path))

    assert result["success"], result
    assert result["context"]["status"] == "unknown"
    assert result["context"]["last_recorded_status"] == "running"
    assert result["context"]["process_observed"] is False


@pytest.fixture
def retry_clock(monkeypatch):
    clock = SimpleNamespace(now=0.0, sleeps=[])

    def sleep(delay):
        clock.sleeps.append(delay)
        clock.now += delay

    monkeypatch.setattr(receipts, "time", SimpleNamespace(monotonic=lambda: clock.now, sleep=sleep))
    return clock


def _reject_io(monkeypatch, tmp_path, operation, error):
    boundary = "open" if operation == "read" else "replace"
    original = getattr(Path, boundary)
    attempts = []

    def fail(path, *args, **kwargs):
        if operation == "replace" or path == tmp_path / "result.json":
            attempts.append(path)
            raise error
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, boundary, fail)
    return attempts


@pytest.mark.parametrize("operation,winerror", [("read", 5), ("read", None), ("replace", 32), ("replace", 33)])
def test_persistent_conflict_fails_within_short_retry_budget(tmp_path, monkeypatch, retry_clock, operation, winerror):
    original = _receipt()
    write_receipt(tmp_path, original)
    error = _sharing_error(winerror)
    monkeypatch.setattr(sys, "platform", "win32")
    attempts = _reject_io(monkeypatch, tmp_path, operation, error)

    if operation == "read":
        result = load_skill_script("blender-render", "get_render_job").main(job_id="test", job_directory=str(tmp_path))
        assert result["success"] is False
        assert result["message"] == "Render receipt unavailable"
        assert "Receipt sharing conflict" in result["error"]
        assert "status" not in result["context"]
    else:
        with pytest.raises(PermissionError) as raised:
            write_receipt(tmp_path, _receipt("failed"))
        assert raised.value is error
        assert read_receipt(tmp_path, "test") == original
        assert list(tmp_path.iterdir()) == [tmp_path / "result.json"]

    assert 1 < len(attempts) <= 10
    assert retry_clock.sleeps
    assert retry_clock.now <= 0.1


def test_retry_deadline_prevents_another_attempt_after_scheduler_delay(tmp_path, monkeypatch, retry_clock):
    write_receipt(tmp_path, _receipt())
    monkeypatch.setattr(sys, "platform", "win32")
    attempts = _reject_io(monkeypatch, tmp_path, "read", _sharing_error())

    def delayed_sleep(delay):
        retry_clock.now += 0.2

    monkeypatch.setattr(receipts.time, "sleep", delayed_sleep)
    result = load_skill_script("blender-render", "get_render_job").main(job_id="test", job_directory=str(tmp_path))

    assert result["success"] is False
    assert result["message"] == "Render receipt unavailable"
    assert len(attempts) == 1


@pytest.mark.parametrize("operation", ["read", "replace"])
@pytest.mark.parametrize(
    "platform,winerror,error_number",
    [
        ("linux", 5, errno.EACCES),
        ("darwin", None, errno.EACCES),
        ("win32", 183, errno.EACCES),
        ("win32", None, errno.EIO),
        ("win32", None, errno.ENOENT),
    ],
)
def test_other_io_errors_are_not_retried(
    tmp_path, monkeypatch, retry_clock, operation, platform, winerror, error_number
):
    write_receipt(tmp_path, _receipt())
    error = OSError(error_number, "Permanent receipt error")
    if winerror is not None:
        error.winerror = winerror
    monkeypatch.setattr(sys, "platform", platform)
    attempts = _reject_io(monkeypatch, tmp_path, operation, error)

    if operation == "read":
        result = load_skill_script("blender-render", "get_render_job").main(job_id="test", job_directory=str(tmp_path))
        assert result["success"] is False
        assert result["message"] == "Render receipt unavailable"
    else:
        with pytest.raises(OSError) as raised:
            write_receipt(tmp_path, _receipt("failed"))
        assert raised.value is error

    assert len(attempts) == 1
    assert not retry_clock.sleeps


def test_windows_writer_without_winerror_does_not_retry_crt_access_error(tmp_path, monkeypatch, retry_clock):
    write_receipt(tmp_path, _receipt())
    monkeypatch.setattr(sys, "platform", "win32")
    attempts = _reject_io(monkeypatch, tmp_path, "replace", _sharing_error(None))

    with pytest.raises(PermissionError):
        write_receipt(tmp_path, _receipt("failed"))

    assert len(attempts) == 1
    assert not retry_clock.sleeps


@pytest.mark.parametrize("corruption", ["json", "size", "job_id", "kind", "status", "items", "completed"])
def test_invalid_receipts_fail_public_poll_without_retries(tmp_path, monkeypatch, retry_clock, corruption):
    result = _receipt()
    if corruption == "json":
        text = "{invalid JSON"
    elif corruption == "size":
        text = " " * 1_000_001
    else:
        if corruption == "completed":
            result["status"] = "completed"
        else:
            result[corruption] = "invalid"
        text = json.dumps(result)
    (tmp_path / "result.json").write_text(text, encoding="utf-8")
    monkeypatch.setattr(sys, "platform", "win32")

    response = load_skill_script("blender-render", "get_render_job").main(job_id="test", job_directory=str(tmp_path))

    assert response["success"] is False
    assert response["message"] == "Render receipt unavailable"
    assert "status" not in response["context"]
    assert not retry_clock.sleeps


def test_overlapping_writers_use_independent_temporary_files(tmp_path, monkeypatch):
    write_receipt(tmp_path, _receipt())
    replace = Path.replace
    pending = []
    final = _receipt("failed")

    def overlapping_replace(path, target):
        pending.append(path)
        if len(pending) == 1:
            write_receipt(tmp_path, _receipt("cancelled"))
            assert read_receipt(tmp_path, "test")["status"] == "cancelled"
        return replace(path, target)

    monkeypatch.setattr(Path, "replace", overlapping_replace)
    write_receipt(tmp_path, final)

    assert len(set(pending)) == 2
    assert read_receipt(tmp_path, "test") == final
    assert list(tmp_path.iterdir()) == [tmp_path / "result.json"]


@pytest.mark.parametrize("failure", [errno.ENOSPC, errno.EIO, "serialization"])
def test_cleanup_error_does_not_mask_original_write_failure(tmp_path, monkeypatch, failure):
    original = _receipt()
    write_receipt(tmp_path, original)
    updated = _receipt("failed")
    primary_error = None
    if failure == "serialization":
        updated["invalid"] = object()
    else:
        primary_error = OSError(failure, "Primary receipt write failure")

        def fail_replace(path, target):
            raise primary_error

        monkeypatch.setattr(Path, "replace", fail_replace)

    def fail_cleanup(path, **kwargs):
        raise PermissionError("Temporary receipt cleanup denied")

    monkeypatch.setattr(Path, "unlink", fail_cleanup)
    with pytest.raises(TypeError if failure == "serialization" else OSError) as raised:
        write_receipt(tmp_path, updated)

    if primary_error is not None:
        assert raised.value is primary_error
    else:
        assert "not JSON serializable" in str(raised.value)
    assert read_receipt(tmp_path, "test") == original
