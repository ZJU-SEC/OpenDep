from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[5]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from resolving.containerization.images.pip.backend import cli
from resolving.containerization.images.pip.backend.metadata_sources.base import MetadataSource
from resolving.containerization.images.pip.backend.models import PackageMetadataRecord, VersionRecord
from resolving.containerization.images.pip.backend.stores.base import IndexStore
from resolving.gateway.contract import validate_response


def _make_wheel(base_dir: Path, name: str, version: str, requires: tuple[str, ...] = ()) -> Path:
    wheel_path = base_dir / f"{name}-{version}-py3-none-any.whl"
    dist_info = f"{name}-{version}.dist-info"
    metadata_lines = [
        "Metadata-Version: 2.1",
        f"Name: {name}",
        f"Version: {version}",
    ]
    for requirement in requires:
        metadata_lines.append(f"Requires-Dist: {requirement}")
    metadata_text = "\n".join(metadata_lines) + "\n\n"
    with zipfile.ZipFile(wheel_path, "w") as archive:
        archive.writestr(f"{dist_info}/METADATA", metadata_text)
        archive.writestr(
            f"{dist_info}/WHEEL",
            "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        archive.writestr(f"{dist_info}/RECORD", "")
    return wheel_path


def _write_project_json(
    index_dir: Path,
    name: str,
    version: str,
    wheel_path: Path,
    *,
    requires_python: str | None = None,
) -> None:
    project_dir = index_dir / name
    version_dir = project_dir / version
    project_dir.mkdir(parents=True, exist_ok=True)
    version_dir.mkdir(parents=True, exist_ok=True)

    info: dict[str, str] = {"name": name}
    if requires_python:
        info["requires_python"] = requires_python

    file_entry = {
        "filename": wheel_path.name,
        "url": wheel_path.as_uri(),
        "packagetype": "bdist_wheel",
        "python_version": "py3",
        "yanked": False,
        "digests": {},
    }
    project_payload = {"info": info, "releases": {version: [file_entry]}}
    release_payload = {"info": info, "urls": [file_entry]}
    (project_dir / "json").write_text(json.dumps(project_payload), encoding="utf-8")
    (version_dir / "json").write_text(json.dumps(release_payload), encoding="utf-8")


class BackendResolveLiveTests(unittest.TestCase):
    def test_backend_resolve_outputs_graph_from_local_file_index(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pip-live-test-") as temp_dir:
            fixture_dir = Path(temp_dir)
            index_dir = fixture_dir / "pypi"

            root_wheel = _make_wheel(fixture_dir, "rootpkg", "1.0.0", ("depone>=2",))
            dep_wheel = _make_wheel(fixture_dir, "depone", "2.1.0")
            _write_project_json(index_dir, "rootpkg", "1.0.0", root_wheel, requires_python=">=3.8")
            _write_project_json(index_dir, "depone", "2.1.0", dep_wheel)

            env = dict(os.environ)
            env["PYTHONPATH"] = os.pathsep.join(
                [str(PROJECT_ROOT), env.get("PYTHONPATH", "")]
            )
            env["PIP_PYPI_JSON_BASE_URL"] = index_dir.as_uri()
            env["PIP_CACHE_DIR"] = str(fixture_dir / "cache")

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "resolving.containerization.images.pip.backend",
                    "resolve",
                    "--name",
                    "rootpkg",
                    "--format",
                    "graph",
                ],
                cwd=PROJECT_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["root"]["id"], "pip:rootpkg@1.0.0")
            self.assertEqual(payload["metrics"]["node_count"], 2)
            self.assertEqual(payload["metrics"]["edge_count"], 1)
            self.assertEqual(payload["semantics"]["metadata_mode"], "live")
            self.assertEqual(payload["edges"][0]["constraint"], "depone>=2")
            self.assertEqual(payload["edges"][0]["type"], "direct")


