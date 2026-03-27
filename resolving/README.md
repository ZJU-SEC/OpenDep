# resolving

This directory contains the resolver subsystem of OpenDep.
It is the implementation layer behind the repository-root `main.py` entrypoint and provides the full request path from gateway dispatch to ecosystem-specific backend execution.

## Purpose

The `resolving/` tree is responsible for:

- defining the shared request and response protocol used by resolver operations
- selecting the correct backend for a requested ecosystem and command
- managing resolver registry configuration
- executing container-backed ecosystem resolvers through the gateway
- normalizing backend-native output into a common response model

In the current structure, users interact with the repository-root `main.py`, while the code in `resolving/` provides the supporting implementation.

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

The host-side orchestration layer.
It validates incoming requests, selects the correct resolver from the registry, runs the configured launcher, and normalizes the backend response.

### `resolving/config/`

resolving registry definitions.
These files declare which backend handles each ecosystem, how it is launched, and which capabilities are exposed before backend startup.

### `resolving/containerization/`

The container-backed execution stack.
This subtree contains Docker Compose wiring, runtime adapters, and ecosystem-specific image definitions for integrated resolvers.

### `resolving/spec/`

The shared wire specification.
This directory documents the request schema, response schema, error taxonomy, result model, and sample request/response payloads.

## Current ecosystems

The actively integrated container-backed ecosystems are:

- `npm`
- `maven`
- `cargo`
- `go`

A placeholder `pip` service still exists in the container stack for wiring and future backend replacement.

## Relationship to `main.py`

The repository-root `main.py` is the intended user-facing CLI entrypoint.
It imports the gateway from this directory and automatically selects the recommended resolver registry for the requested ecosystem unless a custom registry path is provided.

That means:

- `resolving/` is not a separate end-user CLI directory
- `resolving/gateway/` is an internal implementation layer
- `resolving/config/` and `resolving/spec/` support the runtime and contract model
- `resolving/containerization/` contains the current backend integration strategy

## Recommended reading order

If you are new to this subtree, a good reading order is:

1. `resolving/spec/README.md`
2. `resolving/config/README.md`
3. `resolving/gateway/README.md`
4. `resolving/containerization/README.md`

## Notes

- The current resolver stack is container-first for the actively integrated ecosystems.
- Registry files currently use JSON syntax while keeping the historical `.yaml` suffix.
- The gateway-level request and response validation logic currently lives in `resolving/gateway/contract.py`.
