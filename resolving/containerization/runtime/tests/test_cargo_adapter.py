from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from resolving.containerization.runtime import cargo_adapter


def write_text(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")


class CargoAdapterTests(unittest.TestCase):
    def test_build_capabilities_advertises_both_metadata_modes(self) -> None:
        capabilities = cargo_adapter.build_capabilities()

        self.assertEqual(capabilities["metadata_modes"], ["indexed", "online"])
        self.assertIn("indexed-local-registry", capabilities["features"])
        self.assertIn("online-network", capabilities["features"])

    def test_indexed_mode_uses_local_registry_subdir_and_runtime_config(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargo-adapter-indexed-") as temp_dir:
            temp_root = Path(temp_dir)
            runtime_root = temp_root / "runtime"
            shared_root = temp_root / "shared"
            cargo_home = shared_root / "cargo-home"
            local_registry_dir = shared_root / "local-registry"
            runtime_config_dir = runtime_root / ".cargo"
            runtime_config_path = runtime_config_dir / "config.toml"
            runtime_config_templates = {
                "indexed": runtime_config_dir / "config.indexed.toml",
                "online": runtime_config_dir / "config.online.toml",
            }

            write_text(runtime_config_templates["indexed"], "indexed-config\n")
            write_text(runtime_config_templates["online"], "online-config\n")
            write_text(local_registry_dir / "index" / "config.json", '{"dl":"https://example.invalid"}\n')
            cargo_home.mkdir(parents=True, exist_ok=True)

            with ExitStack() as stack:
                stack.enter_context(patch.object(cargo_adapter, "METADATA_MODE", "indexed"))
                stack.enter_context(patch.object(cargo_adapter, "RUNTIME_ROOT", runtime_root))
                stack.enter_context(patch.object(cargo_adapter, "SHARED_DATA_ROOT", shared_root))
                stack.enter_context(patch.object(cargo_adapter, "CARGO_HOME", cargo_home))
                stack.enter_context(patch.object(cargo_adapter, "LOCAL_REGISTRY_DIR", local_registry_dir))
                stack.enter_context(patch.object(cargo_adapter, "RUNTIME_CONFIG_DIR", runtime_config_dir))
                stack.enter_context(patch.object(cargo_adapter, "RUNTIME_CONFIG_PATH", runtime_config_path))
                stack.enter_context(
                    patch.object(cargo_adapter, "RUNTIME_CONFIG_TEMPLATE_PATHS", runtime_config_templates)
                )

                binding = cargo_adapter.ensure_runtime_registry_ready()

            self.assertEqual(binding["metadata_mode"], "indexed")
            self.assertEqual(binding["source"], "preprocess-local-registry")
            self.assertEqual(Path(binding["active_path"]), local_registry_dir.resolve())
            self.assertEqual(Path(binding["config_path"]), (local_registry_dir / "index" / "config.json").resolve())
            self.assertEqual(runtime_config_path.read_text(encoding="utf-8"), "indexed-config\n")

    def test_online_mode_uses_index_clone_subdir_and_runtime_config(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargo-adapter-online-") as temp_dir:
            temp_root = Path(temp_dir)
            runtime_root = temp_root / "runtime"
            shared_root = temp_root / "shared"
            cargo_home = shared_root / "cargo-home"
            local_registry_dir = shared_root / "local-registry"
            runtime_config_dir = runtime_root / ".cargo"
            runtime_config_path = runtime_config_dir / "config.toml"
            runtime_config_templates = {
                "indexed": runtime_config_dir / "config.indexed.toml",
                "online": runtime_config_dir / "config.online.toml",
            }

            write_text(runtime_config_templates["indexed"], "indexed-config\n")
            write_text(runtime_config_templates["online"], "online-config\n")
            write_text(local_registry_dir / "index" / "config.json", '{"dl":"https://example.invalid"}\n')

            with ExitStack() as stack:
                stack.enter_context(patch.object(cargo_adapter, "METADATA_MODE", "online"))
                stack.enter_context(patch.object(cargo_adapter, "RUNTIME_ROOT", runtime_root))
                stack.enter_context(patch.object(cargo_adapter, "SHARED_DATA_ROOT", shared_root))
                stack.enter_context(patch.object(cargo_adapter, "CARGO_HOME", cargo_home))
                stack.enter_context(patch.object(cargo_adapter, "LOCAL_REGISTRY_DIR", local_registry_dir))
                stack.enter_context(patch.object(cargo_adapter, "RUNTIME_CONFIG_DIR", runtime_config_dir))
                stack.enter_context(patch.object(cargo_adapter, "RUNTIME_CONFIG_PATH", runtime_config_path))
                stack.enter_context(
                    patch.object(cargo_adapter, "RUNTIME_CONFIG_TEMPLATE_PATHS", runtime_config_templates)
                )

                binding = cargo_adapter.ensure_runtime_registry_ready()

            self.assertEqual(binding["metadata_mode"], "online")
            self.assertEqual(binding["source"], "network-crates-io")
            self.assertEqual(Path(binding["active_path"]), cargo_home.resolve())
            self.assertIsNone(binding["config_path"])
            self.assertIsNone(binding["config_sha256"])
            self.assertEqual(runtime_config_path.read_text(encoding="utf-8"), "online-config\n")


if __name__ == "__main__":
    unittest.main()
