from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from dcc_mcp_blender import _render_job_ops as jobs
from dcc_mcp_blender._image_format import worker_format_expression


def _write_valid_exr(path):
    path.write_bytes(b"\x76\x2f\x31\x01payload")


def _write_valid_png(path):
    path.write_bytes((Path(__file__).parent / "fixtures" / "png" / "basn6a08.png").read_bytes())


def _write_valid_jpeg(path):
    path.write_bytes(b"\xff\xd8\xffpayload")


def _write_valid_tiff(path):
    path.write_bytes(b"\x49\x49\x2a\x00payload")


def _write_valid_bmp(path):
    path.write_bytes(b"BMpayload")


def _fake_bpy(filepath, file_format="PNG"):
    """Minimal bpy stand-in exposing the scene render format the job reads."""
    return SimpleNamespace(
        app=SimpleNamespace(binary_path="blender"),
        data=SimpleNamespace(filepath=str(filepath)),
        context=SimpleNamespace(
            scene=SimpleNamespace(render=SimpleNamespace(image_settings=SimpleNamespace(file_format=file_format)))
        ),
        ops=SimpleNamespace(wm=SimpleNamespace(save_as_mainfile=lambda filepath: [])),
    )


def test_build_command_uses_multilayer_exr_and_exact_frames(tmp_path):
    command = jobs._build_blender_command(
        blender_path="blender",
        scene_path=str(tmp_path / "scene.blend"),
        output_pattern=str(tmp_path / "beauty_####"),
        frames=[1, 3, 7],
        device="OPTIX",
        factory_startup=False,
    )

    assert command[:3] == ["blender", "--background", str(tmp_path / "scene.blend")]
    assert "--factory-startup" not in command
    assert command[command.index("--python-expr") + 1] == worker_format_expression("OPEN_EXR_MULTILAYER")
    assert [command[index + 1] for index, value in enumerate(command) if value == "--render-frame"] == [
        "1",
        "3",
        "7",
    ]
    assert command[-3:] == ["--", "--cycles-device", "OPTIX"]

    factory_command = jobs._build_blender_command(
        blender_path="blender",
        scene_path=str(tmp_path / "scene.blend"),
        output_pattern=str(tmp_path / "beauty_####"),
        frames=[1],
        device="CPU",
        factory_startup=True,
    )
    assert factory_command[2] == "--factory-startup"


def test_build_command_omits_cycles_device_when_unset(tmp_path):
    """No device means no override: the worker uses the .blend's Cycles device."""
    command = jobs._build_blender_command(
        blender_path="blender",
        scene_path=str(tmp_path / "scene.blend"),
        output_pattern=str(tmp_path / "beauty_####"),
        frames=[1],
        factory_startup=False,
    )

    assert "--" not in command
    assert "--cycles-device" not in command


def test_build_command_omits_cycles_device_for_empty_string(tmp_path):
    command = jobs._build_blender_command(
        blender_path="blender",
        scene_path=str(tmp_path / "scene.blend"),
        output_pattern=str(tmp_path / "beauty_####"),
        frames=[1],
        device="",
        factory_startup=False,
    )

    assert "--cycles-device" not in command


def test_build_command_supports_png_animation_output(tmp_path):
    pattern = str(tmp_path / "beauty_####")

    command = jobs._build_blender_command(
        blender_path="blender",
        scene_path=str(tmp_path / "scene.blend"),
        output_pattern=pattern,
        output_format="PNG",
        frames=[2],
        device="CPU",
        factory_startup=False,
    )

    assert command[command.index("--python-expr") + 1] == worker_format_expression("PNG")
    assert jobs._expected_output_path(pattern, 2, output_format="PNG") == tmp_path / "beauty_0002.png"


