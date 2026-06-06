"""Unit tests for blender-render-farm skill scripts.

Covers behavioral contracts that structural/lint tests cannot catch:
- Flamenco v3 API endpoint correctness and HTTP verbs
- Single-frame validation acceptance
- Priority passthrough in submission
- Cooperative cancel checkpoints
"""

from __future__ import annotations

import json
import types
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

from tests.conftest import _LOAD_COUNTER, SKILLS_ROOT, load_and_call, make_mock_bpy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_urllib_patch(urllib_request_mock: MagicMock) -> dict:
    """Build a sys.modules patch dict for scripts that ``import urllib.request``.

    Scripts do ``import urllib.request`` which requires ``urllib`` to be a
    real module/proxy whose ``request`` attribute resolves to our mock.
    """

    class _UrllibProxy(types.ModuleType):
        request = urllib_request_mock
        error = urllib.error

    _UrllibProxy.__name__ = "urllib"
    return {
        "urllib": _UrllibProxy("urllib"),
        "urllib.request": urllib_request_mock,
        "urllib.error": urllib.error,
    }


def _load_with_urllib_mock(
    rel_path: str,
    urllib_request_mock: MagicMock,
    dcc_mcp_core_mock: MagicMock | None = None,
    bpy_mock: MagicMock | None = None,
    **kwargs,
):
    """Load a skill script with urllib.request and optionally dcc_mcp_core mocked.

    Args:
        rel_path: Script path relative to ``skills/``.
        urllib_request_mock: MagicMock replacing ``urllib.request``.
        dcc_mcp_core_mock: If given, replaces ``dcc_mcp_core`` in sys.modules
            so that ``from dcc_mcp_core import ...`` resolves to this mock.
        bpy_mock: If given, uses this as ``bpy`` instead of auto-creating one.
        **kwargs: Keyword arguments forwarded to ``main()``.
    """
    _LOAD_COUNTER[0] += 1
    fpath = SKILLS_ROOT / rel_path
    mod_name = f"skill_rf_{fpath.stem}_{_LOAD_COUNTER[0]}"
    import importlib.util

    spec = importlib.util.spec_from_file_location(mod_name, str(fpath))
    mod = importlib.util.module_from_spec(spec)
    patches = _make_urllib_patch(urllib_request_mock)
    patches.update(
        {
            "bpy": bpy_mock or make_mock_bpy(),
            "mathutils": MagicMock(),
        }
    )
    if dcc_mcp_core_mock is not None:
        patches["dcc_mcp_core"] = dcc_mcp_core_mock
    with patch.dict("sys.modules", patches):
        spec.loader.exec_module(mod)
        return mod.main(**kwargs)


# ---------------------------------------------------------------------------
# Flamenco API endpoint correctness
# ---------------------------------------------------------------------------


