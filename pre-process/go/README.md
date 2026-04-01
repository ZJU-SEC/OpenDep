# Go Pre-process Workspace

`pre-process/go/` is the offline indexing workspace for Go module metadata. This README documents the Docker workflow and the shared PostgreSQL contract.

## What It Does

The Go preprocess container can:

- read explicit `module@version` inputs from CLI flags or a text file
- fetch raw `.mod` files from a Go proxy
- store one PostgreSQL row per requested `(module_path, version)`
- preserve the exact `raw_mod` payload so the indexed resolver can keep using the existing Go parser

The current indexed target is:

- database: `opendep_preprocess`
- table: `go_metadata`

The indexed Go resolver reads these rows when `--go-mode indexed` is enabled.

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

## Workflow

For bulk indexing, use a plain text module list with one `module` or `module@version` per line. Example file: [`module-list.txt`](examples/module-list.txt)

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
2. when a version is omitted, call `/<module>/@v/list` to enumerate all known versions
3. fetch `/<module>/@v/<version>.mod` from the configured Go proxy
4. upsert rows into `go_metadata`

Use `--concurrency N` when you want to overlap Go proxy fetches for larger module lists.
The default is `1`, which keeps the fetch path fully sequential.

Build the resolver image:

```bash
docker compose -f resolving/containerization/docker-compose.yml build resolver-go
```

Check that the resolver health:

```bash
python3 main.py health --ecosystem go
```

Then run a resolve:

```bash
python3 main.py resolve --ecosystem go --name github.com/rogpeppe/godef --version v1.1.2 --format graph --go-mode indexed --go-index-dsn 'postgresql://opendep:opendep@host.docker.internal:55432/opendep_preprocess' --go-index-table go_metadata
```



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

If your PostgreSQL container is exposed differently, override those variables when running the Go preprocess container.

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
