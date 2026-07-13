---
layout: default
title: Preprocessing and Indexed Mode
description: Prepare local metadata stores and shared caches for reproducible indexed or cache-backed resolution.
permalink: /preprocessing-indexed-mode/
---

OpenDep supports two execution styles:

- **Online mode** queries upstream package metadata during resolution.
- **Indexed or cache-backed mode** first prepares local metadata stores or shared caches, then resolves against that prepared data.

Indexed or cache-backed mode is recommended for reproducible and large-scale dependency analysis because it reduces repeated upstream fetches and makes the metadata handoff explicit.

## Shared PostgreSQL Setup for pip, npm, and Go

pip, npm, and Go indexed workflows use a shared PostgreSQL database.

Start the shared preprocessing PostgreSQL container:

```bash
docker compose \
  --env-file pre-process/common/database/.env.example \
  -f pre-process/common/database/docker-compose.yml \
  up -d
```

Set the shared DSN on Linux or macOS:

```bash
export INDEX_DSN='postgresql://opendep:opendep@host.docker.internal:55432/opendep_preprocess'
```

Set the shared DSN on Windows PowerShell:

```powershell
$env:INDEX_DSN="postgresql://opendep:opendep@host.docker.internal:55432/opendep_preprocess"
```

## pip Indexed Workflow

Build the pip preprocess image:

```bash
docker compose -f pre-process/pip/docker-compose.yml build pip-preprocess
```

Index package metadata from the example package list:

```bash
docker compose -f pre-process/pip/docker-compose.yml run --rm pip-preprocess \
  build \
  --project-file /workspace/pre-process/pip/examples/package-list.txt \
  --pretty
```

Resolve against the indexed metadata:

```bash
python3 main.py resolve \
  --ecosystem pip \
  --name requests \
  --version 2.32.5 \
  --format graph \
  --pip-mode indexed \
  --pip-index-dsn "$INDEX_DSN" \
  --pip-index-table pip_metadata
```

## npm Indexed Workflow

Build the npm preprocess image:

```bash
docker compose -f pre-process/npm/docker-compose.yml build npm-preprocess
```

Index package metadata from the example package list:

```bash
docker compose -f pre-process/npm/docker-compose.yml run --rm npm-preprocess \
  build \
  --package-file /workspace/pre-process/npm/examples/package-list.txt \
  --pretty
```

Resolve against the indexed metadata:

```bash
python3 main.py resolve \
  --ecosystem npm \
  --name mocha \
  --version 10.0.0 \
  --format graph \
  --npm-mode indexed \
  --npm-index-dsn "$INDEX_DSN" \
  --npm-index-table npm_metadata
```

## Go Indexed Workflow

Build the Go preprocess image:

```bash
docker compose -f pre-process/go/docker-compose.yml build go-preprocess
```

Index module metadata from the example module list:

```bash
docker compose -f pre-process/go/docker-compose.yml run --rm go-preprocess \
  build \
  --module-file /workspace/pre-process/go/examples/module-list.txt \
  --pretty
```

Resolve against the indexed metadata:

```bash
python3 main.py resolve \
  --ecosystem go \
  --name github.com/rogpeppe/godef \
  --version v1.1.2 \
  --format graph \
  --go-mode indexed \
  --go-index-dsn "$INDEX_DSN" \
  --go-index-table go_metadata
```

Optional Go `list` command:

```bash
python3 main.py list \
  --ecosystem go \
  --name github.com/rogpeppe/godef \
  --version v1.1.2 \
  --go-mode indexed \
  --go-index-dsn "$INDEX_DSN" \
  --go-index-table go_metadata
```

## Cargo Indexed Workflow

Cargo indexed mode does not use PostgreSQL. It uses a shared Docker volume containing a prepared Cargo local registry.

Build the Cargo preprocess image:

```bash
docker compose -f pre-process/cargo/docker-compose.yml build cargo-preprocess
```

Bootstrap the shared Cargo metadata:

```bash
docker compose -f pre-process/cargo/docker-compose.yml run --rm cargo-preprocess clone --pretty
```

Prepare the local registry:

```bash
docker compose -f pre-process/cargo/docker-compose.yml run --rm cargo-preprocess \
  prepare-local-registry \
  --force \
  --pretty
```

Resolve against the indexed Cargo data:

```bash
python3 main.py resolve \
  --ecosystem cargo \
  --name rand \
  --version 0.8.5 \
  --format graph \
  --cargo-mode indexed
```

Optional full-format output:

```bash
python3 main.py resolve \
  --ecosystem cargo \
  --name rand \
  --version 0.8.5 \
  --format full \
  --cargo-mode indexed
```

## Maven Shared Cache Workflow

Maven uses a shared `.m2` cache volume instead of a PostgreSQL metadata table.

Build the Maven preprocess image:

```bash
docker compose -f pre-process/maven/docker-compose.yml build maven-preprocess
```

Warm the Maven cache with the curated example coordinate closure:

```bash
docker compose -f pre-process/maven/docker-compose.yml run --rm \
  maven-preprocess warm \
  --coordinate-file /workspace/pre-process/maven/examples/coordinate-list.txt \
  --pretty
```

Resolve through the shared Maven cache contract:

```bash
python3 main.py resolve \
  --ecosystem maven \
  --name org.apache.logging.log4j:log4j-core \
  --version 2.23.1 \
  --format graph
```

## Indexed Mode Summary

| Ecosystem | Preprocess input | Persistent contract | Resolver option |
| --- | --- | --- | --- |
| pip | package specs or local artifacts | PostgreSQL `pip_metadata` | `--pip-mode indexed` |
| npm | package names or registry changes | PostgreSQL `npm_metadata` | `--npm-mode indexed` |
| Go | module or `module@version` entries | PostgreSQL `go_metadata` | `--go-mode indexed` |
| Cargo | managed `crates.io-index` clone | Docker volume `resolver-cargo-cache` | `--cargo-mode indexed` |
| Maven | Maven coordinates or package names | Docker volume `resolver-maven-m2-cache` | default shared-cache contract |