class TestFlamencoEndpoints:
    """Verify that the right Flamenco v3 API URLs and HTTP verbs are used."""

    def test_render_farm_status_hits_status_and_workers_endpoints(self):
        """GET /api/v3/status and GET /api/v3/worker-mgt/workers (not /workers)."""
        urllib_mock = MagicMock()
        # Simulate successful responses
        resp_mock = MagicMock()
        resp_mock.read.return_value = b'{"version":"3.5","name":"Flamenco Manager"}'
        resp_mock.__enter__.return_value = resp_mock
        urllib_mock.Request.return_value = MagicMock()
        urllib_mock.urlopen.return_value = resp_mock

        result = _load_with_urllib_mock(
            "blender-render-farm/scripts/render_farm_status.py",
            urllib_mock,
        )

        assert result["success"] is True
        # Collect all Request calls and their args
        requests = urllib_mock.Request.call_args_list
        urls = [c[0][0] if c[0] else "" for c in requests]

        # Must hit /api/v3/status (not /api/v3/workers)
        assert any("/api/v3/status" in u for u in urls), "Expected GET /api/v3/status but got: {}".format(urls)
        # Must hit /api/v3/worker-mgt/workers
        assert any("/api/v3/worker-mgt/workers" in u for u in urls), (
            "Expected GET /api/v3/worker-mgt/workers but got: {}".format(urls)
        )
        # Must NOT hit the old /api/v3/workers (without worker-mgt prefix)
        assert not any(
            "/api/v3/workers" == u.rstrip("/").split("?")[0].rsplit("/", 1)[-1] and "worker-mgt" not in u for u in urls
        ), "Must not call deprecated /api/v3/workers, use /api/v3/worker-mgt/workers. Got: {}".format(urls)
        # Must NOT hit the old /api/v3/jobs/queue
        assert not any("/api/v3/jobs/queue" in u for u in urls), (
            "Must not call deprecated /api/v3/jobs/queue. Got: {}".format(urls)
        )

    def test_cancel_render_job_hits_setstatus_endpoint(self):
        """POST /api/v3/jobs/{job_id}/setstatus (not /status)."""
        urllib_mock = MagicMock()
        resp_mock = MagicMock()
        resp_mock.read.return_value = b'{"id":"job-123"}'
        resp_mock.__enter__.return_value = resp_mock
        urllib_mock.Request.return_value = MagicMock()
        urllib_mock.urlopen.return_value = resp_mock

        result = _load_with_urllib_mock(
            "blender-render-farm/scripts/cancel_render_job.py",
            urllib_mock,
            job_id="job-abc",
            farm="flamenco",
        )

        assert result["success"] is True
        # Check that the Request URL includes /setstatus
        req_call = urllib_mock.Request.call_args
        url = req_call[0][0] if req_call[0] else ""
        assert "/api/v3/jobs/job-abc/setstatus" in url, (
            "Expected POST /api/v3/jobs/job-abc/setstatus but got: {}".format(url)
        )
        assert "/status" not in url.split("/setstatus")[0] if "/setstatus" in url else True, (
            "Must not call deprecated /api/v3/jobs/.../status. Got: {}".format(url)
        )

    def test_cancel_render_job_sends_correct_method(self):
        """The setstatus call must use POST with cancel-requested body."""
        urllib_mock = MagicMock()
        resp_mock = MagicMock()
        resp_mock.read.return_value = b'{"id":"job-xyz"}'
        resp_mock.__enter__.return_value = resp_mock
        urllib_mock.Request.return_value = MagicMock()
        urllib_mock.urlopen.return_value = resp_mock

        _load_with_urllib_mock(
            "blender-render-farm/scripts/cancel_render_job.py",
            urllib_mock,
            job_id="job-xyz",
            farm="flamenco",
        )

        # Verify POST method
        req_call = urllib_mock.Request.call_args
        kwargs = req_call[1] if len(req_call) > 1 else {}
        method = kwargs.get("method", "GET")
        assert method == "POST", "Cancel must use POST, got: {}".format(method)

        # Verify payload includes cancel-requested
        data = kwargs.get("data")
        if data is not None:
            body = json.loads(data.decode("utf-8") if isinstance(data, bytes) else data)
            assert body.get("status") == "cancel-requested", "Expected cancel-requested status, got: {}".format(body)


# ---------------------------------------------------------------------------
# Single-frame validation
# ---------------------------------------------------------------------------


class TestSingleFrameValidation:
    """validate_scene_for_farm must accept single-frame renders."""

    def test_single_frame_is_valid(self):
        """Frame start == end (single frame) should NOT produce an issue."""
        bpy = make_mock_bpy()
        bpy.data.filepath = "/tmp/scene.blend"
        bpy.context.scene.camera = MagicMock()
        bpy.context.scene.frame_start = 47
        bpy.context.scene.frame_end = 47
        bpy.context.scene.render.filepath = "/tmp/output/"
        bpy.data.images = []
        bpy.data.libraries = []

        result = load_and_call("blender-render-farm/scripts/validate_scene_for_farm.py", bpy)

        assert result["success"] is True
        assert result["context"]["valid"] is True, "Single-frame render (47-47) should be valid, got issues: {}".format(
            result["context"].get("issues", [])
        )
        assert len(result["context"]["issues"]) == 0

    def test_multi_frame_is_valid(self):
        """Frame start < end should still be valid."""
        bpy = make_mock_bpy()
        bpy.data.filepath = "/tmp/scene.blend"
        bpy.context.scene.camera = MagicMock()
        bpy.context.scene.frame_start = 1
        bpy.context.scene.frame_end = 250
        bpy.context.scene.render.filepath = "/tmp/output/"
        bpy.data.images = []
        bpy.data.libraries = []

        result = load_and_call("blender-render-farm/scripts/validate_scene_for_farm.py", bpy)

        assert result["success"] is True
        assert result["context"]["valid"] is True

    def test_end_before_start_is_invalid(self):
        """Frame end < start should still be flagged as invalid."""
        bpy = make_mock_bpy()
        bpy.data.filepath = "/tmp/scene.blend"
        bpy.context.scene.camera = MagicMock()
        bpy.context.scene.frame_start = 250
        bpy.context.scene.frame_end = 1
        bpy.context.scene.render.filepath = "/tmp/output/"
        bpy.data.images = []
        bpy.data.libraries = []

        result = load_and_call("blender-render-farm/scripts/validate_scene_for_farm.py", bpy)

        assert result["context"]["valid"] is False
        assert any("frame range invalid" in i.lower() for i in result["context"]["issues"])


