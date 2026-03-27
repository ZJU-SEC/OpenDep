from __future__ import annotations

import argparse
from dataclasses import replace
import json
import subprocess
import sys
import tarfile
import tempfile
import shutil
import unittest
from pathlib import Path
import zipfile


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PIP_ROOT = PROJECT_ROOT / "pre-process" / "pip"
COMMON_UTILS_ROOT = PROJECT_ROOT / "pre-process" / "common" / "utils"
COMMON_DATABASE_ROOT = PROJECT_ROOT / "pre-process" / "common" / "database"

for path in (PROJECT_ROOT, PIP_ROOT, COMMON_UTILS_ROOT, COMMON_DATABASE_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


from adapters.request_adapter import BuildRequestAdapter
from adapters.local_artifact import LocalArtifactAdapter
from adapters.manifest import ManifestAdapter
from jsonl import append_jsonl, read_jsonl
from loaders.postgres_loader import PipMetadataPostgresLoader
from pip_models import AcquiredArtifact, BatchBuildItemResult, BatchBuildSummary, BuildJobSpec, BuildRequest, VersionPlanItem
from pipeline.artifact_fetcher import ArtifactFetcher
from pipeline.batch_runner import PipBatchJobRunner
from pipeline.build_service import PipBuildService
from pipeline.extractor import PipDependencyExtractor
from pipeline.legacy_fallback import LegacyFallbackExtractor
from pipeline.pypi_client import PyPIJsonClient
from pipeline.validation import ExtractionQualityValidator
from pipeline.version_planner import VersionPlanner
from resolving.containerization.images.pip.backend.metadata_sources.indexed import IndexedMetadataSource
from resolving.containerization.images.pip.backend.stores.postgres import PostgresIndexStore


REQUESTS_WHEEL = PROJECT_ROOT / "resolving/containerization/images/pip/.legacy/ModuleGuard/EnvResolver/testfile/requests-2.31.0-py3-none-any.whl"
REQUESTS_SDIST = PROJECT_ROOT / "resolving/containerization/images/pip/.legacy/ModuleGuard/EnvResolver/testfile/requests-2.31.0.tar.gz"
DEEPTCR_SDIST = PROJECT_ROOT / "resolving/containerization/images/pip/.legacy/ModuleGuard/testfile/DeepTCR-1.4.20.tar.gz"


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_minimal_wheel(
    wheel_path: Path,
    *,
    name: str = "requests",
    version: str = "2.31.0",
    requires_dist: tuple[str, ...] = ("urllib3 (<3,>=1.21.1)",),
    requires_python: str = ">=3.8",
) -> Path:
    normalized_name = name.replace("-", "_")
    dist_info = f"{normalized_name}-{version}.dist-info"
    metadata_lines = [
        "Metadata-Version: 2.1",
        f"Name: {name}",
        f"Version: {version}",
        f"Requires-Python: {requires_python}",
    ]
    metadata_lines.extend(f"Requires-Dist: {dependency}" for dependency in requires_dist)

    wheel_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(wheel_path, "w") as archive:
        archive.writestr(f"{dist_info}/METADATA", "\n".join(metadata_lines) + "\n")
        archive.writestr(
            f"{dist_info}/WHEEL",
            "\n".join(
                [
                    "Wheel-Version: 1.0",
                    "Generator: unit-test",
                    "Root-Is-Purelib: true",
                    "Tag: py3-none-any",
                ]
            )
            + "\n",
        )
    return wheel_path


def _build_local_pypi_index(
    temp_path: Path,
    *,
    project_name: str = "requests",
    releases: list[dict[str, object]] | None = None,
) -> str:
    normalized_name = project_name
    releases = releases or [
        {
            "version": "2.31.0",
            "filename": REQUESTS_WHEEL.name,
            "artifact_url": REQUESTS_WHEEL.resolve().as_uri(),
            "yanked": False,
            "digests": {"sha256": "deadbeef"},
        }
    ]

    project_payload = {
        "info": {"name": project_name},
        "releases": {
            item["version"]: [
                {
                    "filename": item["filename"],
                    "url": item["artifact_url"],
                    "packagetype": "bdist_wheel" if str(item["filename"]).endswith(".whl") else "sdist",
                    "python_version": "py3",
                    "requires_python": ">=3.8",
                    "yanked": bool(item.get("yanked", False)),
                    "digests": dict(item.get("digests", {})),
                }
            ]
            for item in releases
        },
    }
    _write_json(temp_path / normalized_name / "json", project_payload)

    for item in releases:
        release_payload = {
            "info": {"name": project_name, "version": item["version"], "requires_python": ">=3.8"},
            "urls": [
                {
                    "filename": item["filename"],
                    "url": item["artifact_url"],
                    "packagetype": "bdist_wheel" if str(item["filename"]).endswith(".whl") else "sdist",
                    "python_version": "py3",
                    "requires_python": ">=3.8",
                    "yanked": bool(item.get("yanked", False)),
                    "digests": dict(item.get("digests", {})),
                }
            ],
        }
        _write_json(temp_path / normalized_name / str(item["version"]) / "json", release_payload)

    return temp_path.resolve().as_uri()


class _MemoryCursor:
    def __init__(self, connection):
        self._connection = connection
        self._results: list[tuple] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def execute(self, query, params=None):
        normalized = " ".join(str(query).split())
        params = params or ()
        self._results = self._connection.execute(normalized, params)

    def fetchone(self):
        return self._results[0] if self._results else None

    def fetchall(self):
        return list(self._results)


class _MemoryIndexedConnection:
    def __init__(self):
        self.calls = []
        self.rows: dict[tuple[str, str], dict[str, object]] = {}
        self.commit_count = 0
        self.rollback_count = 0
        self.closed = False

    def cursor(self):
        return _MemoryCursor(self)

    def execute(self, query: str, params: tuple[object, ...]) -> list[tuple]:
        self.calls.append((query, params))
        if query.startswith("CREATE TABLE") or query.startswith("CREATE UNIQUE INDEX") or query.startswith("CREATE INDEX") or query.startswith("COMMENT ON"):
            return []
        if query.startswith("INSERT INTO"):
            key = (str(params[0]), str(params[1]))
            self.rows[key] = {
                "name": params[0],
                "version": params[1],
                "dependency": params[2],
                "yanked": params[3],
                "metadata": params[4],
                "parsed_type_for_dep": params[5],
                "version_struct": params[6],
            }
            return []
        if query.startswith("SELECT 1 FROM"):
            key = (str(params[0]), str(params[1]))
            return [(1,)] if key in self.rows else []
        if query.startswith("SELECT version FROM"):
            name = str(params[0])
            versions = [(row["version"],) for key, row in self.rows.items() if key[0] == name]
            return versions
        if query.startswith("SELECT name, version, yanked, parsed_type_for_dep FROM"):
            name = str(params[0])
            return [
                (row["name"], row["version"], row["yanked"], row["parsed_type_for_dep"])
                for key, row in self.rows.items()
                if key[0] == name
            ]
        if query.startswith("SELECT name, version, dependency, yanked, metadata, parsed_type_for_dep FROM"):
            key = (str(params[0]), str(params[1]))
            row = self.rows.get(key)
            if row is None:
                return []
            return [
                (
                    row["name"],
                    row["version"],
                    row["dependency"],
                    row["yanked"],
                    row["metadata"],
                    row["parsed_type_for_dep"],
                )
            ]
        raise AssertionError(f"unexpected query: {query}")

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1

    def close(self):
        self.closed = True


class _FakeResolverPostgresStore(PostgresIndexStore):
    def __init__(self, connection, table_name: str = "pip_projects_metadata") -> None:
        self._connection = connection
        self._table_name = table_name
        self._driver_name = "fake"
        self._driver = None

    def _connect(self):
        return self._connection


class LocalArtifactAdapterTests(unittest.TestCase):
    def test_prepare_job_detects_wheel(self) -> None:
        job = LocalArtifactAdapter().prepare_job(str(REQUESTS_WHEEL))
        self.assertEqual(job.artifact_kind, "wheel")
        self.assertEqual(job.project_name, "requests")
        self.assertEqual(job.version, "2.31.0")

    def test_prepare_job_detects_egg(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pip-egg-") as temp_dir:
            artifact = Path(temp_dir) / "demo-1.2.3.egg"
            with zipfile.ZipFile(artifact, "w") as archive:
                archive.writestr("EGG-INFO/PKG-INFO", "Name: demo\nVersion: 1.2.3\n")

            job = LocalArtifactAdapter().prepare_job(str(artifact))

        self.assertEqual(job.artifact_kind, "egg")
        self.assertEqual(job.project_name, "demo")
        self.assertEqual(job.version, "1.2.3")


class ManifestAdapterTests(unittest.TestCase):
    def test_loads_manifest_jobs_from_top_level_jobs_key(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pip-manifest-") as temp_dir:
            temp_path = Path(temp_dir)
            manifest = temp_path / "jobs.json"
            manifest.write_text(
                json.dumps(
                    {
                        "jobs": [
                            {
                                "artifact_path": str(REQUESTS_WHEEL),
                                "name": "requests",
                                "version": "2.31.0",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            jobs = ManifestAdapter().load(str(manifest))

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].artifact_path, str(REQUESTS_WHEEL))
        self.assertEqual(jobs[0].project_name, "requests")
        self.assertEqual(jobs[0].versions, ("2.31.0",))

    def test_loads_package_requests_with_defaults(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pip-manifest-pkg-") as temp_dir:
            temp_path = Path(temp_dir)
            manifest = temp_path / "jobs.json"
            manifest.write_text(
                json.dumps(
                    {
                        "defaults": {
                            "limit": 2,
                            "mirror_dir": "./mirror",
                        },
                        "packages": [
                            {
                                "name": "requests",
                                "versions": ["2.31.0", "2.30.0"],
                                "include_yanked": True,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            jobs = ManifestAdapter().load(str(manifest))

        self.assertEqual(len(jobs), 1)
        self.assertTrue(jobs[0].is_package)
        self.assertEqual(jobs[0].project_name, "requests")
        self.assertEqual(jobs[0].versions, ("2.31.0", "2.30.0"))
        self.assertEqual(jobs[0].limit, 2)
        self.assertTrue(jobs[0].include_yanked)
        self.assertEqual(jobs[0].mirror_dir, str((temp_path / "mirror").resolve()))


class BuildRequestAdapterTests(unittest.TestCase):
    def test_parses_project_specs(self) -> None:
        args = argparse.Namespace(
            artifacts=[],
            projects=["requests", "urllib3==2.2.1"],
            project_file=None,
            name=None,
            version=None,
            limit=3,
            include_yanked=True,
            mirror_dir="/tmp/pypi-mirror",
        )

        requests = BuildRequestAdapter().from_cli_args(args)

        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0].project_name, "requests")
        self.assertEqual(requests[0].versions, ())
        self.assertEqual(requests[0].limit, 3)
        self.assertTrue(requests[0].include_yanked)
        self.assertEqual(requests[1].project_name, "urllib3")
        self.assertEqual(requests[1].versions, ("2.2.1",))

    def test_loads_project_specs_from_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pip-project-file-") as temp_dir:
            project_file = Path(temp_dir) / "packages.txt"
            project_file.write_text(
                "\n".join(
                    [
                        "# pypi packages",
                        "requests",
                        "",
                        "urllib3==2.2.1",
                        "requests",
                    ]
                ),
                encoding="utf-8",
            )

            args = argparse.Namespace(
                artifacts=[],
                projects=[],
                project_file=str(project_file),
                name=None,
                version=None,
                limit=None,
                include_yanked=False,
                mirror_dir=None,
            )

            requests = BuildRequestAdapter().from_cli_args(args)

        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0].project_name, "requests")
        self.assertEqual(requests[1].project_name, "urllib3")
        self.assertEqual(requests[1].versions, ("2.2.1",))


class PipDependencyExtractorTests(unittest.TestCase):
    def test_extracts_requests_wheel_via_resolver_inspector(self) -> None:
        record = PipDependencyExtractor().extract_local_artifact(str(REQUESTS_WHEEL))
        self.assertEqual(record.name, "requests")
        self.assertEqual(record.version, "2.31.0")
        self.assertEqual(record.source_kind, "wheel-metadata")
        self.assertIn("urllib3 (<3,>=1.21.1)", record.requires_dist)
        self.assertEqual(record.extraction_backend, "resolver-inspector")

    def test_extracts_requests_sdist_via_resolver_inspector(self) -> None:
        record = PipDependencyExtractor().extract_local_artifact(str(REQUESTS_SDIST))
        self.assertEqual(record.name, "requests")
        self.assertEqual(record.version, "2.31.0")
        self.assertEqual(record.source_kind, "sdist-setup.py")
        self.assertTrue(any(dep.startswith("urllib3") for dep in record.requires_dist))
        self.assertEqual(record.extraction_backend, "resolver-inspector")

    def test_falls_back_to_legacy_requires_when_needed(self) -> None:
        record = PipDependencyExtractor().extract_local_artifact(str(DEEPTCR_SDIST))
        self.assertEqual(record.name.lower(), "deeptcr")
        self.assertEqual(record.version, "1.4.20")
        self.assertEqual(record.source_kind, "legacy-egg-info-requires")
        self.assertIn("tensorflow==1.15.2", record.requires_dist)
        self.assertEqual(record.extraction_backend, "legacy-fallback")
        self.assertTrue(record.parse_warnings)

    def test_can_disable_legacy_fallback(self) -> None:
        with self.assertRaises(ValueError):
            PipDependencyExtractor().extract_local_artifact(
                str(DEEPTCR_SDIST),
                allow_legacy_fallback=False,
            )

    def test_extracts_egg_requires_with_markers_via_legacy_fallback(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pip-egg-fallback-") as temp_dir:
            artifact = Path(temp_dir) / "demo-1.0.0.egg"
            with zipfile.ZipFile(artifact, "w") as archive:
                archive.writestr(
                    "EGG-INFO/requires.txt",
                    "\n".join(
                        [
                            "urllib3>=2",
                            "[security]",
                            "pyopenssl>=23",
                            "[:python_version < '3.12']",
                            "typing-extensions>=4",
                            "[docs:python_version >= '3.11']",
                            "sphinx>=7",
                        ]
                    ),
                )

            record = PipDependencyExtractor().extract_local_artifact(str(artifact))

        self.assertEqual(record.name, "demo")
        self.assertEqual(record.version, "1.0.0")
        self.assertEqual(record.source_kind, "legacy-egg-info-requires")
        self.assertIn("urllib3>=2", record.requires_dist)
        self.assertIn("pyopenssl>=23 ; extra == 'security'", record.requires_dist)
        self.assertIn("typing-extensions>=4 ; python_version < '3.12'", record.requires_dist)
        self.assertIn("sphinx>=7 ; extra == 'docs' and python_version >= '3.11'", record.requires_dist)
        self.assertEqual(record.extraction_backend, "legacy-fallback")


class LegacyFallbackCompatibilityTests(unittest.TestCase):
    def test_fallback_can_parse_setup_cfg(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pip-setupcfg-fallback-") as temp_dir:
            artifact = Path(temp_dir) / "demo-0.4.0.tar.gz"
            package_root = "demo-0.4.0"
            setup_cfg = "\n".join(
                [
                    "[options]",
                    "install_requires =",
                    "    requests>=2",
                    "",
                    "[options.extras_require]",
                    "tests =",
                    "    pytest>=8",
                ]
            )
            with tarfile.open(artifact, "w:gz") as archive:
                cfg_path = Path(temp_dir) / "setup.cfg"
                cfg_path.write_text(setup_cfg, encoding="utf-8")
                archive.add(cfg_path, arcname=f"{package_root}/setup.cfg")

            job = LocalArtifactAdapter().prepare_job(str(artifact))
            record = LegacyFallbackExtractor().extract(job, primary_error=ValueError("primary failed"))

        self.assertEqual(record.source_kind, "legacy-setup.cfg")
        self.assertIn("requests>=2", record.requires_dist)
        self.assertIn("pytest>=8 ; extra == 'tests'", record.requires_dist)
        self.assertTrue(record.parse_warnings)

    def test_fallback_can_parse_pyproject_toml(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pip-pyproject-fallback-") as temp_dir:
            artifact = Path(temp_dir) / "demo-0.5.0.tar.gz"
            package_root = "demo-0.5.0"
            pyproject = "\n".join(
                [
                    "[project]",
                    'dependencies = ["requests>=2"]',
                    "",
                    "[project.optional-dependencies]",
                    'gpu = ["torch>=2"]',
                ]
            )
            with tarfile.open(artifact, "w:gz") as archive:
                pyproject_path = Path(temp_dir) / "pyproject.toml"
                pyproject_path.write_text(pyproject, encoding="utf-8")
                archive.add(pyproject_path, arcname=f"{package_root}/pyproject.toml")

            job = LocalArtifactAdapter().prepare_job(str(artifact))
            record = LegacyFallbackExtractor().extract(job, primary_error=ValueError("primary failed"))

        self.assertEqual(record.source_kind, "legacy-pyproject.toml")
        self.assertIn("requests>=2", record.requires_dist)
        self.assertIn("torch>=2 ; extra == 'gpu'", record.requires_dist)


class ExtractCliTests(unittest.TestCase):
    def test_cli_outputs_json(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(PIP_ROOT / "extract.py"), str(REQUESTS_WHEEL)],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["name"], "requests")
        self.assertEqual(payload["source_kind"], "wheel-metadata")


class ValidationTests(unittest.TestCase):
    def test_validator_marks_parse_warnings_as_partial(self) -> None:
        record = PipDependencyExtractor().extract_local_artifact(str(DEEPTCR_SDIST))
        validated = ExtractionQualityValidator().validate(record)
        self.assertEqual(validated.status, "partial")
        self.assertTrue(validated.ok)
        self.assertTrue(validated.warnings)

    def test_failure_log_writes_jsonl(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pip-failure-log-") as temp_dir:
            log_path = Path(temp_dir) / "failures.jsonl"
            append_jsonl(log_path, {"status": "error", "artifact": "demo.whl"})
            payloads = read_jsonl(log_path)
        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0]["artifact"], "demo.whl")


class LoaderTests(unittest.TestCase):
    def test_loader_ensures_schema_and_upserts_record(self) -> None:
        class FakeCursor:
            def __init__(self, calls):
                self.calls = calls

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return None

            def execute(self, query, params=None):
                self.calls.append((query, params))

        class FakeConnection:
            def __init__(self):
                self.calls = []
                self.commit_count = 0
                self.closed = False

            def cursor(self):
                return FakeCursor(self.calls)

            def commit(self):
                self.commit_count += 1

            def close(self):
                self.closed = True

        connection = FakeConnection()
        loader = PipMetadataPostgresLoader(connection=connection)
        loader.ensure_schema()
        record = PipDependencyExtractor().extract_local_artifact(str(REQUESTS_WHEEL))
        validated = ExtractionQualityValidator().validate(record)
        self.assertTrue(validated.ok)
        loader.upsert_record(validated.record)
        loader.close()

        self.assertEqual(connection.commit_count, 2)
        self.assertIn("CREATE TABLE IF NOT EXISTS public.pip_projects_metadata", connection.calls[0][0])
        upsert_query, upsert_params = connection.calls[1]
        self.assertIn("ON CONFLICT (name, version) DO UPDATE", upsert_query)
        self.assertEqual(upsert_params[0], "requests")
        self.assertEqual(upsert_params[1], "2.31.0")
        self.assertTrue(connection.closed)

    def test_loader_has_release_and_list_versions(self) -> None:
        connection = _MemoryIndexedConnection()
        loader = PipMetadataPostgresLoader(connection=connection)
        record = PipDependencyExtractor().extract_local_artifact(str(REQUESTS_WHEEL))
        validated = ExtractionQualityValidator().validate(record)

        self.assertFalse(loader.has_release("requests", "2.31.0"))
        loader.upsert_record(validated.record)
        self.assertTrue(loader.has_release("requests", "2.31.0"))
        self.assertEqual(loader.list_versions("requests"), ("2.31.0",))


class ResolverIndexedIntegrationTests(unittest.TestCase):
    def test_preprocess_loader_output_is_consumable_by_resolver_indexed_store(self) -> None:
        connection = _MemoryIndexedConnection()
        loader = PipMetadataPostgresLoader(connection=connection)
        record = PipDependencyExtractor().extract_local_artifact(str(REQUESTS_WHEEL))
        validated = ExtractionQualityValidator().validate(record)
        enriched = replace(
            validated.record,
            artifact_url="https://files.pythonhosted.org/example/requests-2.31.0.whl",
            artifact_hash="sha256:abc123",
        )
        loader.upsert_record(enriched)

        store = _FakeResolverPostgresStore(connection)
        indexed_source = IndexedMetadataSource(store)
        versions = indexed_source.list_versions("requests")
        loaded = indexed_source.warm("requests", "2.31.0")

        self.assertEqual([item.version for item in versions], ["2.31.0"])
        self.assertEqual(loaded.name, "requests")
        self.assertEqual(loaded.version, "2.31.0")
        self.assertEqual(loaded.artifact_url, "https://files.pythonhosted.org/example/requests-2.31.0.whl")
        self.assertEqual(loaded.artifact_hash, "sha256:abc123")
        self.assertIn("urllib3 (<3,>=1.21.1)", loaded.requires_dist)


class BatchRunnerTests(unittest.TestCase):
    def test_runner_processes_multiple_jobs_with_fake_loader(self) -> None:
        class FakeLoader:
            def __init__(self):
                self.table_name = "pip_projects_metadata"
                self.ensure_schema_called = 0
                self.saved = []

            def ensure_schema(self):
                self.ensure_schema_called += 1

            def upsert_record(self, record):
                self.saved.append((record.name, record.version))

            def close(self):
                return None

        loader = FakeLoader()
        runner = PipBatchJobRunner(loader=loader)
        summary = runner.run(
            [
                BuildJobSpec(str(REQUESTS_WHEEL)),
                BuildJobSpec(str(DEEPTCR_SDIST)),
            ],
            ensure_schema=True,
        )

        self.assertEqual(summary.status, "partial")
        self.assertEqual(summary.loaded_count, 2)
        self.assertEqual(summary.failed_count, 0)
        self.assertEqual(loader.ensure_schema_called, 1)
        self.assertEqual(loader.saved[0], ("requests", "2.31.0"))
        self.assertEqual(loader.saved[1], ("DeepTCR", "1.4.20"))

    def test_runner_captures_extract_failure(self) -> None:
        class FakeLoader:
            table_name = "pip_projects_metadata"

            def ensure_schema(self):
                return None

            def upsert_record(self, record):
                return None

            def close(self):
                return None

        runner = PipBatchJobRunner(loader=FakeLoader())
        summary = runner.run([BuildJobSpec("missing-artifact.whl")])
        self.assertEqual(summary.status, "error")
        self.assertEqual(summary.failed_count, 1)
        self.assertEqual(summary.items[0].stage, "extract")

    def test_runner_keeps_table_name_in_dry_run_mode(self) -> None:
        runner = PipBatchJobRunner(table_name="pip_projects_metadata")
        summary = runner.run([BuildJobSpec(str(REQUESTS_WHEEL))])
        self.assertEqual(summary.to_dict()["store"]["table"], "pip_projects_metadata")

    def test_runner_skips_existing_release(self) -> None:
        class FakeLoader:
            table_name = "pip_projects_metadata"

            def ensure_schema(self):
                return None

            def has_release(self, name, version):
                return name == "requests" and version == "2.31.0"

            def upsert_record(self, record):
                raise AssertionError("upsert_record should not be called for skipped releases")

            def close(self):
                return None

        runner = PipBatchJobRunner(loader=FakeLoader())
        summary = runner.run(
            [BuildJobSpec(str(REQUESTS_WHEEL), project_name="requests", version="2.31.0")],
            skip_existing=True,
        )

        self.assertEqual(summary.status, "ok")
        self.assertEqual(summary.skipped_count, 1)
        self.assertEqual(summary.items[0].stage, "skip-existing")

    def test_runner_records_state_and_resumes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pip-runner-state-") as temp_dir:
            state_file = Path(temp_dir) / "state.jsonl"
            runner = PipBatchJobRunner(table_name="pip_projects_metadata")

            first = runner.run(
                [BuildJobSpec(str(REQUESTS_WHEEL), project_name="requests", version="2.31.0")],
                state_file=str(state_file),
            )
            second = runner.run(
                [BuildJobSpec(str(REQUESTS_WHEEL), project_name="requests", version="2.31.0")],
                state_file=str(state_file),
            )
            state_entries = read_jsonl(state_file)

        self.assertEqual(first.loaded_count, 1)
        self.assertEqual(second.skipped_count, 1)
        self.assertEqual(second.items[0].stage, "resume-skip")
        self.assertEqual(state_entries[0]["state_status"], "completed")

    def test_runner_removes_downloaded_artifact_after_success(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pip-runner-cleanup-") as temp_dir:
            downloaded = _build_minimal_wheel(Path(temp_dir) / "requests-2.31.0-py3-none-any.whl")

            class FakeLoader:
                table_name = "pip_projects_metadata"

                def upsert_record(self, record):
                    return None

            runner = PipBatchJobRunner(loader=FakeLoader())
            summary = runner.run(
                [
                    BuildJobSpec(
                        str(downloaded),
                        project_name="requests",
                        version="2.31.0",
                        cleanup_artifact_path=str(downloaded),
                    )
                ]
            )

            self.assertEqual(summary.status, "ok")
            self.assertFalse(downloaded.exists())


class LoadCliTests(unittest.TestCase):
    def test_load_cli_writes_failure_log_for_extract_error(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pip-load-cli-") as temp_dir:
            failure_log = Path(temp_dir) / "failures.jsonl"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(PIP_ROOT / "load.py"),
                    "does-not-exist.whl",
                    "--failure-log",
                    str(failure_log),
                ],
                cwd=PROJECT_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 1)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "error")
            lines = failure_log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["stage"], "extract")


class BuildCliTests(unittest.TestCase):
    def test_build_cli_accepts_manifest_and_writes_failure_log(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pip-build-cli-") as temp_dir:
            temp_path = Path(temp_dir)
            manifest = temp_path / "jobs.json"
            failure_log = temp_path / "failures.jsonl"
            manifest.write_text(
                json.dumps(
                    {
                        "jobs": [
                            {
                                "artifact_path": "missing-artifact.whl",
                                "name": "missing",
                                "version": "0.0.0",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(PIP_ROOT / "build.py"),
                    "--dry-run",
                    "--manifest",
                    str(manifest),
                    "--failure-log",
                    str(failure_log),
                ],
                cwd=PROJECT_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 1)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "error")
            self.assertEqual(payload["metrics"]["requested_count"], 1)
            self.assertEqual(payload["items"][0]["stage"], "prepare")
            lines = failure_log.read_text(encoding="utf-8").splitlines()

        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["stage"], "prepare")

    def test_build_cli_dry_run_handles_batch(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(PIP_ROOT / "build.py"),
                "--dry-run",
                str(REQUESTS_WHEEL),
                str(DEEPTCR_SDIST),
            ],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["metrics"]["requested_count"], 2)
        self.assertEqual(payload["metrics"]["loaded_count"], 2)
        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["store"]["table"], "pip_projects_metadata")

    def test_build_cli_supports_project_requests_from_local_file_index(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pip-build-project-cli-") as temp_dir:
            temp_path = Path(temp_dir)
            wheel_path = _build_minimal_wheel(temp_path / "requests-2.31.0-py3-none-any.whl")
            base_url = _build_local_pypi_index(
                temp_path / "pypi",
                releases=[
                    {
                        "version": "2.31.0",
                        "filename": wheel_path.name,
                        "artifact_url": wheel_path.resolve().as_uri(),
                        "yanked": False,
                        "digests": {"sha256": "deadbeef"},
                    }
                ],
            )
            cache_dir = Path(temp_dir) / "cache"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(PIP_ROOT / "build.py"),
                    "--dry-run",
                    "--project",
                    "requests==2.31.0",
                    "--cache-dir",
                    str(cache_dir),
                    "--pypi-json-base-url",
                    base_url,
                ],
                cwd=PROJECT_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["metrics"]["requested_count"], 1)
        self.assertEqual(payload["metrics"]["loaded_count"], 1)
        self.assertEqual(payload["items"][0]["name"], "requests")
        self.assertEqual(payload["items"][0]["version"], "2.31.0")

    def test_build_cli_supports_project_file_requests(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pip-build-project-file-cli-") as temp_dir:
            temp_path = Path(temp_dir)
            wheel_path = _build_minimal_wheel(temp_path / "requests-2.31.0-py3-none-any.whl")
            base_url = _build_local_pypi_index(
                temp_path / "pypi",
                releases=[
                    {
                        "version": "2.31.0",
                        "filename": wheel_path.name,
                        "artifact_url": wheel_path.resolve().as_uri(),
                        "yanked": False,
                        "digests": {"sha256": "deadbeef"},
                    }
                ],
            )
            cache_dir = temp_path / "cache"
            project_file = temp_path / "packages.txt"
            project_file.write_text("requests\n", encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(PIP_ROOT / "build.py"),
                    "--dry-run",
                    "--project-file",
                    str(project_file),
                    "--cache-dir",
                    str(cache_dir),
                    "--pypi-json-base-url",
                    base_url,
                ],
                cwd=PROJECT_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["metrics"]["requested_count"], 1)
        self.assertEqual(payload["metrics"]["loaded_count"], 1)
        self.assertEqual(payload["items"][0]["name"], "requests")

    def test_build_cli_uses_state_file_for_resume(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pip-build-state-cli-") as temp_dir:
            temp_path = Path(temp_dir)
            wheel_path = _build_minimal_wheel(temp_path / "requests-2.31.0-py3-none-any.whl")
            base_url = _build_local_pypi_index(
                temp_path / "pypi",
                releases=[
                    {
                        "version": "2.31.0",
                        "filename": wheel_path.name,
                        "artifact_url": wheel_path.resolve().as_uri(),
                        "yanked": False,
                        "digests": {"sha256": "deadbeef"},
                    }
                ],
            )
            state_file = Path(temp_dir) / "state.jsonl"
            cache_dir = Path(temp_dir) / "cache"
            first = subprocess.run(
                [
                    sys.executable,
                    str(PIP_ROOT / "build.py"),
                    "--dry-run",
                    "--project",
                    "requests==2.31.0",
                    "--cache-dir",
                    str(cache_dir),
                    "--state-file",
                    str(state_file),
                    "--pypi-json-base-url",
                    base_url,
                ],
                cwd=PROJECT_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            second = subprocess.run(
                [
                    sys.executable,
                    str(PIP_ROOT / "build.py"),
                    "--dry-run",
                    "--project",
                    "requests==2.31.0",
                    "--cache-dir",
                    str(cache_dir),
                    "--state-file",
                    str(state_file),
                    "--pypi-json-base-url",
                    base_url,
                ],
                cwd=PROJECT_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(first.returncode, 0, msg=first.stderr)
        self.assertEqual(second.returncode, 0, msg=second.stderr)
        second_payload = json.loads(second.stdout)
        self.assertEqual(second_payload["metrics"]["skipped_count"], 1)
        self.assertEqual(second_payload["items"][0]["stage"], "resume-skip")


class PlanningAndFetchTests(unittest.TestCase):
    def test_version_planner_filters_yanked_and_applies_limit(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pip-planner-") as temp_dir:
            temp_path = Path(temp_dir)
            wheel_latest = _build_minimal_wheel(temp_path / "requests-2.31.0-py3-none-any.whl", version="2.31.0")
            wheel_prev = _build_minimal_wheel(temp_path / "requests-2.30.0-py3-none-any.whl", version="2.30.0")
            wheel_yanked = _build_minimal_wheel(temp_path / "requests-3.0.0-py3-none-any.whl", version="3.0.0")
            base_url = _build_local_pypi_index(
                temp_path / "pypi",
                releases=[
                    {
                        "version": "3.0.0",
                        "filename": wheel_yanked.name,
                        "artifact_url": wheel_yanked.resolve().as_uri(),
                        "yanked": True,
                        "digests": {"sha256": "1111"},
                    },
                    {
                        "version": "2.31.0",
                        "filename": wheel_latest.name,
                        "artifact_url": wheel_latest.resolve().as_uri(),
                        "yanked": False,
                        "digests": {"sha256": "2222"},
                    },
                    {
                        "version": "2.30.0",
                        "filename": wheel_prev.name,
                        "artifact_url": wheel_prev.resolve().as_uri(),
                        "yanked": False,
                        "digests": {"sha256": "3333"},
                    },
                ],
            )
            planner = VersionPlanner(PyPIJsonClient(pypi_json_base_url=base_url, cache_dir=str(temp_path / "cache")))
            request = BuildRequestAdapter().from_cli_args(
                argparse.Namespace(
                    artifacts=[],
                    projects=["requests"],
                    project_file=None,
                    name=None,
                    version=None,
                    limit=1,
                    include_yanked=False,
                    mirror_dir=None,
                )
            )[0]

            selected = planner.plan(request)

        self.assertEqual([item.version for item in selected], ["2.31.0"])

    def test_artifact_fetcher_prefers_local_mirror(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pip-fetcher-mirror-") as temp_dir:
            temp_path = Path(temp_dir)
            wheel_path = _build_minimal_wheel(temp_path / "requests-2.31.0-py3-none-any.whl")
            filename = wheel_path.name
            artifact_url = f"https://files.pythonhosted.org/packages/aa/bb/{filename}"
            base_url = _build_local_pypi_index(
                temp_path / "pypi",
                releases=[
                    {
                        "version": "2.31.0",
                        "filename": filename,
                        "artifact_url": artifact_url,
                        "yanked": False,
                        "digests": {"sha256": "feedface"},
                    }
                ],
            )
            mirror_path = temp_path / "mirror" / "web" / "packages" / "aa" / "bb"
            mirror_path.mkdir(parents=True, exist_ok=True)
            mirrored_artifact = mirror_path / filename
            shutil.copyfile(wheel_path, mirrored_artifact)

            fetcher = ArtifactFetcher(
                PyPIJsonClient(pypi_json_base_url=base_url, cache_dir=str(temp_path / "cache")),
                cache_dir=str(temp_path / "cache"),
            )

            acquired = fetcher.acquire("requests", "2.31.0", mirror_dir=str(temp_path / "mirror"))

        self.assertEqual(acquired.artifact_path, str(mirrored_artifact.resolve()))
        self.assertEqual(acquired.artifact_hash, "sha256:feedface")

    def test_artifact_fetcher_marks_remote_downloads_for_cleanup(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pip-fetcher-cleanup-") as temp_dir:
            temp_path = Path(temp_dir)
            wheel_path = _build_minimal_wheel(temp_path / "requests-2.31.0-py3-none-any.whl")
            base_url = _build_local_pypi_index(
                temp_path / "pypi",
                releases=[
                    {
                        "version": "2.31.0",
                        "filename": wheel_path.name,
                        "artifact_url": wheel_path.resolve().as_uri(),
                        "yanked": False,
                        "digests": {"sha256": "deadbeef"},
                    }
                ],
            )
            cache_dir = temp_path / "cache"
            fetcher = ArtifactFetcher(
                PyPIJsonClient(pypi_json_base_url=base_url, cache_dir=str(cache_dir)),
                cache_dir=str(cache_dir),
            )

            acquired = fetcher.acquire(
                "requests",
                "2.31.0",
                cleanup_downloaded_artifacts=True,
            )
            artifact_exists = Path(acquired.artifact_path).exists()

        self.assertTrue(artifact_exists)
        self.assertEqual(acquired.cleanup_artifact_path, acquired.artifact_path)

    def test_build_service_combines_package_planning_and_batch_runner(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pip-build-service-") as temp_dir:
            temp_path = Path(temp_dir)
            wheel_path = _build_minimal_wheel(temp_path / "requests-2.31.0-py3-none-any.whl")
            base_url = _build_local_pypi_index(
                temp_path / "pypi",
                releases=[
                    {
                        "version": "2.31.0",
                        "filename": wheel_path.name,
                        "artifact_url": wheel_path.resolve().as_uri(),
                        "yanked": False,
                        "digests": {"sha256": "deadbeef"},
                    }
                ],
            )
            request = BuildRequestAdapter().from_cli_args(
                argparse.Namespace(
                    artifacts=[],
                    projects=["requests==2.31.0"],
                    project_file=None,
                    name=None,
                    version=None,
                    limit=None,
                    include_yanked=False,
                    mirror_dir=None,
                )
            )[0]
            service = PipBuildService(
                cache_dir=str(temp_path / "cache"),
                pypi_json_base_url=base_url,
                table_name="pip_projects_metadata",
            )

            summary = service.run([request])

        self.assertEqual(summary.status, "ok")
        self.assertEqual(summary.loaded_count, 1)
        self.assertEqual(summary.items[0].name, "requests")

    def test_build_service_cleans_up_downloaded_artifacts_after_success(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pip-build-service-cleanup-") as temp_dir:
            temp_path = Path(temp_dir)
            wheel_path = _build_minimal_wheel(temp_path / "requests-2.31.0-py3-none-any.whl")
            base_url = _build_local_pypi_index(
                temp_path / "pypi",
                releases=[
                    {
                        "version": "2.31.0",
                        "filename": wheel_path.name,
                        "artifact_url": wheel_path.resolve().as_uri(),
                        "yanked": False,
                        "digests": {"sha256": "deadbeef"},
                    }
                ],
            )
            cache_dir = temp_path / "cache"

            class FakeLoader:
                table_name = "pip_projects_metadata"

                def upsert_record(self, record):
                    return None

            batch_runner = PipBatchJobRunner(loader=FakeLoader(), table_name="pip_projects_metadata")
            service = PipBuildService(
                batch_runner=batch_runner,
                cache_dir=str(cache_dir),
                pypi_json_base_url=base_url,
                table_name="pip_projects_metadata",
            )

            summary = service.run(
                [BuildRequest(project_name="requests", versions=("2.31.0",))],
                cleanup_downloaded_artifacts=True,
            )

            artifact_dir = cache_dir / "artifacts"
            remaining_artifacts = [path for path in artifact_dir.rglob("*") if path.is_file()] if artifact_dir.exists() else []

        self.assertEqual(summary.status, "ok")
        self.assertEqual(summary.loaded_count, 1)
        self.assertEqual(remaining_artifacts, [])

    def test_build_service_backfill_skips_existing_versions_before_fetch(self) -> None:
        class FakeLoader:
            table_name = "pip_projects_metadata"

            def has_release(self, name, version):
                return version == "2.31.0"

        class FakeBatchRunner:
            def __init__(self):
                self.loader = FakeLoader()
                self.received_jobs = []

            def run(self, jobs, **kwargs):
                self.received_jobs = list(jobs)
                return BatchBuildSummary(
                    status="ok",
                    items=tuple(
                        BatchBuildItemResult(
                            artifact_path=job.artifact_path,
                            status="ok",
                            stage="load",
                            name=job.project_name,
                            version=job.version,
                        )
                        for job in self.received_jobs
                    ),
                    ensure_schema=bool(kwargs.get("ensure_schema", False)),
                    table_name="pip_projects_metadata",
                    failure_log=kwargs.get("failure_log"),
                )

        class FakePlanner:
            def plan(self, request):
                return [
                    VersionPlanItem(project_name="requests", version="2.31.0"),
                    VersionPlanItem(project_name="requests", version="2.30.0"),
                ]

        class FakeFetcher:
            def acquire(self, project_name, version, *, mirror_dir=None, cleanup_downloaded_artifacts=False):
                return AcquiredArtifact(
                    project_name=project_name,
                    version=version,
                    artifact_path=str(REQUESTS_WHEEL),
                )

        service = PipBuildService(
            batch_runner=FakeBatchRunner(),
            version_planner=FakePlanner(),
            artifact_fetcher=FakeFetcher(),
            table_name="pip_projects_metadata",
        )

        summary = service.run([BuildRequest(project_name="requests")], backfill=True)

        self.assertEqual(summary.skipped_count, 1)
        self.assertEqual(summary.loaded_count, 1)
        self.assertEqual(summary.items[0].stage, "skip-existing")


if __name__ == "__main__":
    unittest.main()
