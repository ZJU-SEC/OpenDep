# OpenDep

OpenDep provides a Docker-based dependency resolver CLI through
`python3 main.py`.

## Prerequisites

Before running the resolver, make sure the host machine has:

- Python 3 available as `python3`
- Docker installed and the Docker daemon running
- Docker Compose available through `docker compose`
- Internet access for image builds, preprocess jobs, and `online` resolver runs

## One-Time Setup

Build the resolver images:

```bash
docker compose -f resolving/containerization/docker-compose.yml build
```

Start shared PostgreSQL if you plan to use indexed `pip`, `npm`, or `go`:

```bash
docker compose \
  --env-file pre-process/common/database/.env.example \
  -f pre-process/common/database/docker-compose.yml \
  up -d
```

Use one shared DSN for the indexed examples below:

```bash
export INDEX_DSN='postgresql://opendep:opendep@host.docker.internal:55432/opendep_preprocess'
```

Prepare the shared Cargo data volume only if you plan to use `cargo` in
`indexed` mode:

```bash
docker compose -f pre-process/cargo/docker-compose.yml build cargo-preprocess
docker compose -f pre-process/cargo/docker-compose.yml run --rm cargo-preprocess clone --pretty
docker compose -f pre-process/cargo/docker-compose.yml run --rm cargo-preprocess prepare-local-registry --force --pretty
```

Warm the shared Maven `.m2` cache only if you want Maven data prepared ahead of
time. The resolver can also populate that cache lazily:

```bash
docker compose -f pre-process/maven/docker-compose.yml build maven-preprocess
docker compose -f pre-process/maven/docker-compose.yml run --rm \
  maven-preprocess warm \
  org.apache.logging.log4j:log4j-core:2.23.1 \
  --pretty
```

Check that a resolver is reachable:

```bash
python3 main.py capabilities --ecosystem pip
python3 main.py health --ecosystem pip
```

## Ecosystem Support

| Ecosystem | Modes | Commands | Formats | Indexed contract |
| --- | --- | --- | --- | --- |
| `pip` | `online`, `indexed` | `resolve`, `health`, `capabilities` | `graph` | PostgreSQL table `pip_metadata` |
| `npm` | `online`, `indexed` | `resolve`, `health`, `capabilities` | `graph` | PostgreSQL table `npm_metadata` |
| `go` | `online`, `indexed` | `resolve`, `list`, `health`, `capabilities` | `graph`, `full` | PostgreSQL table `go_metadata` |
| `cargo` | `online`, `indexed` | `resolve`, `health`, `capabilities` | `graph`, `full` | shared `local-registry/` inside Docker volume `resolver-cargo-cache` |
| `maven` | shared-cache mode only | `resolve`, `health`, `capabilities` | `graph` | shared `.m2` cache volume `resolver-maven-m2-cache` |

## Complete Examples

### pip

Online resolve:

```bash
python3 main.py resolve --ecosystem pip --name requests --version 2.32.5 --format graph --pip-mode online
```

Indexed preprocess:

```bash
docker compose -f pre-process/pip/docker-compose.yml build pip-preprocess
docker compose -f pre-process/pip/docker-compose.yml run --rm pip-preprocess \
  build \
  --project requests==2.32.5 \
  --pretty
```

Indexed resolve:

```bash
python3 main.py resolve --ecosystem pip --name requests --version 2.32.5 --format graph --pip-mode indexed --pip-index-dsn "$INDEX_DSN" --pip-index-table pip_metadata
```

### npm

Online resolve:

```bash
python3 main.py resolve --ecosystem npm --name left-pad --version 1.3.0 --format graph --npm-mode online
```

Indexed preprocess:

```bash
docker compose -f pre-process/npm/docker-compose.yml build npm-preprocess
docker compose -f pre-process/npm/docker-compose.yml run --rm npm-preprocess \
  build \
  --package left-pad \
  --pretty
```

Indexed resolve:

```bash
python3 main.py resolve --ecosystem npm --name left-pad --version 1.3.0 --format graph --npm-mode indexed --npm-index-dsn "$INDEX_DSN" --npm-index-table npm_metadata
```

### go

Online resolve:

```bash
python3 main.py resolve --ecosystem go --name github.com/rogpeppe/godef --version v1.1.2 --format graph --go-mode online
```

Indexed preprocess:

```bash
docker compose -f pre-process/go/docker-compose.yml build go-preprocess
docker compose -f pre-process/go/docker-compose.yml run --rm go-preprocess \
  build \
  --module github.com/rogpeppe/godef@v1.1.2 \
  --pretty
```

Indexed resolve:

```bash
python3 main.py resolve --ecosystem go --name github.com/rogpeppe/godef --version v1.1.2 --format graph --go-mode indexed --go-index-dsn "$INDEX_DSN" --go-index-table go_metadata
```

Optional Go `list` example:

```bash
python3 main.py list --ecosystem go --name github.com/rogpeppe/godef --version v1.1.2 --go-mode online
```

### cargo

Online resolve:

```bash
python3 main.py resolve --ecosystem cargo --name rand --version 0.8.5 --format graph --cargo-mode online
```

Indexed preprocess:

```bash
docker compose -f pre-process/cargo/docker-compose.yml build cargo-preprocess
docker compose -f pre-process/cargo/docker-compose.yml run --rm cargo-preprocess clone --pretty
docker compose -f pre-process/cargo/docker-compose.yml run --rm cargo-preprocess prepare-local-registry --force --pretty
```

Indexed resolve:

```bash
python3 main.py resolve --ecosystem cargo --name rand --version 0.8.5 --format graph --cargo-mode indexed
```

Optional Cargo `full` format example:

```bash
python3 main.py resolve --ecosystem cargo --name rand --version 0.8.5 --format full --cargo-mode indexed
```

### maven

Maven does not expose an `online` / `indexed` switch. It always resolves
through the shared `.m2` cache contract.

Cache warm-up:

```bash
docker compose -f pre-process/maven/docker-compose.yml build maven-preprocess
docker compose -f pre-process/maven/docker-compose.yml run --rm \
  maven-preprocess warm \
  org.apache.logging.log4j:log4j-core:2.23.1 \
  --pretty
```

Resolve:

```bash
python3 main.py resolve --ecosystem maven --name org.apache.logging.log4j:log4j-core --version 2.23.1 --format graph
```

## Useful Commands

Inspect CLI help:

```bash
python3 main.py --help
python3 main.py resolve --help
python3 main.py health --help
python3 main.py capabilities --help
python3 main.py list --help
```

Request raw backend output:

```bash
python3 main.py resolve --ecosystem pip --name requests --version 2.32.5 --format graph --return-raw
```

## More Docs

- [pre-process/README.md](pre-process/README.md)
- [resolving/README.md](resolving/README.md)

## License

This project is licensed under the Apache License 2.0. See gg[`LICENSE`](LICENSE) for details.
