from unittest.mock import MagicMock

import pytest

from dcc_mcp_blender import _render_job_ops as jobs
from dcc_mcp_blender._multiview_receipt import multiview_context, png_evidence, write_receipt


def receipt(tmp_path, status="running"):
    result = dict(
        job_id="test",
        kind="multiview",
        status=status,
        items=[{"camera": "Camera", "pass": "beauty", "status": "pending"}],
    )
    write_receipt(tmp_path, result)
    return result


def test_recovery_does_not_claim_live_worker(tmp_path):
    receipt(tmp_path)
    result = jobs.get_render_job("test", str(tmp_path))
    assert result["success"]
    assert result["context"]["status"] == "unknown"
    assert result["context"]["last_recorded_status"] == "running"
    assert result["context"]["process_observed"] is False


def test_cancel_recovered_job_does_not_kill_pid(tmp_path, monkeypatch):
    receipt(tmp_path)
    kill = MagicMock()
    monkeypatch.setattr(jobs, "_terminate_process_tree", kill)
    result = jobs.cancel_render_job("test", str(tmp_path))
    assert result["success"]
    assert result["context"]["cancellation_requested"]
    assert (tmp_path / "cancel").is_file()
    kill.assert_not_called()


def test_wrong_receipt_identity_is_rejected(tmp_path):
    receipt(tmp_path)
    assert not jobs.get_render_job("other", str(tmp_path))["success"]
    assert not jobs.cancel_render_job("other", str(tmp_path))["success"]
    assert not (tmp_path / "cancel").exists()


def test_worker_crash_marks_unfinished_items_failed(tmp_path):
    receipt(tmp_path)
    process = MagicMock()
    process.poll.return_value = 2
    result = multiview_context(dict(job_id="test", job_directory=str(tmp_path), process=process))
    assert result["status"] == "failed"
    assert result["items"][0]["status"] == "failed"
    assert jobs.get_render_job("test", str(tmp_path))["context"]["status"] == "failed"


def test_completed_output_is_rechecked_not_just_file_exists(tmp_path):
    result = receipt(tmp_path, "completed")
    # Receipt verification hashes the worker-decoded PNG, not only its magic.
    path = tmp_path / "00_beauty.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0\0\0\rIHDR" + (16).to_bytes(4, "big") * 2 + b"original")
    result["items"][0].update(status="completed", image=png_evidence(path))
    write_receipt(tmp_path, result)
    path.write_bytes(path.read_bytes()[:-1] + b"X")
    result = jobs.get_render_job("test", str(tmp_path))["context"]
    assert result["status"] == "failed"
    assert result["items"][0]["status"] == "failed"


@pytest.mark.parametrize(
    "field,value",
    [
        ("camera_names", []),
        ("camera_names", ["A"] * 9),
        ("passes", ["wire", "wire"]),
        ("resolution_x", 4097),
        ("wire_radius", float("nan")),
    ],
)
def test_preflight_rejects_invalid_arguments_before_saving(tmp_path, monkeypatch, field, value):
    from dcc_mcp_blender._multiview_ops import start_multiview_render_job

    bpy = MagicMock()
    monkeypatch.setitem(__import__("sys").modules, "bpy", bpy)
    args = dict(output_directory=str(tmp_path), camera_names=["A"])
    args[field] = value
    assert not start_multiview_render_job(**args)["success"]
    bpy.ops.wm.save_as_mainfile.assert_not_called()
    assert list(tmp_path.iterdir()) == []


def test_wire_contract_is_discoverable():
    from pathlib import Path

    import yaml

    root = Path(__file__).resolve().parents[1] / "src/dcc_mcp_blender/skills/blender-render"
    contracts = {tool["name"]: tool for tool in yaml.safe_load((root / "tools.yaml").read_text())["tools"]}
    contract = contracts["start_multiview_render_job"]
    assert contract["job_strategy"] == "isolated"
    assert contract["affinity"] == "main"
    assert contract["input_schema"]["properties"]["camera_names"]["maxItems"] == 8
    assert "job_directory" in contracts["get_render_job"]["input_schema"]["properties"]
    assert "job_directory" in contracts["cancel_render_job"]["input_schema"]["properties"]


def test_worker_observes_cancel_before_first_image(tmp_path, monkeypatch):
    import importlib.util
    import sys
    from pathlib import Path

    path = Path(jobs.__file__).with_name("_multiview_worker.py")
    spec = importlib.util.spec_from_file_location("test_multiview_worker", path)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    receipt(tmp_path)
    (tmp_path / "request.json").write_text('{"job_id":"test"}')
    (tmp_path / "cancel").touch()
    bpy = MagicMock()
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    worker.run(tmp_path)
    result = jobs.get_render_job("test", str(tmp_path))["context"]
    assert result["status"] == "cancelled"
    assert result["items"][0]["status"] == "cancelled"
    bpy.ops.wm.open_mainfile.assert_not_called()


def test_corrupt_earlier_image_does_not_claim_running_worker_stopped(tmp_path):
    result = receipt(tmp_path)
    result["items"][0].update(status="completed", image={})
    write_receipt(tmp_path, result)
    process = MagicMock()
    process.poll.return_value = None
    context = multiview_context(dict(job_id="test", job_directory=str(tmp_path), process=process))
    assert context["status"] == "running"
    assert context["items"][0]["status"] == "failed"


@pytest.mark.parametrize("budget", [0, 500001, True, 1.5])
def test_source_edge_budget_is_validated(tmp_path, monkeypatch, budget):
    import sys

    from dcc_mcp_blender._multiview_ops import start_multiview_render_job

    bpy = MagicMock()
    bpy.context.scene.objects.get.return_value.type = "CAMERA"
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    result = start_multiview_render_job(str(tmp_path), ["Camera"], max_source_edges=budget)
    assert not result["success"]
    bpy.ops.wm.save_as_mainfile.assert_not_called()


def test_worker_resolves_relative_executable_before_changing_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    popen = MagicMock()
    monkeypatch.setattr(jobs.subprocess, "Popen", popen)
    output = tmp_path / "output"
    output.mkdir()
    jobs._launch_worker(["cache/Blender.app/Blender", "--background"], output, output / "out", output / "err")
    assert popen.call_args.args[0][0] == str((tmp_path / "cache/Blender.app/Blender").resolve())
    assert popen.call_args.kwargs["cwd"] == str(output)
