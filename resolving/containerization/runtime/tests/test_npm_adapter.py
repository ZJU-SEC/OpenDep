from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import unittest
from unittest.mock import patch

from support import PROJECT_ROOT

from resolving.containerization.runtime import npm_adapter


@contextmanager
def fake_shim(**_: object):
    yield type("ShimHandle", (), {"base_url": "http://127.0.0.1:18080"})()


class NpmAdapterTests(unittest.TestCase):
    def test_build_capabilities_advertises_indexed_mode(self) -> None:
        capabilities = npm_adapter.build_capabilities()

        self.assertIn("indexed-postgres", capabilities["features"])
        self.assertEqual(capabilities["metadata_modes"], ["online", "indexed"])

    def test_run_backend_requires_dsn_in_indexed_mode(self) -> None:
        with patch.object(npm_adapter, "METADATA_MODE", "indexed"), patch.object(
            npm_adapter, "INDEX_DSN", ""
        ), patch.object(npm_adapter, "BACKEND_BINARY", Path(__file__)):
            result, raw, error = npm_adapter.run_backend("left-pad", "1.3.0", 1000)

        self.assertIsNone(result)
        self.assertIsNone(raw)
        self.assertEqual(error["code"], "BACKEND_MISCONFIGURED")
        self.assertIn("NPM_INDEX_DSN", error["message"])

    def test_run_backend_uses_shim_in_indexed_mode(self) -> None:
        with patch.object(npm_adapter, "METADATA_MODE", "indexed"), patch.object(
            npm_adapter, "INDEX_DSN", "postgresql://example"
        ), patch.object(npm_adapter, "INDEX_TABLE", "npm_metadata"), patch.object(
            npm_adapter, "INDEX_FALLBACK_TO_ONLINE", True
        ), patch.object(
            npm_adapter, "REGISTRY_BASE_URL", "https://registry.example.test"
        ), patch.object(
            npm_adapter, "BACKEND_BINARY", Path(__file__)
        ), patch.object(
            npm_adapter, "serve_packument_shim", fake_shim
        ), patch.object(
            npm_adapter,
            "_run_backend_process",
            return_value=({"root": {}, "nodes": [], "edges": []}, {"stdout": "", "stderr": "", "exit_code": 0}, None),
        ) as run_backend_process:
            result, raw, error = npm_adapter.run_backend("left-pad", "1.3.0", 1000)

        self.assertIsNone(error)
        self.assertEqual(result, {"root": {}, "nodes": [], "edges": []})
        self.assertEqual(raw["index_table"], "npm_metadata")
        self.assertTrue(raw["index_fallback_to_online"])
        self.assertEqual(raw["shim_base_url"], "http://127.0.0.1:18080")
        self.assertEqual(raw["upstream_registry_base_url"], "https://registry.example.test")
        run_backend_process.assert_called_once_with(
            "left-pad",
            "1.3.0",
            1000,
            registry_base_url="http://127.0.0.1:18080",
        )

    def test_run_backend_uses_configured_registry_in_online_mode(self) -> None:
        with patch.object(npm_adapter, "METADATA_MODE", "online"), patch.object(
            npm_adapter, "REGISTRY_BASE_URL", "https://registry.example.test"
        ), patch.object(
            npm_adapter, "BACKEND_BINARY", Path(__file__)
        ), patch.object(
            npm_adapter,
            "_run_backend_process",
            return_value=(None, None, {"code": "VERSION_NOT_FOUND", "message": "missing", "retryable": False}),
        ) as run_backend_process:
            _, _, error = npm_adapter.run_backend("left-pad", "1.3.0", 1000)

        self.assertEqual(error["code"], "VERSION_NOT_FOUND")
        run_backend_process.assert_called_once_with(
            "left-pad",
            "1.3.0",
            1000,
            registry_base_url="https://registry.example.test",
        )


if __name__ == "__main__":
    unittest.main()
