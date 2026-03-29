# pip Resolver Image

`resolving/containerization/images/pip/` is the Dockerized dependency resolver for Python packages.
This README only documents the Docker-based `live` and `indexed` workflows.

## What It Does

The pip resolver container:

- reads a normalized resolver request JSON from standard input
- resolves Python package dependencies
- returns a normalized dependency graph JSON result

It supports two metadata modes:

- `live`
  - no database required
  - fetches package metadata on demand from the package index
  - easiest to use, but slower
- `indexed`
  - reads pre-extracted metadata from PostgreSQL
  - requires the preprocess pipeline to populate `pip_metadata` first
  - faster and more stable for repeated resolution

## Build the Image

Run from the repository root:

```bash
docker build -f resolving/containerization/images/pip/Dockerfile -t pip-resolver:latest .
```

## Live Mode

Use `live` mode when you want the resolver to work without any preprocessing database.

Example:

```bash
printf '%s\n' '{
  "schema_version": "1.0",
  "request_id": "pip-live-requests-2.32.5",
  "trace_id": "pip-live-requests-2.32.5-trace",
  "command": "resolve",
  "ecosystem": "pip",
  "package": {
    "name": "requests",
    "version": "2.32.5"
  },
  "options": {
    "format": "graph",
    "timeout_ms": 180000,
    "return_raw": false
  }
}' | docker run --rm -i \
  -e PIP_METADATA_MODE=live \
  pip-resolver:latest
```

You can also reuse the example request file:

[`resolve-live-request.json`](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/images/pip/examples/resolve-live-request.json)

```bash
printf '%s\n' "$(cat resolving/containerization/images/pip/examples/resolve-live-request.json)" \
  | docker run --rm -i \
      -e PIP_METADATA_MODE=live \
      pip-resolver:latest
```

## Indexed Mode

Use `indexed` mode when you already have metadata prepared by `pre-process/pip/`.

### Prerequisites

Start the shared preprocessing PostgreSQL container:

```bash
docker compose \
  --env-file pre-process/common/database/.env.example \
  -f pre-process/common/database/docker-compose.yml \
  up -d
```

Populate `pip_metadata` first. Example:

```bash
docker compose -f pre-process/pip/docker-compose.yml run --rm pip-preprocess \
  build \
  --project requests==2.32.5 \
  --ensure-schema \
  --cleanup-downloaded-artifacts \
  --pretty
```

### Resolve with Indexed Metadata

```bash
printf '%s\n' '{
  "schema_version": "1.0",
  "request_id": "pip-indexed-requests-2.32.5",
  "trace_id": "pip-indexed-requests-2.32.5-trace",
  "command": "resolve",
  "ecosystem": "pip",
  "package": {
    "name": "requests",
    "version": "2.32.5"
  },
  "options": {
    "format": "graph",
    "timeout_ms": 180000,
    "return_raw": false
  }
}' | docker run --rm -i \
  -e PIP_METADATA_MODE=indexed \
  -e PIP_INDEX_DSN='postgresql://opendep:opendep@host.docker.internal:55432/opendep_preprocess' \
  -e PIP_INDEX_TABLE='pip_metadata' \
  pip-resolver:latest
```

You can also reuse the example request file:

[`resolve-indexed-request.json`](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/images/pip/examples/resolve-indexed-request.json)

```bash
printf '%s\n' "$(cat resolving/containerization/images/pip/examples/resolve-indexed-request.json)" \
  | docker run --rm -i \
      -e PIP_METADATA_MODE=indexed \
      -e PIP_INDEX_DSN='postgresql://opendep:opendep@host.docker.internal:55432/opendep_preprocess' \
      -e PIP_INDEX_TABLE='pip_metadata' \
      pip-resolver:latest
```

## Notes

- The container default command is the pip runtime adapter, so you only need to pipe request JSON into `docker run`.
- `indexed` mode does not fetch missing releases from PyPI unless you explicitly enable fallback in the environment.
- The default indexed table is `pip_metadata`.
- Inside Docker, `127.0.0.1` points to the resolver container itself. For a PostgreSQL service running on the host, use `host.docker.internal` or your actual reachable database host.