# ---------------------------------------------------------------------------
# Priority passthrough
# ---------------------------------------------------------------------------


class TestPriorityPassthrough:
    """submit_render_job must pass priority through to Flamenco, not hardcode."""

    def test_flamenco_submit_respects_priority_parameter(self):
        """The priority kwarg should appear in the Flamenco job payload."""
        bpy = make_mock_bpy()
        bpy.data.filepath = "/tmp/scene.blend"
        bpy.context.scene.frame_start = 1
        bpy.context.scene.frame_end = 100
        bpy.context.scene.render.filepath = "/tmp/output/"
        bpy.context.scene.render.engine = "CYCLES"

        urllib_mock = MagicMock()
        resp_mock = MagicMock()
        resp_mock.read.return_value = b'{"id":"flam-job-99"}'
        resp_mock.__enter__.return_value = resp_mock
        urllib_mock.Request.return_value = MagicMock()
        urllib_mock.urlopen.return_value = resp_mock

        # Submit with a non-default priority
        result = _load_with_urllib_mock(
            "blender-render-farm/scripts/submit_render_job.py",
            urllib_mock,
            bpy_mock=bpy,
            farm="flamenco",
            priority=77,
        )

        assert result["success"] is True

        # Extract the payload sent to Flamenco
        req_call = urllib_mock.Request.call_args
        kwargs = req_call[1] if len(req_call) > 1 else {}
        data = kwargs.get("data")
        assert data is not None, "Expected Request with data payload"
        body = json.loads(data.decode("utf-8") if isinstance(data, bytes) else data)

        assert body.get("priority") == 77, "Expected priority=77 in payload, got priority={}".format(
            body.get("priority")
        )
        assert body["priority"] != 50, "Priority must not be hardcoded to 50; should use the passed kwarg"

    def test_flamenco_submit_includes_add_path_components(self):
        """The Flamenco payload must include add_path_components setting."""
        bpy = make_mock_bpy()
        bpy.data.filepath = "/tmp/scene.blend"
        bpy.context.scene.frame_start = 1
        bpy.context.scene.frame_end = 10
        bpy.context.scene.render.filepath = "/tmp/output/"
        bpy.context.scene.render.engine = "CYCLES"

        urllib_mock = MagicMock()
        resp_mock = MagicMock()
        resp_mock.read.return_value = b'{"id":"flam-job-add"}'
        resp_mock.__enter__.return_value = resp_mock
        urllib_mock.Request.return_value = MagicMock()
        urllib_mock.urlopen.return_value = resp_mock

        _load_with_urllib_mock(
            "blender-render-farm/scripts/submit_render_job.py",
            urllib_mock,
            bpy_mock=bpy,
            farm="flamenco",
        )

        req_call = urllib_mock.Request.call_args
        kwargs = req_call[1] if len(req_call) > 1 else {}
        data = kwargs.get("data")
        body = json.loads(data.decode("utf-8") if isinstance(data, bytes) else data)

        settings = body.get("settings", {})
        assert "add_path_components" in settings, "Flamenco Simple Blender Render requires add_path_components setting"
        assert settings["add_path_components"] is True

    def test_flamenco_payload_includes_required_settings(self):
        """Verify all Flamenco Simple Blender Render required settings."""
        bpy = make_mock_bpy()
        bpy.data.filepath = "/tmp/scene.blend"
        bpy.context.scene.frame_start = 1
        bpy.context.scene.frame_end = 24
        bpy.context.scene.render.filepath = "/tmp/output/"
        bpy.context.scene.render.engine = "BLENDER_EEVEE"

        urllib_mock = MagicMock()
        resp_mock = MagicMock()
        resp_mock.read.return_value = b'{"id":"flam-job-req"}'
        resp_mock.__enter__.return_value = resp_mock
        urllib_mock.Request.return_value = MagicMock()
        urllib_mock.urlopen.return_value = resp_mock

        _load_with_urllib_mock(
            "blender-render-farm/scripts/submit_render_job.py",
            urllib_mock,
            bpy_mock=bpy,
            farm="flamenco",
            chunk_size=5,
        )

        req_call = urllib_mock.Request.call_args
        kwargs = req_call[1] if len(req_call) > 1 else {}
        data = kwargs.get("data")
        body = json.loads(data.decode("utf-8") if isinstance(data, bytes) else data)

        assert body.get("type") == "blender-render"
        settings = body["settings"]
        assert settings.get("blender_cmd") == "blender"
        assert settings.get("filepath") == "/tmp/scene.blend"
        assert settings.get("frames") == "1-24"
        assert settings.get("chunk_size") == 5
        assert settings.get("render_engine") == "BLENDER_EEVEE"
        assert settings.get("render_output") == "/tmp/output/"
        assert settings.get("add_path_components") is True


