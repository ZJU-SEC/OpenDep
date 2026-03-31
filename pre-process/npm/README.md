# npm Pre-process Workspace

`pre-process/npm/` is the offline indexing workspace for npm package metadata.
This README documents the Docker-based workflow and follows the same shared PostgreSQL setup used by the other preprocess ecosystems.

## What It Does

The npm preprocess container can:

- read explicit package-name inputs from CLI flags or a text file
- fetch raw npm packuments from the configured registry
- store one PostgreSQL row per requested package name
- preserve the exact `raw_packument` payload so a future indexed npm resolver can keep using the existing package-document parsing logic

The current indexed target is:

- database: `opendep_preprocess`
- table: `npm_metadata`
- future checkpoint table: `npm_sync_state`
- delete tombstone table: `npm_tombstones`

This is the selected v1 design:

- one table keyed by package name
- `raw_packument` is the authoritative payload
- package versions and dependency maps are not split into child tables in v1
- v1 is batch ingestion of explicit package names, not `_changes`-based continuous sync

## Prerequisites

Start the shared preprocessing PostgreSQL container first:

```bash
docker compose \
  --env-file pre-process/common/database/.env.example \
  -f pre-process/common/database/docker-compose.yml \
  up -d
```

Build the npm preprocess image:

```bash
docker compose -f pre-process/npm/docker-compose.yml build
```

## Recommended Workflow

For bulk indexing, use a plain text package list with one package name per line.

Example file:

[`package-list.txt`](/Users/xingyu/project/Paper/OpenDep/pre-process/npm/examples/package-list.txt)

```text
is-odd
@types/node
```

Run the recommended package-file workflow:

```bash
docker compose -f pre-process/npm/docker-compose.yml run --rm npm-preprocess \
  build \
  --package-file /workspace/pre-process/npm/examples/package-list.txt \
  --concurrency 4 \
  --pretty
```

This will:

1. read each package name from the file
2. fetch `/<escaped package>` from the configured npm registry
3. compute `raw_packument_sha256`
4. rely on the shared yoyo migration runner over `pre-process/common/database/initdb/`
5. upsert rows into `npm_metadata`

Use `--concurrency N` when you want to overlap registry fetches for larger package lists.
The default is `1`, which keeps the fetch path fully sequential.

## Other Docker Commands

Index one explicit package:

```bash
docker compose -f pre-process/npm/docker-compose.yml run --rm npm-preprocess \
  build \
  --package @types/node \
  --pretty
```

Skip package names that are already present:

```bash
docker compose -f pre-process/npm/docker-compose.yml run --rm npm-preprocess \
  build \
  --package-file /workspace/pre-process/npm/examples/package-list.txt \
  --skip-existing \
  --pretty
```

Increase fetch parallelism for batch ingestion:

```bash
docker compose -f pre-process/npm/docker-compose.yml run --rm npm-preprocess \
  build \
  --package-file /workspace/pre-process/npm/examples/package-list.txt \
  --concurrency 8 \
  --pretty
```

Use a non-default npm registry:

```bash
docker compose -f pre-process/npm/docker-compose.yml run --rm npm-preprocess \
  build \
  --package @types/node \
  --registry-base-url https://registry.npmjs.org \
  --pretty
```

Run one `_changes` sync batch with PostgreSQL-backed checkpoint state:

```bash
docker compose -f pre-process/npm/docker-compose.yml run --rm npm-preprocess \
  sync \
  sync-once \
  --source-key npmjs-primary \
  --pretty
```

Override the `_changes` feed source or the initial checkpoint token when needed:

```bash
docker compose -f pre-process/npm/docker-compose.yml run --rm npm-preprocess \
  sync \
  sync-once \
  --source-key npmjs-primary \
  --changes-url https://replicate.npmjs.com/registry/_changes \
  --registry-base-url https://replicate.npmjs.com/registry \
  --since 0 \
  --limit 500 \
  --pretty
```

Run continuous follow mode with idle backoff and bounded fetch concurrency:

```bash
docker compose -f pre-process/npm/docker-compose.yml run --rm npm-preprocess \
  sync \
  sync-follow \
  --source-key npmjs-primary \
  --poll-interval 30 \
  --idle-backoff 60 \
  --concurrency 4 \
  --pretty
```

Package delete events are now applied during `_changes` sync:

- the current `npm_metadata` snapshot row is removed
- an active tombstone row is written into `npm_tombstones`
- a later non-delete event for the same package restores `npm_metadata` and clears the active tombstone

## Container Database Settings

The npm preprocess container uses the same shared PostgreSQL defaults as the other preprocess containers:

- `PREPROCESS_DB_HOST=host.docker.internal`
- `PREPROCESS_DB_PORT=55432`
- `PREPROCESS_DB_NAME=opendep_preprocess`
- `PREPROCESS_DB_USER=opendep`
- `PREPROCESS_DB_PASSWORD=opendep`

To keep `pre-process` and future `resolving` database access aligned, the npm container does not start its own database service.
It connects to the shared PostgreSQL instance from `pre-process/common/database/`.
That shared DB stack automatically applies new SQL migrations from `pre-process/common/database/initdb/` through the Python-based yoyo migration runner.

If your PostgreSQL container is exposed differently, override those variables when running the npm preprocess container.
Use `NPM_PREPROCESS_DB_HOST` for the compose-level host override, because `127.0.0.1` inside the container points back to the preprocess container itself.

Example:

```bash
NPM_PREPROCESS_DB_HOST=host.docker.internal \
PREPROCESS_DB_PORT=55432 \
PREPROCESS_DB_NAME=opendep_preprocess \
PREPROCESS_DB_USER=opendep \
PREPROCESS_DB_PASSWORD=opendep \
docker compose -f pre-process/npm/docker-compose.yml run --rm npm-preprocess \
  build \
  --package @types/node \
  --pretty
```

## Notes

- The compose service mounts the repository root into `/workspace`.
- Use `/workspace/...` paths for files passed into the container.
- The current workflow is Docker-first and targets the same PostgreSQL instance that other preprocess jobs use.
- `--ensure-schema` remains available as a local fallback, but the shared database lifecycle is now expected to be driven by yoyo migrations.
- `--skip-existing` only skips package names that already have a row in `npm_metadata`; it does not mean the stored packument is the newest possible snapshot.
- `_changes`-based sync is now available through `sync-once` and `sync-follow`, while the original batch `build` entrypoint remains the simpler option for explicit package lists.
- The shared migration set now also creates `npm_sync_state` and `npm_tombstones` for checkpointing and package-level delete tracking.
- `sync-follow` is the PostgreSQL-backed successor to the legacy always-on crawler flow, but it now runs as an explicit command instead of a CouchDB-mirroring Scrapy daemon.
- Version-level unpublish remains a normal packument replacement in `npm_metadata`; only package-level delete events create rows in `npm_tombstones`.
