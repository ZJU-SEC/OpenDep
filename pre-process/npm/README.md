# npm Pre-process Workspace

`pre-process/npm/` is the offline indexing workspace for npm package metadata.

## What It Does

The npm preprocess container can:

- read explicit package-name inputs from CLI flags or a text file
- fetch raw npm packuments from the configured registry
- store one PostgreSQL row per requested package name
- preserve the exact `raw_packument` payload so the indexed npm resolver can keep using the existing package-document parsing logic

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

## Workflow

For bulk indexing, use a plain text package list with one package name per line. Example file: [`package-list.txt`](examples/package-list.txt)

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
4. rely on shared yoyo migrations from `pre-process/common/database/initdb/`
5. upsert rows into `npm_metadata`

Use `--concurrency N` when you want to overlap registry fetches for larger package lists.
The default is `1`, which keeps the fetch path fully sequential.

Build the resolver image:

```bash
docker compose -f resolving/containerization/docker-compose.yml build resolver-npm
```

Check that the resolver health:

```bash
python3 main.py health --ecosystem npm
```

Then run a resolve:

```bash
python3 main.py resolve --ecosystem npm --name left-pad --version 1.3.0 --format graph --npm-mode indexed --npm-index-dsn 'postgresql://opendep:opendep@host.docker.internal:55432/opendep_preprocess' --npm-index-table npm_metadata
```

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

To keep `pre-process` and `resolving` aligned, the npm container does not
start its own database service. It connects to the shared PostgreSQL instance
from `pre-process/common/database/`, which also applies new SQL migrations
through the yoyo migration runner.

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