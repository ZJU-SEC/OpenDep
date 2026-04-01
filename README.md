# OpenDep

OpenDep provides a Docker-based dependency resolver CLI through
`python3 main.py`.

## Prerequisites

Before running the resolver, make sure the host machine has:

- Python 3 available as `python3`
- Docker installed and the Docker daemon running
- Docker Compose available through `docker compose`
- Internet access for first-time live or online fetches, or for preprocess and
  cache warm-up steps

## Quick Start

### 1. Build the resolver services

From the repository root:

```bash
docker compose -f resolving/containerization/docker-compose.yml build
```

### 2. Start shared PostgreSQL if you plan to use indexed `pip`, `npm`, or `go`

```bash
docker compose \
  --env-file pre-process/common/database/.env.example \
  -f pre-process/common/database/docker-compose.yml \
  up -d
```

### 3. Prepare shared runtime data when needed

- Cargo requires a preprocess-managed shared `local-registry`:

```bash
docker compose -f pre-process/cargo/docker-compose.yml run --rm cargo-preprocess clone --pretty
docker compose -f pre-process/cargo/docker-compose.yml run --rm cargo-preprocess prepare-local-registry --force --pretty
```

- Maven can warm the shared `.m2` cache ahead of time, although lazy cache
  population also works:

```bash
docker compose -f resolving/containerization/docker-compose.yml run --rm \
  preprocess-maven warm \
  junit:junit:4.13.2 \
  --pretty
```

### 4. Check that a resolver is ready

`main.py` auto-selects the current container config, so you normally do not
need `--config`.

```bash
python3 main.py capabilities --ecosystem pip
python3 main.py health --ecosystem pip
```

## What Works Today

| Ecosystem | Commands | Formats | Typical setup |
| --- | --- | --- | --- |
| `pip` | `resolve`, `health`, `capabilities` | `graph` | works directly in `live` mode; `indexed` mode uses PostgreSQL table `pip_metadata` |
| `npm` | `resolve`, `health`, `capabilities` | `graph` | works directly in `online` mode; `indexed` mode uses PostgreSQL table `npm_metadata` |
| `maven` | `resolve`, `health`, `capabilities` | `graph` | uses shared `.m2` cache volume `resolver-maven-m2-cache` |
| `cargo` | `resolve`, `health`, `capabilities` | `graph`, `full` | requires preprocess-managed shared `local-registry` |
| `go` | `resolve`, `list`, `health`, `capabilities` | `graph`, `full` | works directly in `online` mode; `indexed` mode uses PostgreSQL table `go_metadata` |

Use `capabilities` when you want to confirm the live command set and feature
flags for a specific ecosystem.

## Core Commands

Inspect CLI help:

```bash
python3 main.py --help
python3 main.py resolve --help
python3 main.py health --help
python3 main.py capabilities --help
python3 main.py list --help
```

Resolve a graph:

```bash
python3 main.py resolve --ecosystem pip|npm|maven|cargo|go --name {package_identity} --version {version} --format graph
```

Check health:

```bash
python3 main.py health --ecosystem pip|npm|maven|cargo|go
```

Inspect capabilities:

```bash
python3 main.py capabilities --ecosystem pip|npm|maven|cargo|go
```

Run Go `list`:

```bash
python3 main.py list --ecosystem go --name github.com/rogpeppe/godef --version v1.1.2
```

Request raw backend output:

```bash
python3 main.py resolve --ecosystem pip|npm|maven|cargo|go --name {package_identity} --version {version} --format graph --return-raw
```

## Common Examples

### pip

Resolve with live metadata:

```bash
python3 main.py resolve --ecosystem pip --name requests --version 2.32.5 --format graph --pip-mode live
```

Resolve with indexed metadata:

```bash
python3 main.py resolve --ecosystem pip --name requests --version 2.32.5 --format graph --pip-mode indexed --pip-index-dsn 'postgresql://opendep:opendep@host.docker.internal:55432/opendep_preprocess' --pip-index-table pip_metadata
```

### npm

Resolve in online mode:

```bash
python3 main.py resolve --ecosystem npm --name left-pad --version 1.3.0 --format graph --npm-mode online
```

Resolve in indexed mode:

```bash
python3 main.py resolve --ecosystem npm --name left-pad --version 1.3.0 --format graph --npm-mode indexed --npm-index-dsn 'postgresql://opendep:opendep@host.docker.internal:55432/opendep_preprocess' --npm-index-table npm_metadata
```

### go

Resolve in online mode:

```bash
python3 main.py resolve --ecosystem go --name github.com/rogpeppe/godef --version v1.1.2 --format graph --go-mode online
```

Resolve in indexed mode:

```bash
python3 main.py resolve --ecosystem go --name github.com/rogpeppe/godef --version v1.1.2 --format graph --go-mode indexed --go-index-dsn 'postgresql://opendep:opendep@host.docker.internal:55432/opendep_preprocess' --go-index-table go_metadata
```

Run `list`:

```bash
python3 main.py list --ecosystem go --name github.com/rogpeppe/godef --version v1.1.2 --go-mode online
```

### maven

Resolve through the shared `.m2` cache:

```bash
python3 main.py resolve --ecosystem maven --name org.apache.logging.log4j:log4j-core --version 2.23.1 --format graph
```

### cargo

Check health after preparing the shared `local-registry`:

```bash
python3 main.py health --ecosystem cargo
```

Resolve a graph:

```bash
python3 main.py resolve --ecosystem cargo --name rand --version 0.8.5 --format graph
```

Resolve in `full` format:

```bash
python3 main.py resolve --ecosystem cargo --name rand --version 0.8.5 --format full
```

## Notes

- The first run can be slower because images, indexes, metadata, and caches may
  need to be populated.
- Maven uses the shared Docker volume `resolver-maven-m2-cache`.
- Cargo uses the shared volumes `resolver-cargo-home-cache` and
  `opendep-cargo-preprocess-data`.
- pip uses the named volume `resolver-pip-cache` for live-mode caching.
- npm and Go do not currently use dedicated named cache volumes.

## More Docs

- [pre-process/README.md](pre-process/README.md)
- [resolving/README.md](resolving/README.md)
