# Container Resolver Stack

`resolving/containerization/` is the Docker runtime layer for the OpenDep resolver stack.

## What It Does

This directory is responsible for:

- building resolver backend images
- providing adapter entrypoints for container execution
- wiring those images and adapters into named Compose services
- exposing the Docker-side execution path used by the resolver registry
- managing resolver-side caches and shared data mounts

## Request Path

The current container-backed execution path is:

```text
main.py
  -> resolver registry
  -> resolving/containerization/docker_gateway_proxy.py
  -> docker compose run <resolver-service>
  -> resolving/containerization/runtime/<ecosystem>_adapter.py
  -> resolving/containerization/images/<ecosystem>/
  -> normalized response payload
```

## Resolver Services

The current gateway-facing Compose services are:

| Ecosystem | Compose service | Commands | Formats | Mode or contract | Persistent data |
| --- | --- | --- | --- | --- | --- |
| `pip` | `resolver-pip` | `resolve`, `health`, `capabilities` | `graph` | `online`, `indexed` | named volume `resolver-pip-cache`; PostgreSQL only in `indexed` mode |
| `npm` | `resolver-npm` | `resolve`, `health`, `capabilities` | `graph` | `online`, `indexed` | PostgreSQL only in `indexed` mode |
| `maven` | `resolver-maven` | `resolve`, `health`, `capabilities` | `graph` | shared `.m2` cache | named volume `resolver-maven-m2-cache` |
| `cargo` | `resolver-cargo` | `resolve`, `health`, `capabilities` | `graph`, `full` | `online`, `indexed` | named volume `resolver-cargo-cache`, mounted as one shared Cargo data root |
| `go` | `resolver-go` | `resolve`, `list`, `health`, `capabilities` | `graph`, `full` | `online`, `indexed` | PostgreSQL only in `indexed` mode |

## Shared Data Contracts

- Maven uses the named volume `resolver-maven-m2-cache` mounted at `/root/.m2`. The shared repository root consumed by the resolver is `/root/.m2/repository`, and that cache can be warmed through [`pre-process/maven/README.md`](../../pre-process/maven/README.md).
- Cargo uses the named volume `resolver-cargo-cache` by default, mounted in the resolver at `/cargo-data`. That shared root contains `local-registry/` for `indexed` mode and `cargo-home/` for Cargo's normal network-backed cache in `online` mode. The volume name can still be overridden with `CARGO_DATA_VOLUME_NAME`.
- pip uses the named volume `resolver-pip-cache` mounted at `/resolver-pip-cache` for `online`-mode cache reuse. In `indexed` mode it reads from PostgreSQL table `pip_metadata`.
- npm does not currently use a dedicated named cache volume. In `indexed` mode it reads from PostgreSQL table `npm_metadata`.
- Go does not currently use a dedicated named cache volume. In `indexed` mode it reads from PostgreSQL table `go_metadata`.
