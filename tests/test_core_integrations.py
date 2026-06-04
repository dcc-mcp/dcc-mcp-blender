"""Tests for the Blender adapter's dcc-mcp-core interface integrations.

Mirrors the Maya adapter's coverage for the newly wired integrations:

* three-state runtime readiness binder,
* compact capability manifest builder + MCP tool,
* project-tools integration with a fake scene resolver,
* MCP resource binder (``scene://current``),
* opt-in semantic skill-recall augmentation,
* Blender context snapshot provider.

None of these require a live Blender — every Blender access is faked or
guarded so the suite runs in plain Python / ``mayapy``-style headless mode.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeInner:
    """Fake inner Rust ``McpHttpServer`` exposing registry + handler + resources."""

    def __init__(self) -> None:
        self.registered: Dict[str, dict] = {}
        self.handlers: Dict[str, Any] = {}
        self.registry = MagicMock()
        self.registry.register.side_effect = lambda name, **kw: self.registered.__setitem__(name, kw)
        self._resources = _FakeResourceHandle()

    def register_handler(self, name: str, handler: Any) -> None:
        self.handlers[name] = handler

    def resources(self) -> "_FakeResourceHandle":
        return self._resources

    def set_readiness_probe(self, probe: Any) -> None:
        self.readiness_probe = probe


class _FakeResourceHandle:
    def __init__(self) -> None:
        self.producers: Dict[str, Any] = {}
        self.scene_payloads: List[dict] = []

    def register_producer(self, scheme: str, producer: Any) -> None:
        self.producers[scheme] = producer

    def set_scene(self, payload: dict) -> None:
        self.scene_payloads.append(payload)


class _FakeServer:
    """Minimal wrapper standing in for BlenderMcpServer."""

    def __init__(self, *, dispatcher: Any = None) -> None:
        self._server = _FakeInner()
        self._blender_dispatcher = dispatcher
        self._config = MagicMock()
        self._config.scene = "/tmp/demo.blend"
        self._config.dcc_version = "4.0.0"
        self.instance_id = "abcd1234"


# ---------------------------------------------------------------------------
# Readiness binder
# ---------------------------------------------------------------------------


class TestReadinessBinder:
    def test_no_dispatcher_marks_dcc_ready_immediately(self):
        from dcc_mcp_blender._readiness import ReadinessBinder

        server = _FakeServer(dispatcher=None)
        binder = ReadinessBinder()
        assert binder.bind(server) is True
        report = binder.report()
        assert report["dispatcher"] is True
        assert report["dcc"] is True
        assert binder.published_to_server is True
        # Probe was published to the inner server.
        assert server._server.readiness_probe is binder.probe

    def test_async_dispatcher_schedules_then_marks_ready(self):
        from dcc_mcp_blender._readiness import ReadinessBinder

        captured = {}

        class _AsyncDispatcher:
            def submit_async_callable(self, *, request_id, task, affinity, timeout_ms, on_complete):
                captured["request_id"] = request_id
                captured["affinity"] = affinity
                # Simulate the main-thread no-op completing.
                on_complete(task())

        server = _FakeServer(dispatcher=_AsyncDispatcher())
        binder = ReadinessBinder()
        assert binder.bind(server) is True
        assert captured["affinity"] == "main"
        report = binder.report()
        assert report["dcc"] is True
        assert report.get("main_thread_executor") is True, (
            "main_thread_executor should be True after dcc probe completes"
        )

    def test_main_thread_executor_deferred_until_probe_completes(self):
        """main_thread_executor stays False until the dcc probe callback fires."""
        from dcc_mcp_blender._readiness import ReadinessBinder

        pending_on_complete = {}

        class _DeferredAsyncDispatcher:
            def submit_async_callable(self, *, request_id, task, affinity, timeout_ms, on_complete):
                # Capture the callback but DON'T call it yet — simulates the
                # real Blender timer pump where the callback runs later.
                pending_on_complete["callback"] = on_complete
                pending_on_complete["task"] = task

        server = _FakeServer(dispatcher=_DeferredAsyncDispatcher())
        binder = ReadinessBinder()
        assert binder.bind(server) is True

        # Before the probe completes, main_thread_executor should be False
        # (the pump has not been verified yet).
        report_before = binder.report()
        assert report_before.get("main_thread_executor") is False, (
            "main_thread_executor should be False before dcc probe completes — "
            "the pump has not drained a callback yet"
        )
        assert report_before["dcc"] is False

        # Now simulate the Blender timer pump draining the probe callback.
        assert "callback" in pending_on_complete
        pending_on_complete["callback"](pending_on_complete["task"]())

        # After the probe completes, both bits should be green.
        report_after = binder.report()
        assert report_after["dcc"] is True
        assert report_after.get("main_thread_executor") is True, (
            "main_thread_executor should be True after the dcc probe callback fires"
        )

    def test_bind_idempotent(self):
        from dcc_mcp_blender._readiness import ReadinessBinder

        server = _FakeServer()
        binder = ReadinessBinder()
        binder.bind(server)
        # Second bind on the same server is a no-op.
        assert binder.bind(server) is True

    def test_resolve_timeout_env(self, monkeypatch):
        from dcc_mcp_blender._readiness import resolve_readiness_timeout_secs

        monkeypatch.setenv("DCC_MCP_BLENDER_READINESS_TIMEOUT_SECS", "45")
        assert resolve_readiness_timeout_secs() == 45
        monkeypatch.setenv("DCC_MCP_BLENDER_READINESS_TIMEOUT_SECS", "-3")
        assert resolve_readiness_timeout_secs() is None
        monkeypatch.delenv("DCC_MCP_BLENDER_READINESS_TIMEOUT_SECS", raising=False)
        assert resolve_readiness_timeout_secs(12) == 12


# ---------------------------------------------------------------------------
# Capability manifest
# ---------------------------------------------------------------------------


class TestCapabilityManifest:
    def _builder(self, *, loaded: bool = False):
        from dcc_mcp_blender._capability_manifest import BlenderCapabilityManifestBuilder

        skills = [
            {
                "name": "blender-scene",
                "tags": ["scene"],
                "tools": [
                    {
                        "name": "get_scene_info",
                        "description": "Return scene hierarchy",
                        "input_schema": {"type": "object"},
                    }
                ],
            }
        ]
        actions: List[dict] = []
        if loaded:
            actions = [
                {
                    "name": "blender_scene__get_scene_info",
                    "skill": "blender-scene",
                    "description": "Return scene hierarchy",
                    "inputSchema": {"type": "object"},
                }
            ]
        return BlenderCapabilityManifestBuilder(
            skill_lister=lambda: skills,
            action_lister=lambda: actions,
            is_loaded=lambda name: loaded,
        )

    def test_unloaded_skill_yields_load_hint_record(self):
        records = self._builder(loaded=False).build()
        assert len(records) == 1
        rec = records[0]
        assert rec.backend_tool == "blender_scene__get_scene_info"
        assert rec.requires_load_skill is True
        assert rec.load_hint == {"tool": "load_skill", "arguments": {"skill_name": "blender-scene"}}
        assert rec.loaded is False

    def test_loaded_action_record(self):
        records = self._builder(loaded=True).build()
        assert len(records) == 1
        rec = records[0]
        assert rec.loaded is True
        assert rec.has_schema is True
        assert rec.tool_slug.startswith("blender.instance.")

    def test_build_manifest_payload_totals(self):
        from dcc_mcp_blender._capability_manifest import build_manifest_payload

        records = self._builder(loaded=False).build()
        payload = build_manifest_payload(records, dcc_name="blender", scene="/tmp/x.blend")
        assert payload["dcc_type"] == "blender"
        assert payload["totals"]["actions"] == 1
        assert payload["totals"]["unloaded_actions"] == 1
        assert payload["metadata"]["scene"] == "/tmp/x.blend"

    def test_register_capability_mcp_tool(self):
        from dcc_mcp_blender._capability_manifest import register_capability_mcp_tool

        server = _FakeServer()
        builder = self._builder(loaded=False)
        assert register_capability_mcp_tool(server, builder=builder) is True
        assert "dcc_capability_manifest" in server._server.registered
        handler = server._server.handlers["dcc_capability_manifest"]
        result = handler({"loaded_only": False})
        assert result["success"] is True
        assert result["context"]["dcc_type"] == "blender"

    def test_register_returns_false_without_inner(self):
        from dcc_mcp_blender._capability_manifest import register_capability_mcp_tool

        class _NoInner:
            _server = None

        assert register_capability_mcp_tool(_NoInner(), builder=self._builder()) is False


# ---------------------------------------------------------------------------
# Project tools
# ---------------------------------------------------------------------------


class TestProjectTools:
    def test_scene_resolver_returns_none_outside_blender(self):
        from dcc_mcp_blender._project_tools import BlenderSceneResolver

        # No bpy importable in the test interpreter.
        assert BlenderSceneResolver().current_scene() is None

    def test_resolve_enabled_env_opt_out(self, monkeypatch):
        from dcc_mcp_blender._project_tools import resolve_enabled

        monkeypatch.setenv("DCC_MCP_BLENDER_PROJECT_TOOLS", "0")
        assert resolve_enabled() is False
        monkeypatch.setenv("DCC_MCP_BLENDER_PROJECT_TOOLS", "1")
        assert resolve_enabled() is True
        monkeypatch.delenv("DCC_MCP_BLENDER_PROJECT_TOOLS", raising=False)
        assert resolve_enabled() is True

    def test_bind_with_fake_resolver(self, monkeypatch):
        import dcc_mcp_core

        from dcc_mcp_blender._project_tools import BlenderSceneResolver, ProjectToolsIntegration

        calls = {}

        def _fake_register(inner, *, dcc_name, project=None):
            calls["inner"] = inner
            calls["dcc_name"] = dcc_name
            calls["project"] = project

        monkeypatch.setattr(dcc_mcp_core, "register_project_tools", _fake_register)

        class _Resolver(BlenderSceneResolver):
            def current_scene(self) -> Optional[str]:
                return "/projects/shot/shot.blend"

        made = {}

        def _factory(scene: str):
            made["scene"] = scene
            proj = MagicMock()
            proj.state.scene_path = scene
            return proj

        server = _FakeServer()
        integration = ProjectToolsIntegration(scene_resolver=_Resolver())
        assert integration.bind(server, project_factory=_factory) is True
        assert calls["dcc_name"] == "blender"
        # The resolver path is normalised through ``pathlib.Path`` before
        # reaching the factory, so compare the resolved form.
        assert os.path.basename(made["scene"]) == "shot.blend"
        assert integration.registered is True

    def test_attach_to_server_disabled(self, monkeypatch):
        from dcc_mcp_blender._project_tools import attach_to_server

        monkeypatch.setenv("DCC_MCP_BLENDER_PROJECT_TOOLS", "0")
        assert attach_to_server(_FakeServer()) is None


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


class TestResources:
    def test_bind_registers_producer_and_publishes_scene(self):
        from dcc_mcp_blender._resources import SCHEME_BLENDER_DATA, BlenderResourceBinder

        server = _FakeServer()
        snapshots = [{"dcc": "blender", "scene": "/tmp/x.blend"}]
        binder = BlenderResourceBinder(snapshot_provider=lambda: snapshots[0])
        assert binder.bind(server) is True
        assert SCHEME_BLENDER_DATA in binder.registered_producers
        assert binder.scene_publish_count == 1
        assert server._server.resources().scene_payloads == snapshots

    def test_install_scene_events_uses_injected_installer(self):
        from dcc_mcp_blender._resources import BlenderResourceBinder

        recorded = {}

        def _installer(callback, handlers):
            recorded["handlers"] = handlers
            return ["h1", "h2"]

        server = _FakeServer()
        binder = BlenderResourceBinder(snapshot_provider=lambda: {}, event_installer=_installer)
        binder.bind(server)
        handles = binder.install_scene_events()
        assert handles == ["h1", "h2"]
        assert "save_post" in recorded["handlers"]
        # Idempotent.
        assert binder.install_scene_events() == ["h1", "h2"]
        binder.unbind()

    def test_install_resources_env_opt_out(self, monkeypatch):
        from dcc_mcp_blender._resources import install_resources

        monkeypatch.setenv("DCC_MCP_BLENDER_RESOURCES", "0")
        assert install_resources(_FakeServer(), snapshot_provider=lambda: {}) is None

    def test_blender_data_producer_without_bpy(self):
        from dcc_mcp_blender._resources import _blender_data_producer

        result = _blender_data_producer("blender-data://current")
        assert result["mimeType"] == "application/json"
        assert "blender_unavailable" in result["text"]


# ---------------------------------------------------------------------------
# Semantic index
# ---------------------------------------------------------------------------


class TestSemanticIndex:
    def test_resolve_enabled_default_off(self, monkeypatch):
        from dcc_mcp_blender._semantic_index import resolve_semantic_index_enabled

        monkeypatch.delenv("DCC_MCP_BLENDER_SEMANTIC_INDEX", raising=False)
        assert resolve_semantic_index_enabled() is False
        monkeypatch.setenv("DCC_MCP_BLENDER_SEMANTIC_INDEX", "1")
        assert resolve_semantic_index_enabled() is True

    def test_build_returns_none_when_disabled(self, monkeypatch):
        from dcc_mcp_blender._semantic_index import build_semantic_index

        monkeypatch.delenv("DCC_MCP_BLENDER_SEMANTIC_INDEX", raising=False)
        assert build_semantic_index() is None

    def test_augment_appends_recall_preserving_base(self):
        from dcc_mcp_blender._semantic_index import BlenderSemanticIndex

        class _Hit:
            def __init__(self, skill_id):
                self.skill_id = skill_id

        class _FakeFusion:
            def clear(self):
                pass

            def index(self, docs):
                self._docs = docs

            def search(self, query, k=16):
                return [_Hit("blender-render")]

        index = BlenderSemanticIndex(_FakeFusion(), "hashed")
        base = [{"name": "blender-scene"}]
        all_summaries = [{"name": "blender-scene"}, {"name": "blender-render", "description": "render"}]
        result = index.augment(base, "rendering", all_summaries)
        names = [r["name"] for r in result]
        assert names[0] == "blender-scene"  # base order preserved
        assert "blender-render" in names  # recall appended

    def test_augment_empty_query_returns_base(self):
        from dcc_mcp_blender._semantic_index import BlenderSemanticIndex

        index = BlenderSemanticIndex(MagicMock(), "hashed")
        base = [{"name": "blender-scene"}]
        assert index.augment(base, "", [{"name": "blender-scene"}]) == base

    def test_morphology_recall_real_fusion_appends_relevant_skills(self, monkeypatch):
        """Integration: real HashedEmbedder + RRF fusion for morphology queries.

        Verifies that queries like "importing usd files" and "rendering a
        preview" hit the correct skills even when the base result set does not
        contain them.
        """
        monkeypatch.delenv("DCC_MCP_BLENDER_SEMANTIC_INDEX", raising=False)
        monkeypatch.setenv("DCC_MCP_BLENDER_SEMANTIC_INDEX", "1")
        monkeypatch.delenv("DCC_MCP_BLENDER_SEMANTIC_EMBEDDER", raising=False)
        # Use hashed embedder (zero-dependency, always available)
        monkeypatch.setenv("DCC_MCP_BLENDER_SEMANTIC_EMBEDDER", "hashed")

        from dcc_mcp_blender._semantic_index import BlenderSemanticIndex, build_semantic_index

        index = build_semantic_index()
        assert index is not None, "semantic index should be built when env is enabled"

        # Simulate a realistic skill catalog with descriptions
        all_summaries: list[dict] = [
            {
                "name": "blender-interchange",
                "description": "Import FBX/OBJ/USD files and export GLTF, USD, Alembic",
                "tags": ["interchange", "import", "export", "usd"],
            },
            {
                "name": "blender-render",
                "description": "Render stills, viewport captures, and configure render settings",
                "tags": ["render", "output", "viewport"],
            },
            {
                "name": "blender-scene",
                "description": "Inspect and manage Blender scene lifecycle",
                "tags": ["scene", "hierarchy"],
            },
            {
                "name": "blender-materials",
                "description": "Create, assign, edit, list, and delete materials",
                "tags": ["material", "lookdev"],
            },
            {
                "name": "blender-animation",
                "description": "Manage keyframes, frame ranges, and animation baking",
                "tags": ["animation", "keyframe", "baking"],
            },
        ]

        # Query 1: morphology variant — "importing usd files" should hit interchange
        base = [{"name": "blender-scene"}]  # base only has scene
        result = index.augment(base, "importing usd files", all_summaries)
        names = [r["name"] for r in result]
        assert names[0] == "blender-scene", "base ordering must be preserved"
        assert "blender-interchange" in names, (
            f"Morphology query 'importing usd files' should recall interchange; got {names}"
        )

        # Query 2: morphology variant — "rendering a preview" should hit render
        base2 = [{"name": "blender-scene"}]
        result2 = index.augment(base2, "rendering a preview", all_summaries)
        names2 = [r["name"] for r in result2]
        assert "blender-render" in names2, (
            f"Morphology query 'rendering a preview' should recall render; got {names2}"
        )

        # Query 3: "create material for this object" should hit materials
        base3: list[dict] = []
        result3 = index.augment(base3, "create material for this object", all_summaries)
        names3 = [r["name"] for r in result3]
        assert "blender-materials" in names3, (
            f"Morphology query should recall materials; got {names3}"
        )

    def test_morphology_recall_default_off_no_side_effect(self, monkeypatch):
        """When SEMANTIC_INDEX is not set, build_semantic_index returns None."""
        monkeypatch.delenv("DCC_MCP_BLENDER_SEMANTIC_INDEX", raising=False)
        from dcc_mcp_blender._semantic_index import build_semantic_index

        assert build_semantic_index() is None, "should be None when env is not set"

    def test_semantic_augment_deduplicates_existing_skills(self):
        """Skills already in base should not be duplicated by recall."""
        from dcc_mcp_blender._semantic_index import BlenderSemanticIndex

        class _Hit:
            def __init__(self, skill_id):
                self.skill_id = skill_id

        class _FakeFusion:
            def clear(self):
                pass

            def index(self, docs):
                pass

            def search(self, query, k=16):
                return [_Hit("blender-scene"), _Hit("blender-render")]

        index = BlenderSemanticIndex(_FakeFusion(), "hashed")
        base = [{"name": "blender-scene"}]  # already in base
        all_summaries = [
            {"name": "blender-scene", "description": "scene"},
            {"name": "blender-render", "description": "render"},
        ]
        result = index.augment(base, "something", all_summaries)
        names = [r["name"] for r in result]
        # blender-scene should appear once (already in base, not duplicated)
        assert names == ["blender-scene", "blender-render"], f"Expected dedup; got {names}"


# ---------------------------------------------------------------------------
# Context snapshot
# ---------------------------------------------------------------------------


class TestContextSnapshot:
    def test_unavailable_outside_blender(self):
        from dcc_mcp_blender.context_snapshot import BlenderContextSnapshotProvider

        provider = BlenderContextSnapshotProvider(bpy_provider=lambda: None)
        snap = provider.collect()
        assert snap["dcc"] == "blender"
        assert snap["available"] is False

    def test_collect_with_fake_bpy(self):
        from dcc_mcp_blender.context_snapshot import BlenderContextSnapshotProvider, collect_gateway_metadata

        fake = MagicMock()
        fake.data.filepath = "/projects/shot/shot.blend"
        fake.data.is_dirty = True
        fake.app.version_string = "4.0.0"
        scene = MagicMock()
        scene.name = "Scene"
        scene.frame_current = 7
        scene.frame_start = 1
        scene.frame_end = 250
        fake.context.scene = scene
        obj = MagicMock()
        obj.name = "Cube"
        fake.context.selected_objects = [obj]

        provider = BlenderContextSnapshotProvider(bpy_provider=lambda: fake)
        snap = provider.collect()
        assert snap["available"] is True
        assert snap["scene"] == "/projects/shot/shot.blend"
        assert snap["scene_modified"] is True
        assert snap["version"] == "4.0.0"
        assert snap["scene_name"] == "Scene"
        assert snap["frame"] == 7
        assert snap["frame_range"] == [1, 250]
        assert snap["selection"] == ["Cube"]
        assert "shot.blend" in snap["display_name"]

        meta = collect_gateway_metadata(provider)
        assert meta["scene"] == "/projects/shot/shot.blend"
        assert meta["documents"] == ["/projects/shot/shot.blend"]
        assert meta["version"] == "4.0.0"


# ---------------------------------------------------------------------------
# Server wiring smoke
# ---------------------------------------------------------------------------


class TestServerWiring:
    def test_server_exposes_readiness_and_manifest(self):
        from dcc_mcp_blender.server import BlenderMcpServer

        server = BlenderMcpServer(port=0)
        report = server.readiness_report()
        assert "dcc" in report
        manifest = server.build_capability_manifest()
        assert manifest["dcc_type"] == "blender"
        assert "capabilities" in manifest

    def test_public_exports(self):
        import dcc_mcp_blender as b

        for symbol in (
            "ReadinessBinder",
            "BlenderCapabilityManifestBuilder",
            "ProjectToolsIntegration",
            "BlenderResourceBinder",
            "BlenderSemanticIndex",
            "BlenderContextSnapshotProvider",
            "attach_project_tools",
            "install_readiness",
        ):
            assert hasattr(b, symbol), symbol


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
