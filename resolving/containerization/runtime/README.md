# resolving Runtime Adapters

This directory contains the container-side runtime adapters used by the OpenDep resolver stack.
These adapters are the protocol bridge between the gateway request model and the native backend binaries, jars, or placeholder runtimes packaged in `resolving/containerization/images/`.

## Purpose

The files in `resolving/containerization/runtime/` are responsible for the container-facing execution layer.
In practice, each adapter:

- reads a normalized request payload from standard input
- handles shared commands such as `health` and `capabilities`
- validates or translates ecosystem-specific request options
- invokes the native backend packaged in the corresponding image
- captures stdout, stderr, timing, and exit status
- normalizes backend-native output into the shared gateway response model

These adapters are not intended to be direct user-facing entrypoints.
They are typically invoked by `docker compose` services defined in `resolving/containerization/docker-compose.yml`.

## Relationship to adjacent directories

Within the containerized resolver stack:

- `resolving/containerization/images/` builds the native backend images
- `resolving/containerization/runtime/` provides the adapter entrypoints that run inside those images
- `resolving/containerization/docker-compose.yml` selects one adapter per service as the container entrypoint
- `resolving/config/` stores resolver registry files used by the gateway
- `resolving/spec/` documents the shared wire protocol used by the gateway and adapters
- `main.py` and the gateway call the services through the resolver registry and Docker proxy

## Directory structure

Current adapter files:

- `resolving/containerization/runtime/pip_adapter.py` — adapter for the Python pip backend
- `resolving/containerization/runtime/npm_adapter.py` — adapter for the native npm C++ backend
- `resolving/containerization/runtime/maven_adapter.py` — adapter for the native Maven Java backend
- `resolving/containerization/runtime/cargo_adapter.py` — adapter for the native Cargo Rust backend
- `resolving/containerization/runtime/go_adapter.py` — adapter for the native Go backend
- `resolving/containerization/runtime/default_adapter.py` — generic placeholder adapter kept for future incomplete integrations

## Adapter responsibilities

### `pip_adapter.py`

This adapter launches the Python pip backend module, reports health for the Python runtime, backend module, metadata mode, and indexed-store configuration, and normalizes backend graph output into the shared response model.
It also supports raw stdout/stderr preservation and timeout/error mapping consistent with the other container-backed ecosystems.

### `npm_adapter.py`

This adapter wraps the native npm resolver binary and converts its backend-native output into the normalized graph response model.
It now supports both `online` and `indexed` metadata modes.
In `indexed` mode it starts a local HTTP shim backed by PostgreSQL so the native C++ backend can keep consuming raw packuments over HTTP without learning direct database access.

### `maven_adapter.py`

This adapter launches the Maven resolver jar, converts Maven coordinates into the backend call format, and normalizes the returned graph payload.
It also reports health information for the Python runtime and the installed Maven backend artifact.

### `cargo_adapter.py`

This adapter invokes the native Rust backend binary, exposes Cargo-specific capability metadata, and reports health information about the backend binary, Cargo home, and registry mode.
It normalizes Cargo backend output into the shared graph model.

### `go_adapter.py`

This adapter wraps the Go backend binary and exposes both `resolve` and `list` operations.
It handles Go-specific output normalization for graph and build-list style results and reports health information for the Go proxy and backend binary.

### `default_adapter.py`

This adapter is a generic placeholder for ecosystems that are wired into the container stack before a real backend exists.
It supports common commands and returns a structured configuration error for backend operations that are not yet implemented.

## Common runtime pattern

Most adapters in this directory follow the same lifecycle:

1. construct `AdapterMetadata`
2. load a request from standard input
3. handle shared commands through helper utilities
4. run the backend process only when a backend-specific command is needed
5. convert backend-native output into the shared response schema
6. emit the final response payload to standard output

## Shared dependencies

The adapters in this directory rely on shared helper modules that now live alongside the adapters:

- `resolving/containerization/runtime/adapter_runtime.py`
- `resolving/containerization/runtime/launcher_normalization.py`

Those helpers centralize request parsing, shared response generation, and graph normalization logic for container-backed adapters.

## Operational notes

- Adapter configuration is driven primarily by environment variables injected by `resolving/containerization/docker-compose.yml`.
- The adapter layer is intentionally thin; the native backend remains the source of ecosystem-specific dependency semantics.
- Health and capability responses are expected to work even when a backend resolution request would fail.
- Placeholder adapters are useful for wiring validation, but they should not be treated as completed backend integrations.
