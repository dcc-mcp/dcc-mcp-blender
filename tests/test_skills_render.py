"""Unit tests for blender-render skill scripts (bpy mocked)."""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import yaml

from tests.conftest import load_and_call, make_mock_bpy


def test_render_tools_publish_ci_safe_input_contracts():
    tools_path = Path("src/dcc_mcp_blender/skills/blender-render/tools.yaml")
    tools = {tool["name"]: tool for tool in yaml.safe_load(tools_path.read_text(encoding="utf-8"))["tools"]}

    render_scene = tools["render_scene"]["input_schema"]
    assert render_scene["properties"]["write_still"]["default"] is True
    assert render_scene["additionalProperties"] is False

    render_job = tools["start_render_job"]["input_schema"]
    assert render_job["properties"]["output_format"] == {
        "type": "string",
        "enum": ["OPEN_EXR_MULTILAYER", "PNG"],
        "default": "OPEN_EXR_MULTILAYER",
        "description": "Background render output format. PNG produces display-ready frames; multilayer EXR preserves render passes.",
    }

    settings = tools["set_render_settings"]["input_schema"]["properties"]
    assert "CYCLES" in settings["engine"]["enum"]
    assert settings["resolution_percentage"]["maximum"] == 100
    assert settings["fps"]["minimum"] == 1
    assert settings["samples"]["minimum"] == 1

    capture = tools["capture_viewport"]["input_schema"]
    assert capture["required"] == ["filepath"]
    assert capture["properties"]["resolution_x"]["minimum"] == 1

    assert tools["get_render_info"]["input_schema"]["properties"] == {}


class TestGetRenderInfo:
    def test_returns_engine_and_resolution(self):
        bpy = make_mock_bpy()
        bpy.context.scene.render.engine = "CYCLES"
        bpy.context.scene.render.resolution_x = 1920
        bpy.context.scene.render.resolution_y = 1080
        bpy.context.scene.camera = None

        result = load_and_call("blender-render/scripts/get_render_info.py", bpy)
        assert result["success"] is True
        ctx = result["context"]
        assert ctx["engine"] == "CYCLES"
        assert ctx["resolution_x"] == 1920
        assert ctx["resolution_y"] == 1080

    def test_returns_cycles_samples(self):
        bpy = make_mock_bpy()
        bpy.context.scene.render.engine = "CYCLES"
        bpy.context.scene.cycles = MagicMock()
        bpy.context.scene.cycles.samples = 128
        bpy.context.scene.cycles.device = "GPU"

        result = load_and_call("blender-render/scripts/get_render_info.py", bpy)
        assert result["success"] is True
        assert result["context"]["cycles_samples"] == 128


class TestSetRenderSettings:
    def test_set_engine(self):
        bpy = make_mock_bpy()
        result = load_and_call("blender-render/scripts/set_render_settings.py", bpy, engine="CYCLES")
        assert result["success"] is True
        assert bpy.context.scene.render.engine == "CYCLES"

    def test_set_resolution(self):
        bpy = make_mock_bpy()
        result = load_and_call(
            "blender-render/scripts/set_render_settings.py",
            bpy,
            resolution_x=2560,
            resolution_y=1440,
        )
        assert result["success"] is True
        assert bpy.context.scene.render.resolution_x == 2560
        assert bpy.context.scene.render.resolution_y == 1440

    def test_set_fps(self):
        bpy = make_mock_bpy()
        result = load_and_call("blender-render/scripts/set_render_settings.py", bpy, fps=30)
        assert result["success"] is True
        assert result["context"]["fps"] == 30

    def test_invalid_engine_returns_error(self):
        bpy = make_mock_bpy()
        result = load_and_call("blender-render/scripts/set_render_settings.py", bpy, engine="INVALID_ENGINE")
        assert result["success"] is False

    def test_set_output_path(self):
        bpy = make_mock_bpy()
        result = load_and_call("blender-render/scripts/set_render_settings.py", bpy, output_path="/tmp/render/")
        assert result["success"] is True
        assert bpy.context.scene.render.filepath == "/tmp/render/"

    def test_set_samples_cycles(self):
        bpy = make_mock_bpy()
        bpy.context.scene.render.engine = "CYCLES"
        bpy.context.scene.cycles = MagicMock()
        result = load_and_call("blender-render/scripts/set_render_settings.py", bpy, samples=256)
        assert result["success"] is True
        assert bpy.context.scene.cycles.samples == 256