def test_select_frames_resumes_only_missing_nonempty_exrs(tmp_path):
    pattern = str(tmp_path / "beauty_####")
    _write_valid_exr(jobs._expected_output_path(pattern, 1))
    jobs._expected_output_path(pattern, 3).write_bytes(b"not an exr")

    assert jobs._select_frames(pattern, 1, 4, 1, resume_missing=True) == [2, 3, 4]
    assert jobs._select_frames(pattern, 1, 4, 2, resume_missing=False) == [1, 3]


def test_select_frames_resumes_only_missing_valid_pngs(tmp_path):
    pattern = str(tmp_path / "beauty_####")
    _write_valid_png(jobs._expected_output_path(pattern, 1, output_format="PNG"))
    jobs._expected_output_path(pattern, 3, output_format="PNG").write_bytes(b"not a png")

    assert jobs._select_frames(pattern, 1, 4, 1, resume_missing=True, output_format="PNG") == [2, 3, 4]


@pytest.mark.parametrize("payload", [b"\x89PNG\r\n\x1a\n", b"\x89PNG\r\n\x1a\npayload"])
def test_png_header_only_is_not_skipped_or_reported_complete(tmp_path, payload):
    pattern = str(tmp_path / "beauty_####")
    jobs._expected_output_path(pattern, 1, output_format="PNG").write_bytes(payload)
    assert not jobs._is_valid_output(tmp_path / "beauty_0001.png", output_format="PNG")
    assert jobs._select_frames(pattern, 1, 1, 1, resume_missing=True, output_format="PNG") == [1]
    context = jobs._job_context(
        dict(
            job_id="truncated-png",
            status="running",
            process=SimpleNamespace(pid=1, poll=lambda: 0),
            output_format="PNG",
            output_pattern=pattern,
            frames=[1],
            stdout_path="",
            stderr_path="",
        )
    )
    assert context["status"] == "failed"
    assert context["written_frame_count"] == 0
    assert context["missing_frame_sample"] == [1]


def test_complete_png_job_validates_each_frame_once_without_bpy(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "bpy", None)
    pattern = str(tmp_path / "beauty_####")
    _write_valid_png(jobs._expected_output_path(pattern, 1, output_format="PNG"))
    original = jobs.is_complete_png
    calls = []

    def validate(stream, size):
        calls.append(size)
        return original(stream, size)

    monkeypatch.setattr(jobs, "is_complete_png", validate)
    context = jobs._job_context(
        dict(
            job_id="valid-png",
            status="running",
            process=SimpleNamespace(pid=1, poll=lambda: 0),
            output_format="PNG",
            output_pattern=pattern,
            frames=[1],
            stdout_path="",
            stderr_path="",
        )
    )
    assert context["status"] == "completed"
    assert context["written_frame_count"] == 1
    assert len(calls) == 1


def test_completed_png_job_is_failed_if_output_later_becomes_incomplete(tmp_path):
    pattern = str(tmp_path / "beauty_####")
    path = jobs._expected_output_path(pattern, 1, output_format="PNG")
    _write_valid_png(path)
    job = dict(
        job_id="later-truncated-png",
        status="running",
        process=SimpleNamespace(pid=1, poll=lambda: 0),
        output_format="PNG",
        output_pattern=pattern,
        frames=[1],
        stdout_path="",
        stderr_path="",
    )
    assert jobs._job_context(job)["status"] == "completed"
    path.write_bytes(b"\x89PNG\r\n\x1a\n")
    context = jobs._job_context(job)
    assert context["status"] == "failed"
    assert context["written_frame_count"] == 0
    assert context["missing_frame_sample"] == [1]


@pytest.mark.parametrize("replace", [False, True])
def test_png_changed_during_validation_is_rejected(monkeypatch, tmp_path, replace):
    path = tmp_path / "frame.png"
    _write_valid_png(path)
    original = jobs.is_complete_png

    def validate(stream, size):
        result = original(stream, size)
        if replace:
            other = tmp_path / "replacement.png"
            other.write_bytes(b"\x89PNG\r\n\x1a\n")
            other.replace(path)
        else:
            path.write_bytes(b"\x89PNG\r\n\x1a\n")
        return result

    monkeypatch.setattr(jobs, "is_complete_png", validate)
    assert not jobs._is_valid_output(path, output_format="PNG")