class IndexCliTests(unittest.TestCase):
    def test_index_command_writes_records_and_reports_summary(self) -> None:
        class FakeSource(MetadataSource):
            mode_name = "live"

            def list_versions(self, project_name: str) -> list[VersionRecord]:
                return [
                    VersionRecord(name="demo", version="2.0.0", source_kind="live-index"),
                    VersionRecord(name="demo", version="1.0.0", source_kind="live-index"),
                ]

            def get_release(self, project_name: str, version: str) -> PackageMetadataRecord | None:
                return None

            def warm(self, project_name: str, version: str) -> PackageMetadataRecord:
                return PackageMetadataRecord(
                    name=project_name,
                    version=version,
                    requires_dist=("dep>=1",) if version == "2.0.0" else (),
                    source_kind="wheel-metadata" if version == "2.0.0" else "sdist-setup.cfg",
                )

            def close(self) -> None:
                return None

        class FakeStore(IndexStore):
            def __init__(self) -> None:
                self.saved: list[tuple[str, str]] = []

            def list_versions(self, project_name: str) -> list[VersionRecord]:
                return []

            def get_release(self, project_name: str, version: str) -> PackageMetadataRecord | None:
                return None

            def put_release(self, record: PackageMetadataRecord) -> None:
                self.saved.append((record.name, record.version))

            def close(self) -> None:
                return None

        source = FakeSource()
        store = FakeStore()
        stdout = io.StringIO()
        with patch.object(cli, "build_metadata_source", return_value=source), patch.object(
            cli, "build_index_store", return_value=store
        ), contextlib.redirect_stdout(stdout):
            exit_code = cli.main(["index", "--name", "demo", "--limit", "2"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["metrics"]["indexed_count"], 2)
        self.assertEqual(payload["metrics"]["failed_count"], 0)
        self.assertEqual(store.saved, [("demo", "2.0.0"), ("demo", "1.0.0")])


class PipAdapterTests(unittest.TestCase):
    def _run_adapter(self, module_name: str, module_source: str, request: dict[str, object]) -> tuple[int, dict[str, object]]:
        with tempfile.TemporaryDirectory(prefix="pip-adapter-test-") as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / f"{module_name}.py").write_text(textwrap.dedent(module_source), encoding="utf-8")

            env = dict(os.environ)
            env["PYTHONPATH"] = os.pathsep.join(
                [str(temp_path), str(PROJECT_ROOT), env.get("PYTHONPATH", "")]
            )
            env["PIP_BACKEND_MODULE"] = module_name

            completed = subprocess.run(
                [sys.executable, "resolving/containerization/runtime/pip_adapter.py"],
                cwd=PROJECT_ROOT,
                env=env,
                input=json.dumps(request),
                capture_output=True,
                text=True,
                check=False,
            )
            return completed.returncode, json.loads(completed.stdout)

    def test_adapter_success_response_validates_against_contract(self) -> None:
        request = {
            "schema_version": "1.0",
            "request_id": "req-success",
            "trace_id": "trace-success",
            "command": "resolve",
            "ecosystem": "pip",
            "package": {"name": "demo", "version": "1.0.0"},
            "options": {"format": "graph", "return_raw": True, "timeout_ms": 1000},
        }
        backend_module = """
            import json

            def main():
                payload = {
                    "root": {"id": "pip:demo@1.0.0", "ecosystem": "pip", "name": "demo", "version": "1.0.0"},
                    "nodes": [
                        {
                            "id": "pip:demo@1.0.0",
                            "ecosystem": "pip",
                            "name": "demo",
                            "version": "1.0.0",
                            "labels": {"scope": "root"},
                            "attributes": {"optional": False, "peer": False, "dev": False}
                        }
                    ],
                    "edges": [],
                    "semantics": {"source": "stub"},
                    "metrics": {"node_count": 1, "edge_count": 0}
                }
                print(json.dumps(payload))
                return 0

            if __name__ == "__main__":
                raise SystemExit(main())
        """

        exit_code, payload = self._run_adapter("stub_success_backend", backend_module, request)
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(validate_response(payload), [])
        self.assertEqual(payload["result"]["root"]["id"], "pip:demo@1.0.0")
        self.assertIsNotNone(payload["raw"])
        self.assertEqual(payload["raw"]["exit_code"], 0)

    def test_adapter_error_response_preserves_structured_backend_error(self) -> None:
        request = {
            "schema_version": "1.0",
            "request_id": "req-error",
            "trace_id": "trace-error",
            "command": "resolve",
            "ecosystem": "pip",
            "package": {"name": "demo"},
            "options": {"format": "graph", "return_raw": True, "timeout_ms": 1000},
        }
        backend_module = """
            import json

            def main():
                print(json.dumps({
                    "status": "error",
                    "code": "DATA_SOURCE_UNAVAILABLE",
                    "message": "stub backend failed",
                    "retryable": True,
                    "backend_error": "StubBackendError"
                }))
                return 1

            if __name__ == "__main__":
                raise SystemExit(main())
        """

        exit_code, payload = self._run_adapter("stub_error_backend", backend_module, request)
        self.assertEqual(exit_code, 1)
        self.assertEqual(validate_response(payload), [])
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "DATA_SOURCE_UNAVAILABLE")
        self.assertTrue(payload["error"]["retryable"])
        self.assertIsNotNone(payload["raw"])

    def test_adapter_health_degrades_instead_of_crashing_for_bad_backend_module(self) -> None:
        request = {
            "schema_version": "1.0",
            "request_id": "req-health-bad-module",
            "trace_id": "trace-health-bad-module",
            "command": "health",
            "ecosystem": "pip",
        }
        backend_module = """
            def main():
                return 0

            if __name__ == "__main__":
                raise SystemExit(main())
        """

        with tempfile.TemporaryDirectory(prefix="pip-adapter-health-") as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "unused_backend.py").write_text(textwrap.dedent(backend_module), encoding="utf-8")

            env = dict(os.environ)
            env["PYTHONPATH"] = os.pathsep.join(
                [str(temp_path), str(PROJECT_ROOT), env.get("PYTHONPATH", "")]
            )
            env["PIP_BACKEND_MODULE"] = "does.not.exist"

            completed = subprocess.run(
                [sys.executable, "resolving/containerization/runtime/pip_adapter.py"],
                cwd=PROJECT_ROOT,
                env=env,
                input=json.dumps(request),
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(validate_response(payload), [])
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["result"]["health"]["state"], "degraded")
        backend_check = next(
            item for item in payload["result"]["health"]["checks"] if item["name"] == "backend_module"
        )
        self.assertEqual(backend_check["status"], "error")


