# Container Resolver Stack

This directory contains the container runtime layer of the OpenDep resolver
system. It packages ecosystem-specific backends into Docker images, wraps them
with runtime adapters, and exposes them to the gateway through Docker Compose
services.

## Purpose

The `resolving/containerization/` directory owns the container execution path
of the resolver architecture. Its responsibilities are:

- build and package ecosystem-specific backend images
- define the runtime adapters that translate gateway requests into backend executions
- wire those images and adapters into named Compose services
- provide the Docker-side execution path used by the resolver registry
- isolate language-specific toolchains and caches from the host machine

## Role in the end-to-end architecture

Within the OpenDep resolver flow, this directory sits between the gateway and
the native backends.
The typical execution path is:

```text
main.py
  -> resolver registry
  -> resolving/containerization/docker_gateway_proxy.py
  -> docker compose run <service>
  -> resolving/containerization/runtime/<ecosystem>_adapter.py
  -> native backend packaged by resolving/containerization/images/<ecosystem>/
  -> normalized response payload
```

## Directory structure

Key contents:

- `resolving/containerization/docker-compose.yml` — Compose service definitions for the container stack
- `resolving/containerization/docker_gateway_proxy.py` — gateway-side Docker Compose launcher proxy
- `resolving/containerization/images/` — ecosystem-specific image definitions and native backend packaging
- `resolving/containerization/runtime/` — container-side runtime adapters used as service entrypoints

## Service map

The current gateway-facing Compose services are:

| Ecosystem | Compose service | Gateway commands | Runtime mode or contract | Persistent data |
| --- | --- | --- | --- | --- |
| `pip` | `resolver-pip` | `resolve`, `health`, `capabilities` | `live` or `indexed` metadata | named volume `resolver-pip-cache`; PostgreSQL only in `indexed` mode |
| `npm` | `resolver-npm` | `resolve`, `health`, `capabilities` | `online` or `indexed` metadata | no dedicated named cache volume; PostgreSQL only in `indexed` mode |
| `maven` | `resolver-maven` | `resolve`, `health`, `capabilities` | shared `.m2` cache contract | named volume `resolver-maven-m2-cache` |
| `cargo` | `resolver-cargo` | `resolve`, `health`, `capabilities` | preprocess-managed shared `local-registry` | named volumes `resolver-cargo-home-cache` and `opendep-cargo-preprocess-data` |
| `go` | `resolver-go` | `resolve`, `list`, `health`, `capabilities` | `online` or `indexed` metadata | no dedicated named cache volume; PostgreSQL only in `indexed` mode |

The same compose file also includes one companion preprocess service:

| Service | Role | Shared contract |
| --- | --- | --- |
| `preprocess-maven` | warms Maven metadata before resolver runs | shares `resolver-maven-m2-cache` with `resolver-maven` |

## Integrated ecosystems

The current container stack covers:

- `pip`
- `npm`
- `maven`
- `cargo`
- `go`

## Runtime model

This directory intentionally separates the container stack into two layers:

### Images layer

The `resolving/containerization/images/` subtree owns the build logic and native backend packaging for each ecosystem.
That layer is responsible for producing runnable backend images.

### Runtime adapter layer

The `resolving/containerization/runtime/` subtree owns the container entrypoint logic.
Each adapter reads the normalized gateway request, handles shared commands such as `health` and `capabilities`, invokes the native backend, and emits a normalized response.

The active adapter-side mode split is:

- `pip`: `live` and `indexed`
- `npm`: `online` and `indexed`
- `go`: `online` and `indexed`
- `maven`: shared `.m2` cache contract, no CLI mode flag
- `cargo`: shared preprocess-managed `local-registry` contract, no CLI mode flag

## Gateway integration

The preferred user entrypoint remains the repository-root `main.py` file.
For integrated ecosystems, the gateway auto-selects the primary registry
defined in `resolving/config/resolvers.container.yaml`.
That registry points gateway requests to `resolving/containerization/docker_gateway_proxy.py`, which launches the matching Compose service.

## Caching and persistence

Some ecosystem services use persistent Docker volumes to improve repeated runs:

- Maven uses the named volume `resolver-maven-m2-cache` mounted at `/root/.m2`.
  The companion `preprocess-maven` service and `resolver-maven` both reuse that same volume.
- Cargo uses the named volume `resolver-cargo-home-cache` mounted at `/cargo-home` and the read-only preprocess metadata volume `opendep-cargo-preprocess-data` mounted at `/cargo-preprocess-data`.
- pip uses the named volume `resolver-pip-cache` mounted at `/resolver-pip-cache` for metadata and artifact caching in `live` mode.
- npm does not currently use a dedicated named cache volume, but `indexed` mode reads from PostgreSQL and `online` mode uses the configured registry base URL at request time.
- Go does not currently use a dedicated named Docker cache volume, but `indexed` mode reads from PostgreSQL and `online` mode uses the configured Go proxy at request time.

## How to read this directory

If you are navigating this part of the repository, a good reading order is:

1. `resolving/containerization/images/README.md`
2. `resolving/containerization/runtime/README.md`
3. `resolving/containerization/docker-compose.yml`
4. `resolving/containerization/docker_gateway_proxy.py`

## Notes

- This directory is not the user-facing CLI entrypoint; `main.py` remains the
  top-level entry for resolver operations.
- The adapter layer is intentionally thin so that ecosystem-specific dependency semantics stay inside the native backend implementation.
- Build and direct image usage details live in the ecosystem READMEs under
  `resolving/containerization/images/`.