def test_png_accepts_windows_stat_and_fstat_ctime_difference(monkeypatch, tmp_path):
    """Windows path stat can expose birth time while fstat exposes change time."""
    path = tmp_path / "frame.png"
    _write_valid_png(path)
    by_path = path.stat()
    calls = []

    def fstat(_fd):
        calls.append(_fd)
        return SimpleNamespace(
            st_dev=by_path.st_dev,
            st_ino=by_path.st_ino,
            st_size=by_path.st_size,
            st_mtime_ns=by_path.st_mtime_ns,
            st_ctime_ns=by_path.st_ctime_ns + 123456789,
        )

    monkeypatch.setattr(jobs.os, "fstat", fstat)
    assert jobs._is_valid_output(path, output_format="PNG")
    assert len(calls) == 2


@pytest.mark.parametrize("field", ["st_size", "st_mtime_ns", "st_ctime_ns"])
def test_png_rejects_fd_metadata_change_without_relying_on_path_ctime(monkeypatch, tmp_path, field):
    path = tmp_path / "frame.png"
    _write_valid_png(path)
    by_path = path.stat()
    snapshot = {name: getattr(by_path, name) for name in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")}
    # Simulate Windows: the path's ctime is unrelated to either fd ctime.
    snapshot["st_ctime_ns"] += 123456789
    calls = []

    def fstat(_fd):
        changed = dict(snapshot)
        if calls:
            changed[field] += 1
        calls.append(_fd)
        return SimpleNamespace(**changed)

    monkeypatch.setattr(jobs.os, "fstat", fstat)
    assert not jobs._is_valid_output(path, output_format="PNG")
    assert len(calls) == 2


@pytest.mark.parametrize("field", ["st_dev", "st_ino", "st_size", "st_mtime_ns"])
def test_png_rejects_current_path_mismatch_even_when_fd_is_unchanged(monkeypatch, tmp_path, field):
    path = tmp_path / "frame.png"
    _write_valid_png(path)
    original_stat = Path.stat
    validation_complete = []
    original_validate = jobs.is_complete_png

    def validate(stream, size):
        result = original_validate(stream, size)
        validation_complete.append(True)
        return result

    def stat(self, *args, **kwargs):
        actual = original_stat(self, *args, **kwargs)
        if self != path or not validation_complete:
            return actual
        snapshot = {
            name: getattr(actual, name) for name in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        }
        snapshot[field] += 1
        return SimpleNamespace(**snapshot)

    monkeypatch.setattr(jobs, "is_complete_png", validate)
    monkeypatch.setattr(Path, "stat", stat)
    assert not jobs._is_valid_output(path, output_format="PNG")


def test_rejects_unsupported_background_render_format(tmp_path):
    # WEBP is a valid set_render_settings format but has no stable leading
    # signature, so a worker cannot verify a resumed frame; it stays rejected.
    with pytest.raises(ValueError, match="output_format"):
        jobs._expected_output_path(str(tmp_path / "beauty_####"), 1, output_format="WEBP")


def test_start_get_cancel_background_render_job(monkeypatch, tmp_path):
    blend = tmp_path / "scene.blend"
    blend.write_bytes(b"blend")
    pattern = str(tmp_path / "beauty_####")
    saved = []
    fake_bpy = _fake_bpy(blend, file_format="OPEN_EXR_MULTILAYER")
    fake_bpy.ops.wm.save_as_mainfile = lambda filepath: saved.append(filepath)
    monkeypatch.setitem(sys.modules, "bpy", fake_bpy)

    created = []

    class FakeProcess:
        pid = 4321

        def poll(self):
            return None

    def fake_popen(command, **kwargs):
        created.append((command, kwargs))
        return FakeProcess()

    terminated = []
    monkeypatch.setattr(jobs.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(jobs, "_terminate_process_tree", lambda process: terminated.append(process.pid))
    jobs._JOBS.clear()

    started = jobs.start_render_job(
        output_pattern=pattern,
        start_frame=1,
        end_frame=3,
        device="OPTIX",
    )
    assert started["success"] is True
    assert started["context"]["output_format"] == "OPEN_EXR_MULTILAYER"
    job_id = started["context"]["job_id"]
    assert started["context"]["expected_frame_count"] == 3
    assert saved == [str(blend)]
    assert created[0][1]["env"]["DCC_MCP_BACKGROUND_RENDER"] == "1"

    status = jobs.get_render_job(job_id)
    assert status["context"]["status"] == "running"
    assert status["context"]["written_frame_count"] == 0

    cancelled = jobs.cancel_render_job(job_id)
    assert cancelled["context"]["status"] == "cancelled"
    assert terminated == [4321]
    repeated = jobs.cancel_render_job(job_id)
    assert repeated["context"]["status"] == "cancelled"
    assert terminated == [4321]


def test_start_render_job_reuses_scene_png_format(monkeypatch, tmp_path):
    blend = tmp_path / "scene.blend"
    blend.write_bytes(b"blend")
    pattern = str(tmp_path / "beauty_####")
    monkeypatch.setitem(sys.modules, "bpy", _fake_bpy(blend, file_format="PNG"))

    created = []

    class FakeProcess:
        pid = 7

        def poll(self):
            return None

    monkeypatch.setattr(jobs.subprocess, "Popen", lambda command, **kwargs: created.append(command) or FakeProcess())
    jobs._JOBS.clear()

    started = jobs.start_render_job(output_pattern=pattern, start_frame=1, end_frame=2, device="CPU")

    assert started["success"] is True
    assert started["context"]["output_format"] == "PNG"
    assert created[0][created[0].index("--python-expr") + 1] == worker_format_expression("PNG")
    assert jobs._expected_output_path(pattern, 1, output_format="PNG") == tmp_path / "beauty_0001.png"

    status = jobs.get_render_job(started["context"]["job_id"])
    assert status["context"]["output_format"] == "PNG"


def test_start_render_job_keeps_explicit_format_over_scene(monkeypatch, tmp_path):
    blend = tmp_path / "scene.blend"
    blend.write_bytes(b"blend")
    monkeypatch.setitem(sys.modules, "bpy", _fake_bpy(blend, file_format="PNG"))

    created = []

    class FakeProcess:
        pid = 7

        def poll(self):
            return None

    monkeypatch.setattr(jobs.subprocess, "Popen", lambda command, **kwargs: created.append(command) or FakeProcess())
    jobs._JOBS.clear()

    started = jobs.start_render_job(
        output_pattern=str(tmp_path / "beauty_####"),
        start_frame=1,
        end_frame=1,
        output_format="OPEN_EXR_MULTILAYER",
    )

    assert started["context"]["output_format"] == "OPEN_EXR_MULTILAYER"
    assert created[0][created[0].index("--python-expr") + 1] == worker_format_expression("OPEN_EXR_MULTILAYER")


def test_start_render_job_accepts_every_new_scene_format(monkeypatch, tmp_path):
    """Each container added to the whitelist is reproducible from the scene."""
    blend = tmp_path / "scene.blend"
    blend.write_bytes(b"blend")

    class FakeProcess:
        pid = 11

        def poll(self):
            return None

    for scene_format in ("JPEG", "TIFF", "BMP"):
        monkeypatch.setitem(sys.modules, "bpy", _fake_bpy(blend, file_format=scene_format))
        monkeypatch.setattr(jobs.subprocess, "Popen", lambda command, **kwargs: FakeProcess())
        jobs._JOBS.clear()

        started = jobs.start_render_job(
            output_pattern=str(tmp_path / "beauty_####"),
            start_frame=1,
            end_frame=2,
        )

        assert started["success"] is True, (scene_format, started)
        assert started["context"]["output_format"] == scene_format, started


def test_start_render_job_rejects_unsupported_scene_format(monkeypatch, tmp_path):
    blend = tmp_path / "scene.blend"
    blend.write_bytes(b"blend")
    monkeypatch.setitem(sys.modules, "bpy", _fake_bpy(blend, file_format="WEBP"))
    jobs._JOBS.clear()

    started = jobs.start_render_job(
        output_pattern=str(tmp_path / "beauty_####"),
        start_frame=1,
        end_frame=48,
    )

    assert started["success"] is False
    assert "WEBP" in started["error"]
    assert "OPEN_EXR_MULTILAYER" in started["error"]
    # fail-loud: the message names the tools that can fix the scene instead of
    # letting a worker silently substitute EXR.
    assert "set_render_settings" in started["error"]
    assert "set_render_output" in started["error"]
    assert "silently" in started["error"]
    assert started["prompt"] == (
        "Call set_render_settings or set_render_output with a supported file_format, then retry."
    )


def test_format_tables_share_one_source_of_truth():
    """_SCENE_OUTPUT_FORMATS is derived, so the two cannot drift apart."""
    assert jobs._SCENE_OUTPUT_FORMATS == tuple(jobs._OUTPUT_FORMATS)
    assert set(jobs._SCENE_OUTPUT_FORMATS) == set(jobs._OUTPUT_FORMATS)
    # The whitelist grew past the original three containers.
    assert len(jobs._OUTPUT_FORMATS) >= 5
    for name in ("OPEN_EXR_MULTILAYER", "OPEN_EXR", "PNG", "JPEG", "TIFF"):
        assert name in jobs._OUTPUT_FORMATS
    # Every accepted container is one set_render_settings also offers, so a
    # scene configured through the typed tool is reproducible by a worker.
    from dcc_mcp_blender._render_ops import _IMAGE_FORMATS

    assert set(jobs._OUTPUT_FORMATS) <= set(_IMAGE_FORMATS)
    # The drift guard survives being re-run against a deliberately broken table.
    saved_scene, saved_output = jobs._SCENE_OUTPUT_FORMATS, jobs._OUTPUT_FORMATS
    try:
        jobs._SCENE_OUTPUT_FORMATS = ("PNG",)
        with pytest.raises(AssertionError, match="_SCENE_OUTPUT_FORMATS"):
            jobs._assert_format_tables_agree()
        jobs._SCENE_OUTPUT_FORMATS = saved_scene + ("PNG",)
        with pytest.raises(AssertionError, match="repeat"):
            jobs._assert_format_tables_agree()
    finally:
        jobs._SCENE_OUTPUT_FORMATS, jobs._OUTPUT_FORMATS = saved_scene, saved_output


@pytest.mark.parametrize(
    "name,suffix,writer",
    [
        ("JPEG", ".jpg", _write_valid_jpeg),
        ("TIFF", ".tif", _write_valid_tiff),
        ("BMP", ".bmp", _write_valid_bmp),
    ],
)
def test_new_formats_resolve_extension_and_signature(tmp_path, name, suffix, writer):
    pattern = str(tmp_path / "beauty_####")
    expected = jobs._expected_output_path(pattern, 7, output_format=name)
    assert expected == tmp_path / ("beauty_0007" + suffix)

    # A frame is only "written" once it carries the container's signature.
    assert jobs._is_valid_output(expected, output_format=name) is False
    writer(expected)
    assert jobs._is_valid_output(expected, output_format=name) is True

    # A truncated or foreign frame is not resumable.
    expected.write_bytes(b"nope")
    assert jobs._is_valid_output(expected, output_format=name) is False


def test_select_frames_resumes_missing_new_format_frames(tmp_path):
    pattern = str(tmp_path / "beauty_####")
    _write_valid_jpeg(jobs._expected_output_path(pattern, 1, output_format="JPEG"))
    jobs._expected_output_path(pattern, 2, output_format="JPEG").write_bytes(b"x")

    assert jobs._select_frames(pattern, 1, 3, 1, resume_missing=True, output_format="JPEG") == [2, 3]


def test_resolve_output_format_maps_scene_values():
    assert jobs._resolve_output_format("png", scene_format="OPEN_EXR_MULTILAYER") == "PNG"
    assert jobs._resolve_output_format(None, scene_format="OPEN_EXR") == "OPEN_EXR"
    assert jobs._resolve_output_format("", scene_format="png") == "PNG"
    assert jobs._resolve_output_format(None, scene_format="JPEG") == "JPEG"
    assert jobs._resolve_output_format(None, scene_format="tiff") == "TIFF"
    assert jobs._resolve_output_format(None, scene_format="BMP") == "BMP"
    with pytest.raises(ValueError, match="not supported"):
        jobs._resolve_output_format(None, scene_format="WEBP")
    with pytest.raises(ValueError, match="not supported"):
        jobs._resolve_output_format(None, scene_format="")


def test_scene_open_exr_stays_single_layer(tmp_path):
    pattern = str(tmp_path / "beauty_####")
    assert jobs._expected_output_path(pattern, 1, output_format="OPEN_EXR") == tmp_path / "beauty_0001.exr"
    assert jobs._resolve_output_format(None, scene_format="OPEN_EXR") == "OPEN_EXR"


def test_rejects_output_pattern_without_frame_placeholder(tmp_path):
    with pytest.raises(ValueError, match="#"):
        jobs._select_frames(str(tmp_path / "beauty"), 1, 2, 1, resume_missing=True)

    with pytest.raises(ValueError, match="absolute"):
        jobs._select_frames("beauty_####", 1, 2, 1, resume_missing=True)

    with pytest.raises(ValueError, match="exactly one"):
        jobs._select_frames(str(tmp_path / "shot_##_beauty_####"), 1, 2, 1, resume_missing=True)


def test_cancel_does_not_overwrite_a_just_completed_job(tmp_path):
    pattern = str(tmp_path / "beauty_####")
    _write_valid_exr(jobs._expected_output_path(pattern, 1))

    class CompletedProcess:
        pid = 99

        def poll(self):
            return 0

    job_id = "completed-race"
    jobs._JOBS[job_id] = {
        "job_id": job_id,
        "process": CompletedProcess(),
        "status": "running",
        "frames": [1],
        "output_pattern": pattern,
        "scene_path": str(tmp_path / "scene.blend"),
        "stdout_path": str(tmp_path / "out.log"),
        "stderr_path": str(tmp_path / "err.log"),
        "started_at": 0.0,
    }

    result = jobs.cancel_render_job(job_id)

    assert result["context"]["status"] == "completed"


class _FailedProcess:
    """A worker that has already exited non-zero."""

    pid = 4242

    def poll(self):
        return 1


def _failed_job(tmp_path, stderr_text, job_id="failed-device", stdout_text=""):
    """Register a running job whose worker already exited, plus its logs."""
    stderr_path = tmp_path / "err.log"
    stderr_path.write_text(stderr_text, encoding="utf-8")
    (tmp_path / "out.log").write_text(stdout_text, encoding="utf-8")
    jobs._JOBS[job_id] = {
        "job_id": job_id,
        "process": _FailedProcess(),
        "status": "running",
        "frames": [1],
        "output_pattern": str(tmp_path / "beauty_####"),
        "scene_path": str(tmp_path / "scene.blend"),
        "stdout_path": str(tmp_path / "out.log"),
        "stderr_path": str(stderr_path),
        "started_at": 0.0,
    }
    return job_id


def test_failed_job_attributes_missing_cycles_device(tmp_path):
    """A missing Cycles device is attributed to ``device``, not anonymous."""
    jobs._JOBS.clear()
    job_id = _failed_job(tmp_path, "Error: Found no Cycles device of the specified type\n")

    result = jobs.get_render_job(job_id)

    context = result["context"]
    assert context["status"] == "failed"
    assert "Found no Cycles device" in context["stderr_tail"]
    hint = context["failure_hint"]
    assert "device" in hint
    assert 'device="CPU"' in hint
    assert hint in result["message"]
    assert result["prompt"] == hint


def test_failed_job_reports_stderr_tail_without_device_hint(tmp_path):
    """A non-device failure still carries the tail but invents no device hint."""
    jobs._JOBS.clear()
    job_id = _failed_job(tmp_path, "Error: Cannot open file /nope/scene.blend\n")

    result = jobs.get_render_job(job_id)
    context = result["context"]

    assert context["status"] == "failed"
    assert "Cannot open file" in context["stderr_tail"]
    assert "failure_hint" not in context
    # Without a device hint the message must still point at the tails, which
    # are the only things that explain the failure.
    assert result["message"] == ("Render job failed; see stderr_tail and stdout_tail for the worker's last output.")
    assert result["prompt"] == "Read stderr_tail and stdout_tail, then resubmit the job."


def test_failed_job_finds_device_error_on_stdout(tmp_path):
    """Blender reports the device error on stdout on some platforms."""
    jobs._JOBS.clear()
    job_id = _failed_job(
        tmp_path,
        stderr_text="",
        stdout_text="00:01.687  reports | ERROR Found no Cycles device of the specified type\n",
    )

    context = jobs.get_render_job(job_id)["context"]

    assert context["stdout_tail"].strip()
    assert 'device="CPU"' in context["failure_hint"]


def test_failed_job_survives_unreadable_stderr(tmp_path):
    """A missing log must not turn a status read into an error."""
    jobs._JOBS.clear()
    job_id = _failed_job(tmp_path, "ignored")
    jobs._JOBS[job_id]["stderr_path"] = str(tmp_path / "missing.log")

    result = jobs.get_render_job(job_id)

    assert result["success"] is True
    assert result["context"]["status"] == "failed"
    assert result["context"]["stderr_tail"] == ""
    assert result["context"]["stdout_tail"] == ""


def test_completed_job_exposes_no_failure_fields(tmp_path):
    """Failure metadata is failure-only, so a green job stays quiet."""
    jobs._JOBS.clear()
    pattern = str(tmp_path / "beauty_####")
    _write_valid_exr(jobs._expected_output_path(pattern, 1))
    jobs._JOBS["done"] = {
        "job_id": "done",
        "process": SimpleNamespace(pid=1, poll=lambda: 0),
        "status": "running",
        "frames": [1],
        "output_pattern": pattern,
        "scene_path": str(tmp_path / "scene.blend"),
        "stdout_path": str(tmp_path / "out.log"),
        "stderr_path": str(tmp_path / "err.log"),
        "started_at": 0.0,
    }

    result = jobs.get_render_job("done")

    assert result["message"] == "Render job status"
    assert result["context"]["status"] == "completed"
    assert "stderr_tail" not in result["context"]


def test_windows_terminate_hides_taskkill_console(monkeypatch):
    calls = []

    monkeypatch.setattr(jobs.os, "name", "nt")
    monkeypatch.setattr(jobs.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(
        jobs.subprocess,
        "run",
        lambda command, **kwargs: calls.append((command, kwargs)),
    )

    jobs._terminate_process_tree(SimpleNamespace(pid=4321, poll=lambda: None))

    assert calls[0][0] == ["taskkill", "/PID", "4321", "/T", "/F"]
    # A console-subsystem taskkill must never inherit a visible console.
    assert calls[0][1]["creationflags"] == 0x08000000


def test_terminate_skips_already_exited_process(monkeypatch):
    calls = []
    monkeypatch.setattr(jobs.os, "name", "nt")
    monkeypatch.setattr(
        jobs.subprocess,
        "run",
        lambda command, **kwargs: calls.append(command),
    )

    jobs._terminate_process_tree(SimpleNamespace(pid=4321, poll=lambda: 0))

    assert calls == []
