# OpenDep

OpenDep is a dependency analysis workspace centered on a unified resolver runtime.
The current active implementation lives under `resolving/` and is exposed through the repository-root `main.py` entrypoint.

## Repository layout

### `resolving/`

The active resolver subsystem.
It contains the gateway, resolver registry configuration, shared specification documents, and the container-backed runtime stack for supported ecosystems.

### `pre-process/`

A staging workspace for dependency dataset preprocessing and database-loading code.
It contains shared helpers plus ecosystem-specific directories for `pip`, `npm`, `maven`, `cargo`, and `go`.

### `main.py`

The main user-facing CLI entrypoint for resolver operations.
Use this file to query resolver capabilities, check backend health, resolve dependency graphs, and run supported list operations.

## Current resolver status

The actively integrated container-backed ecosystems are:

- `pip`
- `npm`
- `maven`
- `cargo`
- `go`

## How to run the resolver

### Prerequisites

Before running the resolver stack, make sure the host machine has:

- Python 3 available as `python3`
- Docker installed and the Docker daemon running
- Docker Compose available through `docker compose`
- Internet access for first-time dependency metadata fetches

### Build the resolver images

From the repository root, build the integrated resolver images:

```bash
docker compose -f resolving/containerization/docker-compose.yml build resolver-pip resolver-npm resolver-maven resolver-cargo resolver-go
```

If you prefer, you can also build all configured services:

```bash
docker compose -f resolving/containerization/docker-compose.yml build
```

### Inspect CLI help

The CLI help output reflects the current gateway and command structure:

```bash
python3 main.py --help
python3 main.py resolve --help
python3 main.py list --help
```

### Run basic health and capability checks

The root `main.py` command automatically selects the recommended resolver registry for the requested ecosystem.
In normal usage, you do not need to pass `--config` manually.

Check resolver capabilities.
In the shorthand below, `pip|go|npm|maven|cargo` means choose one ecosystem value:

```bash
python3 main.py capabilities --ecosystem pip|go|npm|maven|cargo
```

Check backend health:

```bash
python3 main.py health --ecosystem pip|go|npm|maven|cargo
```

### Resolve dependency graphs

In the shorthand below, `pip|go|npm|maven|cargo` means choose one ecosystem value.
Replace `{package_identity}` and `{version}` with values valid for the selected ecosystem.

```bash
python3 main.py resolve --ecosystem pip|go|npm|maven|cargo --name {package_identity} --version {version} --format graph
```

For pip, you can also switch between the online resolver path and the database-backed indexed path directly from `main.py`:

```bash
python3 main.py resolve --ecosystem pip --name requests --version 2.32.5 --format graph --pip-mode indexed --pip-index-dsn 'postgresql://opendep:opendep@host.docker.internal:55432/opendep_preprocess' --pip-index-table pip_metadata

python3 main.py resolve --ecosystem pip --name requests --version 2.32.5 --format graph --pip-mode live
```

For Go, you can also switch between the online resolver path and the database-backed indexed path directly from `main.py`:

```bash
python3 main.py resolve --ecosystem go --name github.com/rogpeppe/godef --version v1.1.2 --format graph --go-mode online

python3 main.py resolve --ecosystem go --name github.com/rogpeppe/godef --version v1.1.2 --format graph --go-mode indexed --go-index-dsn 'postgresql://opendep:opendep@host.docker.internal:55432/opendep_preprocess' --go-index-table go_metadata
```

The Go indexed path now falls back to the online proxy by default when a module row is missing from PostgreSQL.

For npm, you can now switch between the online resolver path and the database-backed indexed path directly from `main.py`:

```bash
python3 main.py resolve --ecosystem npm --name left-pad --version 1.3.0 --format graph --npm-mode online

python3 main.py resolve --ecosystem npm --name left-pad --version 1.3.0 --format graph --npm-mode indexed --npm-index-dsn 'postgresql://opendep:opendep@host.docker.internal:55432/opendep_preprocess' --npm-index-table npm_metadata
```

The npm indexed path keeps the native C++ resolver logic and serves packuments from PostgreSQL through an adapter-managed local HTTP shim.
When indexed data is missing, it falls back to the online registry by default.

### Run the Go `list` command

The `list` command is currently implemented for the Go resolver path.
You can use it in either `online` or `indexed` mode:

```bash
python3 main.py list --ecosystem go --name github.com/rogpeppe/godef --version v1.1.2 --go-mode online

python3 main.py list --ecosystem go --name github.com/rogpeppe/godef --version v1.1.2 --go-mode indexed --go-index-dsn 'postgresql://opendep:opendep@host.docker.internal:55432/opendep_preprocess' --go-index-table go_metadata
```

### Run the Maven command

```bash
python3 main.py resolve --ecosystem maven --name org.apache.logging.log4j:log4j-core --version 2.23.1
```

### Request raw backend output

When needed, preserve backend-native output with `--return-raw`:

```bash
python3 main.py resolve --ecosystem pip|go|npm|maven|cargo --name {package_identity} --version {version} --format graph --return-raw
```

## Runtime notes

- The first run can be significantly slower because backend images, indexes, metadata, and package caches may need to be populated.
- Maven uses a persistent Docker volume for `.m2` caching.
- Cargo uses a persistent Docker volume for `CARGO_HOME` caching.
- Cargo requires the shared preprocess-managed `local-registry` volume prepared by `pre-process/cargo`.
- pip uses a persistent Docker volume for resolver metadata and artifact caching in `live` mode.
- Backend behavior and supported commands are advertised through `capabilities`.
- The resolver registry files currently use JSON syntax while keeping the historical `.yaml` suffix.

## Where to read next

For more detailed subsystem documentation, continue with:

1. `resolving/README.md`
2. `resolving/spec/README.md`
3. `resolving/config/README.md`
4. `resolving/gateway/README.md`
5. `resolving/containerization/README.md`
