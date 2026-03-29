# pip Pre-process Workspace

`pre-process/pip/` is the offline indexing workspace for Python packages.
This README only documents the Docker-based workflow.

## What It Does

The pip preprocess container can:

- read package inputs from a file, manifest, package spec, or local artifact
- fetch package release artifacts from PyPI or a local mirror
- extract dependency metadata from each release artifact
- write normalized rows into the shared preprocessing PostgreSQL database

The indexed pip resolver then reads those rows from `pip_metadata`.

## Prerequisites

Start the shared preprocessing PostgreSQL container first:

```bash
docker compose \
  --env-file pre-process/common/database/.env.example \
  -f pre-process/common/database/docker-compose.yml \
  up -d
```

Build the pip preprocess image:

```bash
docker compose -f pre-process/pip/docker-compose.yml build
```

## Recommended Workflow

For bulk indexing, use a plain text package list with one PyPI package spec per line.

Example file:

[`package-list.txt`](/Users/xingyu/project/Paper/OpenDep/pre-process/pip/examples/package-list.txt)

```text
requests
urllib3
charset-normalizer
```

Run the recommended package-file workflow:

```bash
docker compose -f pre-process/pip/docker-compose.yml run --rm pip-preprocess \
  build \
  --project-file /workspace/pre-process/pip/examples/package-list.txt \
  --cleanup-downloaded-artifacts \
  --pretty
```

This will:

1. read every package name from the file
2. query the package index for all available non-yanked versions
3. download a selected artifact for each version
4. extract dependency metadata
5. rely on the shared yoyo migration runner over `pre-process/common/database/initdb/`
6. write the normalized records into PostgreSQL
7. delete downloaded remote artifacts after successful processing

If you want to avoid downloading release artifacts that have already been
indexed into PostgreSQL, add `--backfill` or `--skip-existing`.

- `--backfill`
  - recommended for package-list workflows
  - plan package versions first, then only process releases that are missing from the target table
- `--skip-existing`
  - skip any release whose `name + version` already exists in the target table

With either flag, the preprocess pipeline checks the database before attempting to fetch the release artifact, so already indexed release versions are skipped without being downloaded again.

## Other Docker Commands

Process one explicit package version:

```bash
docker compose -f pre-process/pip/docker-compose.yml run --rm pip-preprocess \
  build \
  --project requests==2.31.0 \
  --pretty
```

Process the latest `N` versions of a package:

```bash
docker compose -f pre-process/pip/docker-compose.yml run --rm pip-preprocess \
  build \
  --project requests \
  --limit 3 \
  --cache-dir /tmp/pip-preprocess-cache \
  --pretty
```

Use a package manifest:

```bash
docker compose -f pre-process/pip/docker-compose.yml run --rm pip-preprocess \
  build \
  --manifest /workspace/pre-process/pip/examples/build-package-manifest.json \
  --cache-dir /tmp/pip-preprocess-cache \
  --pretty
```

Extract metadata from one local artifact without writing to PostgreSQL:

```bash
docker compose -f pre-process/pip/docker-compose.yml run --rm pip-preprocess \
  extract \
  --pretty \
  /workspace/path/to/package.whl
```

Extract and load one local artifact:

```bash
docker compose -f pre-process/pip/docker-compose.yml run --rm pip-preprocess \
  load \
  /workspace/path/to/package.whl \
  --pretty
```

Process one or more local artifacts in batch:

```bash
docker compose -f pre-process/pip/docker-compose.yml run --rm pip-preprocess \
  build \
  --pretty \
  /workspace/path/to/package-a.whl \
  /workspace/path/to/package-b.tar.gz
```

## Incremental Indexing

`build` supports three controls for larger jobs:

- `--skip-existing`
  - skip releases that already exist in the target table
- `--backfill`
  - plan the selected versions and only fill missing releases
- `--state-file /path/to/state.jsonl`
  - record completed releases and skip them on rerun

Example:

```bash
docker compose -f pre-process/pip/docker-compose.yml run --rm pip-preprocess \
  build \
  --project-file /workspace/pre-process/pip/examples/package-list.txt \
  --backfill \
  --state-file /tmp/pip-build-state.jsonl \
  --cache-dir /tmp/pip-preprocess-cache \
  --cleanup-downloaded-artifacts \
  --pretty
```

If your main goal is to avoid re-downloading already indexed release artifacts,
prefer:

```bash
docker compose -f pre-process/pip/docker-compose.yml run --rm pip-preprocess \
  build \
  --project-file /workspace/pre-process/pip/examples/package-list.txt \
  --backfill \
  --cleanup-downloaded-artifacts \
  --pretty
```

## Container Database Settings

The pip preprocess container uses these defaults:

- `PREPROCESS_DB_HOST=host.docker.internal`
- `PREPROCESS_DB_PORT=55432`
- `PREPROCESS_DB_NAME=opendep_preprocess`
- `PREPROCESS_DB_USER=opendep`
- `PREPROCESS_DB_PASSWORD=opendep`

If your PostgreSQL container is exposed differently, override those variables
when running the preprocess container. Use `PIP_PREPROCESS_DB_HOST` for the
compose-level host override, because `127.0.0.1` inside the container points
back to the preprocess container itself.
The shared DB stack automatically applies new SQL migrations from `pre-process/common/database/initdb/` through the Python-based yoyo migration runner.

Example:

```bash
PIP_PREPROCESS_DB_HOST=host.docker.internal \
PREPROCESS_DB_PORT=55432 \
PREPROCESS_DB_NAME=opendep_preprocess \
PREPROCESS_DB_USER=opendep \
PREPROCESS_DB_PASSWORD=opendep \
docker compose -f pre-process/pip/docker-compose.yml run --rm pip-preprocess \
  build \
  --project requests==2.31.0 \
  --pretty
```

## Notes

- The compose service mounts the repository root into `/workspace`.
- Use `/workspace/...` paths for files passed into the container.
- `--cleanup-downloaded-artifacts` only removes remotely downloaded artifacts.
- It does not delete the package list file, local artifact inputs, mirror files, or cached PyPI JSON metadata.
- `--ensure-schema` remains available as a local fallback, but the shared database lifecycle is now expected to be driven by yoyo migrations.
- The current indexed target is:
  - database: `opendep_preprocess`
  - table: `pip_metadata`
