# resolving

This directory contains the resolver subsystem of OpenDep. It sits behind the repository-root `main.py` entrypoint and covers the request path from gateway dispatch to ecosystem-specific backend execution.

## Purpose

The resolver subsystem is responsible for:

- defining the shared request/response protocol
- selecting the correct backend for a requested ecosystem and command
- managing resolver registry files
- executing container resolvers through the gateway
- normalizing backend-native output into a common response model

## High-level architecture

A typical request flows through the resolver subsystem in the following order:

```text
main.py
  -> resolving/gateway/
  -> resolving/config/
  -> resolving/containerization/docker_gateway_proxy.py
  -> docker compose run <resolver-service>
  -> resolving/containerization/runtime/<ecosystem>_adapter.py
  -> resolving/containerization/images/<ecosystem>/
  -> normalized response
```

## Directory map

### `resolving/gateway/`

The host-side orchestration layer. It validates incoming requests, selects the correct resolver from the registry, runs the configured launcher, and normalizes the backend response.

### `resolving/config/`

Primary resolver registry definitions. These files declare which backend handles each ecosystem, how it is launched, and which capabilities are exposed before backend startup.

### `resolving/containerization/`

The container resolver stack. This subtree contains Docker Compose wiring, runtime adapters, and ecosystem-specific image definitions for integrated resolvers.

### `resolving/spec/`

The shared request/response protocol. This directory documents the request schema, response schema, error taxonomy, result model, and sample request/response payloads.

## Current ecosystems

The current resolver matrix from the primary registry [`resolving/config/resolvers.container.yaml`](config/resolvers.container.yaml) is:

| Ecosystem | Commands | Formats | Current runtime contract |
| --- | --- | --- | --- |
| `pip` | `resolve`, `health`, `capabilities` | `graph` | `live` or `indexed` metadata, with PostgreSQL-backed `pip_metadata` in indexed mode |
| `npm` | `resolve`, `health`, `capabilities` | `graph` | `online` or `indexed` metadata, with PostgreSQL-backed `npm_metadata` served through an adapter-managed local HTTP shim in indexed mode |
| `maven` | `resolve`, `health`, `capabilities` | `graph` | shared `.m2` cache contract through `resolver-maven-m2-cache` |
| `cargo` | `resolve`, `health`, `capabilities` | `graph`, `full` | preprocess-managed shared Cargo `local-registry` plus persistent Cargo home cache |
| `go` | `resolve`, `list`, `health`, `capabilities` | `graph`, `full` | `online` or `indexed` metadata, with PostgreSQL-backed `go_metadata` in indexed mode |

## Recommended reading order

If you are new to this subtree, a good reading order is:

1. `resolving/spec/README.md`
2. `resolving/config/README.md`
3. `resolving/gateway/README.md`
4. `resolving/containerization/README.md`