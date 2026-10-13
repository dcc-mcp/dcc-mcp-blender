"""Keep the documented no-gateway fallback usable with released Core builds."""

import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch


def _fallback_options(registry_dir):
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    section = readme.split("### Gateway compatibility", 1)[1].split("To keep a private local gateway", 1)[0]
    code = re.search(r"```python\n(.*?)```", section, re.DOTALL).group(1)
    adapter = Mock()
    # Execute the actual snippet, intercepting server lifecycle calls so no
    # listener starts. A predictable fresh directory keeps the test isolated.
    with patch.dict("sys.modules", {"dcc_mcp_blender": adapter}):
        with patch("tempfile.mkdtemp", return_value=registry_dir) as private_registry, patch("builtins.print"):
            exec(compile(code, "README.md gateway fallback", "exec"), {})
    private_registry.assert_called_once_with(prefix="dcc-mcp-blender-private-")
    options = adapter.start_server.call_args.kwargs
    assert adapter.mock_calls == [call.stop_server(), call.start_server(**options)]
    return options


class TestReadmeGatewayCompatibility(unittest.TestCase):
    def test_released_core_fallback_disables_gateway_without_remote_options(self):
        # Resolve the actual public options without starting any listener.
        from dcc_mcp_blender.server import BlenderServerOptions

        with tempfile.TemporaryDirectory() as registry_dir:
            options = _fallback_options(registry_dir)
            self.assertEqual(options["port"], 0)
            self.assertEqual(options["gateway_port"], 0)
            self.assertIs(options["enable_gateway_failover"], False)
            self.assertEqual(options["registry_dir"], registry_dir)
            self.assertFalse(any(name.startswith("gateway_remote_") for name in options))
            with patch.dict(os.environ, {}, clear=True):
                core_options = BlenderServerOptions(**options).to_core_options()
            self.assertEqual(core_options.port, 0)
            self.assertEqual(core_options.gateway.port, 0)
            self.assertIs(core_options.gateway.enable_failover, False)
            self.assertEqual(core_options.gateway.registry_dir, registry_dir)

    def test_private_registry_overrides_shared_environment_in_native_config(self):
        from dcc_mcp_core._server.config import build_mcp_http_config

        from dcc_mcp_blender.server import BlenderServerOptions

        with tempfile.TemporaryDirectory() as registry_dir:
            options = _fallback_options(registry_dir)
            with patch.dict(
                os.environ, {"DCC_MCP_REGISTRY_DIR": "/shared/registry", "DCC_MCP_GATEWAY_PORT": "9765"}, clear=True
            ):
                core_options = BlenderServerOptions(**options).to_core_options()
                config = build_mcp_http_config(core_options, package_version="test", version_provider=lambda: "test")
            self.assertEqual(config.port, 0)
            self.assertEqual(config.host, "127.0.0.1")
            self.assertEqual(config.gateway_port, 0)
            self.assertEqual(config.registry_dir, registry_dir)


if __name__ == "__main__":
    unittest.main()
