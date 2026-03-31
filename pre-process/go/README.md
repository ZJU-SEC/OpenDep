# Go Pre-process Workspace

`pre-process/go/` is the offline indexing workspace for Go module metadata.
This README documents the Docker-based workflow and follows the same shared PostgreSQL setup used by `pre-process/pip`.

## What It Does

The Go preprocess container can:

- read explicit `module@version` inputs from CLI flags or a text file
- fetch raw `.mod` files from a Go proxy
- store one PostgreSQL row per requested `(module_path, version)`
- preserve the exact `raw_mod` payload so the future indexed resolver can keep using the existing Go parser

The current indexed target is:

- database: `opendep_preprocess`
- table: `go_metadata`

This is the selected Scheme A design:

- one table keyed by `(module_path, version)`
- `raw_mod` is the authoritative payload
- dependency edges are not split into separate tables in v1

## Prerequisites

Start the shared preprocessing PostgreSQL container first:

```bash
docker compose \
  --env-file pre-process/common/database/.env.example \
  -f pre-process/common/database/docker-compose.yml \
  up -d
```

Build the Go preprocess image:

```bash
docker compose -f pre-process/go/docker-compose.yml build
```

## Recommended Workflow

For bulk indexing, use a plain text module list with one `module` or `module@version` per line.

Example file:

[`module-list.txt`](/Users/xingyu/project/Paper/OpenDep/pre-process/go/examples/module-list.txt)

```text
github.com/rogpeppe/godef@v1.1.2
golang.org/x/text@v0.23.0
```

If a line omits the version, the preprocess pipeline first calls the Go proxy
`/@v/list` endpoint for that module, then fetches and stores every listed
version.

Run the recommended module-file workflow:

```bash
docker compose -f pre-process/go/docker-compose.yml run --rm go-preprocess \
  build \
  --module-file /workspace/pre-process/go/examples/module-list.txt \
  --concurrency 4 \
  --pretty
```

This will:

1. read each `module` or `module@version` entry from the file
2. when a version is omitted, call `/<escaped module>/@v/list` to enumerate all known versions
3. fetch `/<escaped module>/@v/<escaped version>.mod` from the configured Go proxy
4. compute `raw_mod_sha256`
5. rely on the shared yoyo migration runner over `pre-process/common/database/initdb/`
6. upsert rows into `go_metadata`

Use `--concurrency N` when you want to overlap Go proxy fetches for larger module lists.
The default is `1`, which keeps the fetch path fully sequential.

## Other Docker Commands

Index one explicit module version:

```bash
docker compose -f pre-process/go/docker-compose.yml run --rm go-preprocess \
  build \
  --module github.com/rogpeppe/godef@v1.1.2 \
  --pretty
```

Skip rows that are already present:

```bash
docker compose -f pre-process/go/docker-compose.yml run --rm go-preprocess \
  build \
  --module-file /workspace/pre-process/go/examples/module-list.txt \
  --skip-existing \
  --pretty
```

Increase fetch parallelism for batch ingestion:

```bash
docker compose -f pre-process/go/docker-compose.yml run --rm go-preprocess \
  build \
  --module-file /workspace/pre-process/go/examples/module-list.txt \
  --concurrency 8 \
  --pretty
```

Use a non-default Go proxy:

```bash
docker compose -f pre-process/go/docker-compose.yml run --rm go-preprocess \
  build \
  --module github.com/rogpeppe/godef@v1.1.2 \
  --proxy-base-url https://proxy.golang.org \
  --pretty
```

## Container Database Settings

The Go preprocess container uses the same shared PostgreSQL defaults as the pip preprocess container:

- `PREPROCESS_DB_HOST=host.docker.internal`
- `PREPROCESS_DB_PORT=55432`
- `PREPROCESS_DB_NAME=opendep_preprocess`
- `PREPROCESS_DB_USER=opendep`
- `PREPROCESS_DB_PASSWORD=opendep`

To keep `pre-process` and future `resolving` database access aligned, the Go container does not start its own database service.
It connects to the shared PostgreSQL instance from `pre-process/common/database/`.
That shared DB stack automatically applies new SQL migrations from `pre-process/common/database/initdb/` through the Python-based yoyo migration runner.

If your PostgreSQL container is exposed differently, override those variables when running the Go preprocess container.
Use `GO_PREPROCESS_DB_HOST` for the compose-level host override, because `127.0.0.1` inside the container points back to the preprocess container itself.

Example:

```bash
GO_PREPROCESS_DB_HOST=host.docker.internal \
PREPROCESS_DB_PORT=55432 \
PREPROCESS_DB_NAME=opendep_preprocess \
PREPROCESS_DB_USER=opendep \
PREPROCESS_DB_PASSWORD=opendep \
docker compose -f pre-process/go/docker-compose.yml run --rm go-preprocess \
  build \
  --module github.com/rogpeppe/godef@v1.1.2 \
  --pretty
```

## Notes

- The compose service mounts the repository root into `/workspace`.
- Use `/workspace/...` paths for files passed into the container.
- The current workflow is Docker-first and targets the same PostgreSQL instance that other preprocess jobs use.
- `--ensure-schema` remains available as a local fallback, but the shared database lifecycle is now expected to be driven by yoyo migrations.
- The future Go indexed resolver should read from `go_metadata` instead of requiring a separate database.