class TestRenderScene:
    def test_render_calls_bpy_ops(self):
        bpy = make_mock_bpy()
        bpy.context.scene.render.filepath = "/tmp/output.png"

        result = load_and_call("blender-render/scripts/render_scene.py", bpy)
        assert result["success"] is True
        bpy.ops.render.render.assert_called_once()

    def test_render_with_output_path(self):
        bpy = make_mock_bpy()
        bpy.context.scene.render.filepath = ""

        result = load_and_call("blender-render/scripts/render_scene.py", bpy, output_path="/custom/output.png")
        assert result["success"] is True
        assert bpy.context.scene.render.filepath == "/custom/output.png"


class TestCaptureViewport:
    @staticmethod
    def _with_view3d(bpy, scene=None):
        region = SimpleNamespace(type="WINDOW")
        space = SimpleNamespace(type="VIEW_3D")
        area = SimpleNamespace(
            type="VIEW_3D",
            regions=[region],
            spaces=SimpleNamespace(active=space),
        )
        screen = SimpleNamespace(areas=[area])
        window = SimpleNamespace(screen=screen, scene=scene or bpy.context.scene)
        bpy.context.window = window
        bpy.context.screen = screen
        bpy.context.temp_override = MagicMock(return_value=nullcontext())
        return window, screen, area, region, space

    def test_capture_viewport_renders_only_view3d_at_requested_size_and_restores_settings(self, tmp_path):
        bpy = make_mock_bpy()
        window, screen, area, region, space = self._with_view3d(bpy)
        output = tmp_path / "viewport.png"
        bpy.context.scene.render.filepath = "//original.png"
        bpy.context.scene.render.resolution_x = 1920
        bpy.context.scene.render.resolution_y = 1080
        bpy.context.scene.render.resolution_percentage = 75
        bpy.context.scene.render.image_settings.file_format = "JPEG"
        bpy.context.scene.render.use_file_extension = True
        rendered_settings = []

        def render_viewport(**_kwargs):
            render = bpy.context.scene.render
            rendered_settings.append(
                (
                    render.filepath,
                    render.resolution_x,
                    render.resolution_y,
                    render.resolution_percentage,
                    render.image_settings.file_format,
                    render.use_file_extension,
                )
            )
            Path(render.filepath).write_bytes(b"viewport render")
            return {"FINISHED"}

        bpy.ops.render.opengl.side_effect = render_viewport
        image = SimpleNamespace(size=(800, 600))
        bpy.data.images.load.return_value = image

        result = load_and_call(
            "blender-render/scripts/capture_viewport.py",
            bpy,
            filepath=str(output),
            resolution_x=800,
            resolution_y=600,
        )

        assert result["success"] is True
        assert result["context"]["filepath"] == str(output)
        assert result["context"]["method"] == "viewport_opengl"
        assert result["context"]["width"] == 800
        assert result["context"]["height"] == 600
        bpy.ops.screen.screenshot.assert_not_called()
        bpy.context.temp_override.assert_called_once_with(
            window=window,
            screen=screen,
            area=area,
            region=region,
            space_data=space,
            scene=bpy.context.scene,
        )
        bpy.ops.render.opengl.assert_called_once_with(write_still=True, view_context=True)
        assert len(rendered_settings) == 1
        staged_path, *settings = rendered_settings[0]
        assert Path(staged_path).parent == output.parent
        assert Path(staged_path).name.startswith(".viewport-")
        assert settings == [800, 600, 100, "PNG", False]
        bpy.data.images.load.assert_called_once_with(staged_path, check_existing=False)
        bpy.data.images.remove.assert_called_once_with(image)
        assert output.read_bytes() == b"viewport render"
        assert not Path(staged_path).exists()
        assert bpy.context.scene.render.filepath == "//original.png"
        assert bpy.context.scene.render.resolution_x == 1920
        assert bpy.context.scene.render.resolution_y == 1080
        assert bpy.context.scene.render.resolution_percentage == 75
        assert bpy.context.scene.render.image_settings.file_format == "JPEG"
        assert bpy.context.scene.render.use_file_extension is True

    def test_capture_viewport_fails_closed_without_view3d(self, tmp_path):
        bpy = make_mock_bpy()
        bpy.context.window = SimpleNamespace(screen=SimpleNamespace(areas=[]))
        bpy.context.screen = bpy.context.window.screen

        result = load_and_call(
            "blender-render/scripts/capture_viewport.py",
            bpy,
            filepath=str(tmp_path / "viewport.png"),
        )

        assert result["success"] is False
        assert "VIEW_3D" in result["message"]
        bpy.ops.screen.screenshot.assert_not_called()
        bpy.ops.render.opengl.assert_not_called()

    def test_capture_viewport_modal_override_failure_does_not_fall_back_to_screen(self, tmp_path):
        bpy = make_mock_bpy()
        self._with_view3d(bpy)
        bpy.context.temp_override.side_effect = RuntimeError("modal context is unavailable")

        result = load_and_call(
            "blender-render/scripts/capture_viewport.py",
            bpy,
            filepath=str(tmp_path / "viewport.png"),
        )

        assert result["success"] is False
        assert "modal context is unavailable" in result["message"]
        bpy.ops.screen.screenshot.assert_not_called()

    def test_capture_viewport_fails_closed_when_context_override_api_is_unavailable(self, tmp_path):
        bpy = make_mock_bpy()
        self._with_view3d(bpy)
        bpy.context.temp_override = None

        result = load_and_call(
            "blender-render/scripts/capture_viewport.py",
            bpy,
            filepath=str(tmp_path / "viewport.png"),
        )

        assert result["success"] is False
        assert "context override unavailable" in result["message"]
        bpy.ops.render.opengl.assert_not_called()
        bpy.ops.screen.screenshot.assert_not_called()

    def test_capture_viewport_restores_settings_when_viewport_render_raises(self, tmp_path):
        bpy = make_mock_bpy()
        self._with_view3d(bpy)
        output = tmp_path / "viewport.png"
        output.write_bytes(b"existing viewport")
        render = bpy.context.scene.render
        render.filepath = "//original.exr"
        render.resolution_x = 2048
        render.resolution_y = 1024
        render.resolution_percentage = 50
        render.image_settings.file_format = "OPEN_EXR"
        bpy.ops.render.opengl.side_effect = RuntimeError("viewport render failed")

        result = load_and_call(
            "blender-render/scripts/capture_viewport.py",
            bpy,
            filepath=str(output),
            resolution_x=640,
            resolution_y=360,
        )

        assert result["success"] is False
        assert render.filepath == "//original.exr"
        assert render.resolution_x == 2048
        assert render.resolution_y == 1024
        assert render.resolution_percentage == 50
        assert render.image_settings.file_format == "OPEN_EXR"
        assert output.read_bytes() == b"existing viewport"
        assert list(tmp_path.glob(".viewport-*.png")) == []
        bpy.ops.screen.screenshot.assert_not_called()

    def test_capture_viewport_rejects_wrong_output_dimensions(self, tmp_path):
        bpy = make_mock_bpy()
        self._with_view3d(bpy)
        output = tmp_path / "viewport.png"

        def render_viewport(**_kwargs):
            Path(bpy.context.scene.render.filepath).write_bytes(b"viewport render")
            return {"FINISHED"}

        bpy.ops.render.opengl.side_effect = render_viewport
        image = SimpleNamespace(size=(1024, 768))
        bpy.data.images.load.return_value = image

        result = load_and_call(
            "blender-render/scripts/capture_viewport.py",
            bpy,
            filepath=str(output),
            resolution_x=800,
            resolution_y=600,
        )

        assert result["success"] is False
        assert "1024x768" in result["message"]
        assert "800x600" in result["message"]
        bpy.data.images.remove.assert_called_once_with(image)
        bpy.ops.screen.screenshot.assert_not_called()
        assert not output.exists()
        assert list(tmp_path.glob(".viewport-*.png")) == []

    def test_capture_viewport_uses_window_manager_view3d_when_current_window_is_missing(self, tmp_path):
        bpy = make_mock_bpy()
        window, screen, area, region, space = self._with_view3d(bpy)
        bpy.context.window = None
        bpy.context.window_manager.windows = [window]
        output = tmp_path / "viewport.png"

        def render_viewport(**_kwargs):
            Path(bpy.context.scene.render.filepath).write_bytes(b"viewport render")
            return {"FINISHED"}

        bpy.ops.render.opengl.side_effect = render_viewport
        image = SimpleNamespace(size=(1920, 1080))
        bpy.data.images.load.return_value = image

        result = load_and_call(
            "blender-render/scripts/capture_viewport.py",
            bpy,
            filepath=str(output),
        )

        assert result["success"] is True
        bpy.context.temp_override.assert_called_once_with(
            window=window,
            screen=screen,
            area=area,
            region=region,
            space_data=space,
            scene=window.scene,
        )

    def test_capture_viewport_rejects_same_size_stale_destination_when_write_is_missing(self, tmp_path):
        bpy = make_mock_bpy()
        self._with_view3d(bpy)
        output = tmp_path / "viewport.png"
        output.write_bytes(b"stale image")
        bpy.ops.render.opengl.return_value = {"FINISHED"}
        bpy.data.images.load.return_value = SimpleNamespace(size=(800, 600))

        result = load_and_call(
            "blender-render/scripts/capture_viewport.py",
            bpy,
            filepath=str(output),
            resolution_x=800,
            resolution_y=600,
        )

        assert result["success"] is False
        assert output.read_bytes() == b"stale image"
        bpy.data.images.load.assert_not_called()
        assert list(tmp_path.glob(".viewport-*.png")) == []

    def test_capture_viewport_configures_and_restores_the_overridden_window_scene(self, tmp_path):
        bpy = make_mock_bpy()
        scene_a = bpy.context.scene
        scene_a.render.filepath = "//scene-a.png"
        scene_a.render.resolution_x = 320
        scene_a.render.resolution_y = 200
        scene_b = MagicMock()
        scene_b.render.filepath = "//scene-b.exr"
        scene_b.render.resolution_x = 2048
        scene_b.render.resolution_y = 1024
        scene_b.render.resolution_percentage = 50
        scene_b.render.image_settings.file_format = "OPEN_EXR"
        scene_b.render.use_file_extension = True

        bpy.context.window = SimpleNamespace(screen=SimpleNamespace(areas=[]), scene=scene_a)
        window, screen, area, region, space = self._with_view3d(bpy, scene=scene_b)
        bpy.context.window = SimpleNamespace(screen=SimpleNamespace(areas=[]), scene=scene_a)
        bpy.context.window_manager.windows = [window]
        output = tmp_path / "viewport.png"
        observed = []

        @contextmanager
        def switch_scene(**_override):
            previous = bpy.context.scene
            bpy.context.scene = scene_b
            try:
                yield
            finally:
                bpy.context.scene = previous

        bpy.context.temp_override = MagicMock(side_effect=switch_scene)

        def render_viewport(**_kwargs):
            render = bpy.context.scene.render
            observed.append((bpy.context.scene, render.resolution_x, render.resolution_y, render.filepath))
            Path(render.filepath).write_bytes(b"viewport render")
            return {"FINISHED"}

        bpy.ops.render.opengl.side_effect = render_viewport
        bpy.data.images.load.return_value = SimpleNamespace(size=(640, 360))

        result = load_and_call(
            "blender-render/scripts/capture_viewport.py",
            bpy,
            filepath=str(output),
            resolution_x=640,
            resolution_y=360,
        )

        assert result["success"] is True
        assert observed[0][0] is scene_b
        assert observed[0][1:3] == (640, 360)
        assert Path(observed[0][3]).name.startswith(".viewport-")
        assert scene_a.render.filepath == "//scene-a.png"
        assert scene_a.render.resolution_x == 320
        assert scene_a.render.resolution_y == 200
        assert scene_b.render.filepath == "//scene-b.exr"
        assert scene_b.render.resolution_x == 2048
        assert scene_b.render.resolution_y == 1024
        assert scene_b.render.resolution_percentage == 50
        assert scene_b.render.image_settings.file_format == "OPEN_EXR"
        assert scene_b.render.use_file_extension is True
        bpy.context.temp_override.assert_called_once_with(
            window=window,
            screen=screen,
            area=area,
            region=region,
            space_data=space,
            scene=scene_b,
        )

    def test_capture_viewport_rejects_cancelled_operator_without_using_stale_output(self, tmp_path):
        bpy = make_mock_bpy()
        self._with_view3d(bpy)
        output = tmp_path / "viewport.png"
        output.write_bytes(b"stale image")
        bpy.ops.render.opengl.return_value = {"CANCELLED"}
        bpy.data.images.load.return_value = SimpleNamespace(size=(1920, 1080))

        result = load_and_call(
            "blender-render/scripts/capture_viewport.py",
            bpy,
            filepath=str(output),
        )

        assert result["success"] is False
        assert "did not finish" in result["message"]
        bpy.data.images.load.assert_not_called()
        bpy.ops.screen.screenshot.assert_not_called()

    def test_capture_viewport_requires_filepath(self):
        bpy = make_mock_bpy()

        result = load_and_call("blender-render/scripts/capture_viewport.py", bpy, filepath="")

        assert result["success"] is False