# ---------------------------------------------------------------------------
# Cooperative cancel checkpoints
# ---------------------------------------------------------------------------


def _make_dcc_mcp_core_mock(check_cancelled: MagicMock | None = None) -> MagicMock:
    """Build a dcc_mcp_core mock with real skill helpers and a mock checkpoint.

    Scripts import ``from dcc_mcp_core.skill import ...`` and
    ``from dcc_mcp_core import check_dcc_cancelled``.  We wire up the real
    skill module but replace the cancellation entry-point.
    """
    import dcc_mcp_core.skill as real_skill  # noqa: PLC0415

    mock = MagicMock()
    mock.check_dcc_cancelled = check_cancelled or MagicMock()
    mock.skill = real_skill
    # Forward common attributes that scripts may import at module level
    mock.skill_entry = real_skill.skill_entry
    mock.skill_error = real_skill.skill_error
    mock.skill_success = real_skill.skill_success
    mock.skill_exception = real_skill.skill_exception
    return mock


class TestCooperativeCancelCheckpoint:
    """Scripts must call check_dcc_cancelled() at appropriate checkpoints."""

    def test_validate_scene_calls_check_dcc_cancelled(self):
        """validate_scene_for_farm should call check_dcc_cancelled()."""
        bpy = make_mock_bpy()
        bpy.data.filepath = "/tmp/scene.blend"
        bpy.context.scene.camera = MagicMock()
        bpy.context.scene.frame_start = 1
        bpy.context.scene.frame_end = 250
        bpy.context.scene.render.filepath = "/tmp/output/"
        bpy.data.images = []
        bpy.data.libraries = []

        mock_check = MagicMock()
        dcc_mock = _make_dcc_mcp_core_mock(mock_check)

        _LOAD_COUNTER[0] += 1
        fpath = SKILLS_ROOT / "blender-render-farm/scripts/validate_scene_for_farm.py"
        mod_name = f"skill_rf_v_{_LOAD_COUNTER[0]}"
        import importlib.util

        spec = importlib.util.spec_from_file_location(mod_name, str(fpath))
        mod = importlib.util.module_from_spec(spec)
        with patch.dict(
            "sys.modules",
            {
                "bpy": bpy,
                "mathutils": MagicMock(),
                "dcc_mcp_core": dcc_mock,
            },
        ):
            spec.loader.exec_module(mod)
            result = mod.main()

        assert result["success"] is True
        assert mock_check.call_count >= 1, (
            "validate_scene_for_farm must call check_dcc_cancelled() at checkpoints, got {} calls".format(
                mock_check.call_count
            )
        )

    def test_submit_flamenco_calls_check_dcc_cancelled(self):
        """submit_render_job Flamenco path should call check_dcc_cancelled()."""
        bpy = make_mock_bpy()
        bpy.data.filepath = "/tmp/scene.blend"
        bpy.context.scene.frame_start = 1
        bpy.context.scene.frame_end = 10
        bpy.context.scene.render.filepath = "/tmp/output/"
        bpy.context.scene.render.engine = "CYCLES"

        urllib_mock = MagicMock()
        resp_mock = MagicMock()
        resp_mock.read.return_value = b'{"id":"job-ck"}'
        resp_mock.__enter__.return_value = resp_mock
        urllib_mock.Request.return_value = MagicMock()
        urllib_mock.urlopen.return_value = resp_mock

        mock_check = MagicMock()
        dcc_mock = _make_dcc_mcp_core_mock(mock_check)

        result = _load_with_urllib_mock(
            "blender-render-farm/scripts/submit_render_job.py",
            urllib_mock,
            bpy_mock=bpy,
            dcc_mcp_core_mock=dcc_mock,
            farm="flamenco",
        )

        assert result["success"] is True
        assert mock_check.call_count >= 1, "submit_render_job Flamenco path must call check_dcc_cancelled()"

    def test_get_render_job_status_calls_check_dcc_cancelled(self):
        """get_render_job_status Flamenco path should call check_dcc_cancelled()."""
        urllib_mock = MagicMock()
        resp_mock = MagicMock()
        resp_mock.read.return_value = (
            b'{"id":"job-1","status":"completed","task_summary":{"completed":10,"total":10,"failed":0},"name":"Test"}'
        )
        resp_mock.__enter__.return_value = resp_mock
        urllib_mock.Request.return_value = MagicMock()
        urllib_mock.urlopen.return_value = resp_mock

        mock_check = MagicMock()
        dcc_mock = _make_dcc_mcp_core_mock(mock_check)

        result = _load_with_urllib_mock(
            "blender-render-farm/scripts/get_render_job_status.py",
            urllib_mock,
            dcc_mcp_core_mock=dcc_mock,
            job_id="job-1",
            farm="flamenco",
        )

        assert result["success"] is True
        assert mock_check.call_count >= 1, "get_render_job_status must call check_dcc_cancelled()"

    def test_list_render_jobs_calls_check_dcc_cancelled(self):
        """list_render_jobs Flamenco path should call check_dcc_cancelled()."""
        urllib_mock = MagicMock()
        resp_mock = MagicMock()
        resp_mock.read.return_value = b'{"jobs":[{"id":"job-1","name":"Test"}]}'
        resp_mock.__enter__.return_value = resp_mock
        urllib_mock.Request.return_value = MagicMock()
        urllib_mock.urlopen.return_value = resp_mock

        mock_check = MagicMock()
        dcc_mock = _make_dcc_mcp_core_mock(mock_check)

        result = _load_with_urllib_mock(
            "blender-render-farm/scripts/list_render_jobs.py",
            urllib_mock,
            dcc_mcp_core_mock=dcc_mock,
            farm="flamenco",
        )

        assert result["success"] is True
        assert mock_check.call_count >= 1, "list_render_jobs must call check_dcc_cancelled()"

    def test_cancel_render_job_calls_check_dcc_cancelled(self):
        """cancel_render_job Flamenco path should call check_dcc_cancelled()."""
        urllib_mock = MagicMock()
        resp_mock = MagicMock()
        resp_mock.read.return_value = b'{"id":"job-c"}'
        resp_mock.__enter__.return_value = resp_mock
        urllib_mock.Request.return_value = MagicMock()
        urllib_mock.urlopen.return_value = resp_mock

        mock_check = MagicMock()
        dcc_mock = _make_dcc_mcp_core_mock(mock_check)

        result = _load_with_urllib_mock(
            "blender-render-farm/scripts/cancel_render_job.py",
            urllib_mock,
            dcc_mcp_core_mock=dcc_mock,
            job_id="job-c",
            farm="flamenco",
        )

        assert result["success"] is True
        assert mock_check.call_count >= 1, "cancel_render_job Flamenco path must call check_dcc_cancelled()"

    def test_render_farm_status_calls_check_dcc_cancelled(self):
        """render_farm_status Flamenco path should call check_dcc_cancelled()."""
        urllib_mock = MagicMock()
        resp_mock = MagicMock()
        resp_mock.read.return_value = b'{"version":"3.5","name":"Manager"}'
        resp_mock.__enter__.return_value = resp_mock
        urllib_mock.Request.return_value = MagicMock()
        urllib_mock.urlopen.return_value = resp_mock

        mock_check = MagicMock()
        dcc_mock = _make_dcc_mcp_core_mock(mock_check)

        result = _load_with_urllib_mock(
            "blender-render-farm/scripts/render_farm_status.py",
            urllib_mock,
            dcc_mcp_core_mock=dcc_mock,
        )

        assert result["success"] is True
        assert mock_check.call_count >= 1, (
            "render_farm_status Flamenco path must call check_dcc_cancelled(). Got {} calls".format(
                mock_check.call_count
            )
        )