class ContainerConfigTests(unittest.TestCase):
    def test_compose_and_registry_reference_real_pip_backend(self) -> None:
        compose_text = (PROJECT_ROOT / "resolving/containerization/docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn('entrypoint: ["python3", "resolving/containerization/runtime/pip_adapter.py"]', compose_text)
        self.assertNotIn('command: ["python", "resolving/containerization/runtime/default_adapter.py"]', compose_text)
        self.assertIn("pip_cache", compose_text)

        registry = json.loads(
            (PROJECT_ROOT / "resolving/config/resolvers.container.yaml").read_text(encoding="utf-8")
        )
        pip_entry = next(item for item in registry["resolvers"] if item["ecosystem"] == "pip")
        self.assertEqual(pip_entry["mode"], "process")
        self.assertIn("cache", pip_entry["capabilities"]["features"])
        self.assertIn("indexed", pip_entry["capabilities"]["features"])
        self.assertIn("live", pip_entry["capabilities"]["features"])


class BackendDescribeTests(unittest.TestCase):
    def test_backend_describe_matches_completed_task_state(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "resolving.containerization.images.pip.backend", "describe"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["scope"], "active")
        self.assertIn("PIP-T13", payload["implemented_tasks"])
        self.assertIn("PIP-T14", payload["implemented_tasks"])
        self.assertEqual(payload["pending_tasks"], [])


if __name__ == "__main__":
    unittest.main()
