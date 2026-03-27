# Containerized resolving Stack

This directory contains the container-first runtime layer of the OpenDep resolver system.
It packages ecosystem-specific backends into Docker images, wraps them with runtime adapters, and exposes them to the gateway through Docker Compose services.

## Purpose

The `resolving/containerization/` directory is responsible for the containerized execution path of the resolver architecture.
Its responsibilities are:

- build and package ecosystem-specific backend images
- define the runtime adapters that translate gateway requests into backend executions
- wire those images and adapters into named Compose services
- provide the Docker-side execution path used by the gateway registry
- isolate language-specific toolchains and caches from the host machine

## Role in the end-to-end architecture

Within the OpenDep resolver flow, this directory sits between the gateway and the native backends.
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

- `resolving/containerization/docker-compose.yml` — Compose service definitions for the containerized resolvers
- `resolving/containerization/docker_gateway_proxy.py` — gateway-side Docker Compose launcher proxy
- `resolving/containerization/images/` — ecosystem-specific image definitions and native backend packaging
- `resolving/containerization/runtime/` — container-side runtime adapters used as service entrypoints

## Service map

The current Compose services are:

| Ecosystem | Compose service  | Image source                               | Runtime adapter                                       | Status |
| --------- | ---------------- | ------------------------------------------ | ----------------------------------------------------- | ------ |
| pip       | `resolver-pip`   | `resolving/containerization/images/pip/`   | `resolving/containerization/runtime/pip_adapter.py`   | Active |
| npm       | `resolver-npm`   | `resolving/containerization/images/npm/`   | `resolving/containerization/runtime/npm_adapter.py`   | Active |
| maven     | `resolver-maven` | `resolving/containerization/images/maven/` | `resolving/containerization/runtime/maven_adapter.py` | Active |
| cargo     | `resolver-cargo` | `resolving/containerization/images/cargo/` | `resolving/containerization/runtime/cargo_adapter.py` | Active |
| go        | `resolver-go`    | `resolving/containerization/images/go/`    | `resolving/containerization/runtime/go_adapter.py`    | Active |

## Integrated ecosystems

The currently active integrated container backends are:

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

## Gateway integration

The preferred user entrypoint remains the repository-root `main.py` file.
For integrated ecosystems, the gateway auto-selects the container registry defined in `resolving/config/resolvers.container.yaml`.
That registry points gateway requests to `resolving/containerization/docker_gateway_proxy.py`, which launches the matching Compose service.

## Caching and persistence

Some ecosystem services use persistent Docker volumes to improve repeated runs:

- Maven uses the named volume `resolver-maven-m2-cache` mounted at `/root/.m2`
- Cargo uses the named volume `resolver-cargo-home-cache` mounted at `/cargo-home`
- pip uses the named volume `resolver-pip-cache` mounted at `/resolver-pip-cache` for metadata and artifact caching in `live` mode
- Go does not currently use a dedicated named Docker cache volume
- npm currently relies on its packaged native backend and image-level build artifacts

## How to read this directory

If you are navigating this part of the repository, a good reading order is:

1. `resolving/containerization/images/README.md`
2. `resolving/containerization/runtime/README.md`
3. `resolving/containerization/docker-compose.yml`
4. `resolving/containerization/docker_gateway_proxy.py`

## Notes

- This directory is not the user-facing CLI entrypoint; `main.py` remains the top-level entry for resolver operations.
- The adapter layer is intentionally thin so that ecosystem-specific dependency semantics stay inside the native backend implementation.
- Build and direct image usage details are documented in each ecosystem README under `resolving/containerization/images/`.
