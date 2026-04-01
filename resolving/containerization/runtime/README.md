# resolving Runtime Adapters

This directory contains the container runtime adapters used by the OpenDep
resolver stack. These adapters bridge the gateway request model and the
backend binaries, jars, or runtime modules packaged by
`resolving/containerization/images/`.

## Purpose

The files in `resolving/containerization/runtime/` make up the container-facing
execution layer. In practice, each adapter:

- reads a normalized request payload from standard input
- handles shared commands such as `health` and `capabilities`
- validates or translates ecosystem-specific request options
- invokes the native backend packaged in the corresponding image
- captures stdout, stderr, timing, and exit status
- normalizes backend-native output into the shared response model

These adapters are not user-facing entrypoints. They are typically invoked by
the `docker compose` services defined in
`resolving/containerization/docker-compose.yml`.

## Relationship to adjacent directories

Within the container resolver stack:

- `resolving/containerization/images/` builds the native backend images
- `resolving/containerization/runtime/` provides the adapter entrypoints that run inside those images
- `resolving/containerization/docker-compose.yml` selects one adapter per service as the container entrypoint
- `resolving/config/` stores resolver registry files used by the gateway
- `resolving/spec/` documents the shared request/response protocol used by the gateway and adapters
- `main.py` and the gateway call the services through the resolver registry and Docker proxy

## Directory structure

Current adapter files:

- `resolving/containerization/runtime/pip_adapter.py` — adapter for the Python pip backend
- `resolving/containerization/runtime/npm_adapter.py` — adapter for the native npm C++ backend
- `resolving/containerization/runtime/maven_adapter.py` — adapter for the native Maven Java backend
- `resolving/containerization/runtime/cargo_adapter.py` — adapter for the native Cargo Rust backend
- `resolving/containerization/runtime/go_adapter.py` — adapter for the native Go backend
- `resolving/containerization/runtime/default_adapter.py` — generic placeholder adapter kept for future incomplete integrations

## Current Adapter Alignment

| Adapter | Supported commands | Mode or contract | Current handoff behavior |
| --- | --- | --- | --- |
| `pip_adapter.py` | `resolve`, `health`, `capabilities` | `live`, `indexed` | launches the Python backend module and reads PostgreSQL only in `indexed` mode |
| `npm_adapter.py` | `resolve`, `health`, `capabilities` | `online`, `indexed` | launches the native C++ backend and starts a local HTTP shim in `indexed` mode |
| `maven_adapter.py` | `resolve`, `health`, `capabilities` | shared `.m2` cache contract | launches the resolver jar against the shared Maven cache |
| `cargo_adapter.py` | `resolve`, `health`, `capabilities` | shared preprocess-managed `local-registry` contract | validates the staged Cargo registry mount and fails fast when it is absent or incomplete |
| `go_adapter.py` | `resolve`, `list`, `health`, `capabilities` | `online`, `indexed` | launches the Go backend for graph or build-list style output |
| `default_adapter.py` | generic shared commands only | placeholder wiring | not used by the current five active ecosystems |

## Adapter responsibilities

### `pip_adapter.py`

This adapter launches the Python pip backend module, reports health for the
Python runtime, backend module, metadata mode, and indexed-store
configuration, and normalizes backend graph output into the shared response
model. It exposes `resolve`, `health`, and `capabilities`.
In `indexed` mode it reads from PostgreSQL `pip_metadata`; indexed fallback to `live` metadata is optional and disabled by default.

### `npm_adapter.py`

This adapter wraps the native npm resolver binary and converts its
backend-native output into the normalized graph response model. It exposes
`resolve`, `health`, and `capabilities` in both `online` and `indexed` modes.
In `indexed` mode it starts a local HTTP shim backed by PostgreSQL so the
native C++ backend can keep consuming raw packuments over HTTP without
learning direct database access.
Indexed fallback to the online registry is enabled by default.

### `maven_adapter.py`

This adapter launches the Maven resolver jar, converts Maven coordinates into
the backend call format, and normalizes the returned graph payload. It also
reports health for the Python runtime and the installed backend artifact.
It exposes `resolve`, `health`, and `capabilities` and relies on the shared
`.m2` cache contract rather than a resolver-side mode switch.

### `cargo_adapter.py`

This adapter invokes the native Rust backend binary, exposes Cargo-specific
capability metadata, and reports health for the backend binary, Cargo home,
and registry mode. It exposes `resolve`, `health`, and `capabilities`,
normalizes Cargo backend output, and validates the preprocess-managed
`local-registry` mount before backend execution.

### `go_adapter.py`

This adapter wraps the Go backend binary and exposes both `resolve` and
`list`. It handles Go-specific output normalization for graph and build-list
results and reports health for the Go proxy and backend binary. It supports
both `online` and `indexed` modes, and indexed fallback to the Go proxy is
enabled by default.

### `default_adapter.py`

This adapter is a generic placeholder for ecosystems that are wired into the
container stack before a real backend exists. It supports common commands and
returns a structured configuration error for backend operations that are not
yet implemented. It is not on the active request path for `pip`, `npm`,
`maven`, `cargo`, or `go`.

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

Those helpers centralize request parsing, shared response generation, and graph
normalization logic for container adapters.

## Operational notes

- Adapter configuration is driven primarily by environment variables injected by `resolving/containerization/docker-compose.yml`.
- The adapter layer is intentionally thin; the native backend remains the source of ecosystem-specific dependency semantics.
- Health and capability responses are expected to work even when a backend resolution request would fail.
- The currently advertised commands and features are declared in `resolving/config/resolvers.container.yaml`; the adapters implement the container-side behavior behind those registry entries.
