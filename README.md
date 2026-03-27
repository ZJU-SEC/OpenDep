# OpenDep

OpenDep is a dependency analysis workspace centered on a unified resolver runtime.
The current active implementation lives under `resolving/` and is exposed through the repository-root `main.py` entrypoint.

## Repository layout

### `resolving/`

The active resolver subsystem.
It contains the gateway, resolver registry configuration, shared specification documents, and the container-backed runtime stack for supported ecosystems.

### `Crawler/`

A placeholder directory for future crawler-related work.
It is not part of the active runtime path today.

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

For pip, you can also switch metadata mode directly from `main.py`:

```bash
python3 main.py resolve --ecosystem pip --name requests --version 2.32.5 --format graph --pip-mode live
python3 main.py resolve --ecosystem pip --name requests --version 2.32.5 --format graph --pip-mode indexed --pip-index-dsn 'postgresql://opendep:opendep@host.docker.internal:55432/opendep_preprocess' --pip-index-table pip_projects_metadata
```

### Run the Go `list` command

The `list` command is currently implemented for the Go resolver path.
Replace `{package_identity}` and `{version}` with Go module values:

```bash
python3 main.py list --ecosystem go --name {package_identity} --version {version}
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
