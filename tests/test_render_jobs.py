from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from dcc_mcp_blender import _render_job_ops as jobs


def _write_valid_exr(path):
    path.write_bytes(b"\x76\x2f\x31\x01payload")


def _write_valid_png(path):
    path.write_bytes(b"\x89PNG\r\n\x1a\npayload")


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
    assert command[command.index("--render-format") + 1] == "OPEN_EXR_MULTILAYER"
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

    assert command[command.index("--render-format") + 1] == "PNG"
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


def test_rejects_unsupported_background_render_format(tmp_path):
    with pytest.raises(ValueError, match="output_format"):
        jobs._expected_output_path(str(tmp_path / "beauty_####"), 1, output_format="TIFF")


def test_start_get_cancel_background_render_job(monkeypatch, tmp_path):
    blend = tmp_path / "scene.blend"
    blend.write_bytes(b"blend")
    pattern = str(tmp_path / "beauty_####")
    saved = []
    fake_bpy = SimpleNamespace(
        app=SimpleNamespace(binary_path="blender"),
        data=SimpleNamespace(filepath=str(blend)),
        ops=SimpleNamespace(wm=SimpleNamespace(save_as_mainfile=lambda filepath: saved.append(filepath))),
    )
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
