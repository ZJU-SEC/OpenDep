# Architecture

**Analysis Date:** 2026-03-18

## Pattern Overview

**Overall:** Registry-driven layered CLI that dispatches resolver requests through a Python gateway into container-backed, ecosystem-specific native backends.

**Key Characteristics:**
- Use `main.py` as the only user-facing entrypoint. It parses CLI arguments, builds the request envelope, selects a registry file, and prints the final normalized JSON response.
- Keep orchestration in `resolving/gateway/`. The gateway validates requests, chooses a resolver from the registry, launches a subprocess, and normalizes the adapter response.
- Keep backend selection declarative in `resolving/config/resolvers.container.yaml` and `resolving/config/resolvers.yaml`. The runtime path is controlled by registry entries, not by hard-coded ecosystem branching in `main.py`.
- Keep protocol normalization at the adapter boundary. Files in `resolving/containerization/runtime/` convert backend-native output into the shared graph-oriented response contract documented in `resolving/spec/`.
- Keep dependency-resolution semantics inside ecosystem-owned backend code under `resolving/containerization/images/`, not in the gateway.
- Treat `Crawler/` and `.legacy/Crawler/` as outside the active resolver path. The active runtime does not import or launch code from those directories.

## Layers

**CLI Entry Layer:**
- Purpose: Accept command-line arguments and convert them into the shared request envelope.
- Location: `main.py`
- Contains: `argparse` setup, request assembly, registry selection, and process exit status mapping.
- Depends on: `resolving/gateway/config.py`, `resolving/gateway/registry.py`, `resolving/gateway/service.py`
- Used by: End users and shell automation.

**Protocol and Contract Layer:**
- Purpose: Define and enforce the request and response shape shared across the CLI, gateway, and adapters.
- Location: `resolving/spec/`, `resolving/gateway/contract.py`
- Contains: JSON schema references in `resolving/spec/request.schema.json` and `resolving/spec/response.schema.json`, sample payloads in `resolving/spec/examples/`, and executable validation in `resolving/gateway/contract.py`.
- Depends on: Plain JSON payloads only.
- Used by: `main.py`, `resolving/gateway/service.py`, `resolving/gateway/response.py`, and `resolving/containerization/runtime/adapter_runtime.py`.

**Registry and Configuration Layer:**
- Purpose: Map ecosystems to launch commands, working directories, timeouts, and advertised capabilities.
- Location: `resolving/config/`, `resolving/gateway/config.py`, `resolving/gateway/registry.py`
- Contains: Active container registry in `resolving/config/resolvers.container.yaml`, legacy host-process registry in `resolving/config/resolvers.yaml`, path resolution and placeholder expansion in `resolving/gateway/config.py`, and lookup logic in `resolving/gateway/registry.py`.
- Depends on: Repository-relative file paths and current process environment.
- Used by: `main.py`, `resolving/gateway/router.py`, `resolving/gateway/runner.py`.

**Gateway Orchestration Layer:**
- Purpose: Enforce gateway-level rules before launching a backend and convert failures into the shared error envelope.
- Location: `resolving/gateway/`
- Contains: `GatewayService` in `resolving/gateway/service.py`, `GatewayDispatcher` in `resolving/gateway/dispatcher.py`, route checks in `resolving/gateway/router.py`, subprocess execution in `resolving/gateway/runner.py`, error types in `resolving/gateway/errors.py`, and response normalization in `resolving/gateway/response.py`.
- Depends on: The contract layer, the registry layer, and subprocess execution.
- Used by: `main.py`.

**Container Launch Layer:**
- Purpose: Bridge host-side gateway execution into a named Docker Compose service without teaching the gateway Docker details.
- Location: `resolving/containerization/docker_gateway_proxy.py`, `resolving/containerization/docker-compose.yml`
- Contains: Docker Compose command assembly, stdin/stdout proxying, service definitions, persistent volume declarations, and environment injection for adapters.
- Depends on: Docker Compose, registry-selected service names, and the repository root as working directory.
- Used by: Registry commands in `resolving/config/resolvers.container.yaml`.

**Adapter Layer:**
- Purpose: Translate the shared request envelope into backend-specific CLI invocations and normalize backend-native output back into the shared response shape.
- Location: `resolving/containerization/runtime/`
- Contains: Shared adapter helpers in `resolving/containerization/runtime/adapter_runtime.py` and `resolving/containerization/runtime/launcher_normalization.py`, plus ecosystem adapters in `resolving/containerization/runtime/npm_adapter.py`, `resolving/containerization/runtime/maven_adapter.py`, `resolving/containerization/runtime/cargo_adapter.py`, `resolving/containerization/runtime/go_adapter.py`, and placeholder support in `resolving/containerization/runtime/default_adapter.py`.
- Depends on: The contract layer, environment variables from `resolving/containerization/docker-compose.yml`, and native binaries or jars inside the container image.
- Used by: Docker Compose service entrypoints.

**Native Backend Layer:**
- Purpose: Execute ecosystem-specific dependency-resolution logic with the toolchain and data model native to that ecosystem.
- Location: `resolving/containerization/images/`
- Contains: Go backend command and packages in `resolving/containerization/images/go/cmd/go_resolver/main.go` and `resolving/containerization/images/go/internal/`, Rust backend code in `resolving/containerization/images/cargo/src/`, Java backend code in `resolving/containerization/images/maven/src/main/java/`, C++ backend code in `resolving/containerization/images/npm/src/`, and placeholder image wiring in `resolving/containerization/images/pip/`.
- Depends on: Language-specific toolchains and upstream package metadata sources.
- Used by: Runtime adapters in `resolving/containerization/runtime/`.

**Legacy and Archive Layer:**
- Purpose: Preserve earlier crawler implementations without coupling them to the active resolver runtime.
- Location: `Crawler/`, `.legacy/Crawler/`
- Contains: Placeholder guidance in `Crawler/README.md` and archived language-specific crawlers in `.legacy/Crawler/go-dependency-crawler/`, `.legacy/Crawler/js-dependency-crawler/`, `.legacy/Crawler/maven-dependency-crawler/`, `.legacy/Crawler/pip-dependency-crawler/`, and `.legacy/Crawler/cargo-dependency-crawler/`.
- Depends on: Their own historical databases and toolchains.
- Used by: No active imports from `main.py` or `resolving/`.

## Data Flow

**Resolve Request Flow:**

1. `main.py` parses `resolve`, `list`, `health`, or `capabilities`, then builds a request envelope with `schema_version`, `request_id`, `trace_id`, `ecosystem`, `package`, and `options`.
2. `main.py` asks `resolving/gateway/config.py` for `default_config_path()` and loads the selected registry through `resolving/gateway/registry.py`.
3. `resolving/gateway/service.py` validates the request with `resolving/gateway/contract.py`.
4. `resolving/gateway/dispatcher.py` asks `resolving/gateway/router.py` to select and validate the resolver entry for the requested ecosystem and command.
5. `resolving/gateway/runner.py` launches the registry-provided command. For active ecosystems, that command is `resolving/containerization/docker_gateway_proxy.py`.
6. `resolving/containerization/docker_gateway_proxy.py` forwards the JSON request to `docker compose run --rm --no-deps -T <service>` using `resolving/containerization/docker-compose.yml`.
7. The selected adapter in `resolving/containerization/runtime/` reads stdin, short-circuits common commands if possible, or spawns the native backend from `resolving/containerization/images/<ecosystem>/`.
8. The adapter maps backend stdout, stderr, exit code, and parsed payload into the shared response envelope with helpers from `resolving/containerization/runtime/adapter_runtime.py`.
9. `resolving/gateway/response.py` validates the adapter JSON again, injects `raw` output when `return_raw` is enabled, and returns the normalized payload to `main.py`.
10. `main.py` prints the final JSON response and exits with `0` for `"status": "ok"` and `1` otherwise.

**Health and Capabilities Flow:**

1. `main.py` builds the same request envelope for `health` or `capabilities`.
2. The gateway still routes through the registry, proxy, and selected adapter.
3. `resolving/containerization/runtime/adapter_runtime.py` handles those commands before the adapter launches the ecosystem backend.
4. The response returns adapter-local metadata such as binary presence, environment configuration, and supported formats from files like `resolving/containerization/runtime/go_adapter.py` and `resolving/containerization/runtime/cargo_adapter.py`.

**Backend-Specific Result Construction:**

1. Go resolves module metadata into `ResolveResult` in `resolving/containerization/images/go/internal/resolver/resolver.go`.
2. Go converts that internal graph into normalized payloads in `resolving/containerization/images/go/internal/output/graph.go` and `resolving/containerization/images/go/internal/output/list.go`.
3. Cargo resolves and serializes graph data from `resolving/containerization/images/cargo/src/lib.rs` and `resolving/containerization/images/cargo/src/bin/cargo_resolver.rs`.
4. Maven emits graph JSON directly from `resolving/containerization/images/maven/src/main/java/cn/edu/zju/nirvana/adapter/MavenSingleresolving.java`.
5. npm emits backend-native stdout from `resolving/containerization/images/npm/src/main.cpp`, then `resolving/containerization/runtime/npm_adapter.py` reconstructs the normalized node and edge model from that raw output.

**State Management:**
- Keep execution request-scoped. There is no long-lived Python service process or shared in-memory state across invocations.
- Load configuration on each CLI invocation through `resolving/gateway/config.py`.
- Pass transient process state as plain dictionaries and `ProcessRunResult` from `resolving/gateway/models.py`.
- Persist backend caches only where Docker services declare them, such as `resolver-cargo-home-cache` and `resolver-maven-m2-cache` in `resolving/containerization/docker-compose.yml`.
- Keep legacy crawler persistence isolated from the active runtime. Archived crawlers refer to MongoDB, CouchDB, or PostgreSQL in `.legacy/Crawler/*/README.md`, but those stores are not part of the current resolver flow.

## Key Abstractions

**Request/Response Envelope:**
- Purpose: Standardize all cross-layer communication as JSON with a stable schema.
- Examples: `resolving/spec/request.schema.json`, `resolving/spec/response.schema.json`, `resolving/gateway/contract.py`
- Pattern: Schema-first contract documented in JSON Schema and enforced again in Python validation code.

**resolvingRegistry:**
- Purpose: Hide registry-file shape behind ecosystem lookup.
- Examples: `resolving/gateway/registry.py`, `resolving/config/resolvers.container.yaml`
- Pattern: Configuration-backed registry object with `get()` and `require()` lookup methods.

**GatewayService and GatewayDispatcher:**
- Purpose: Separate validation/error wrapping from dispatch and execution.
- Examples: `resolving/gateway/service.py`, `resolving/gateway/dispatcher.py`
- Pattern: Thin service facade plus dispatcher pipeline.

**ProcessRunner and ProcessRunResult:**
- Purpose: Encapsulate subprocess execution, timeout handling, and raw stdout/stderr capture.
- Examples: `resolving/gateway/runner.py`, `resolving/gateway/models.py`
- Pattern: Request-scoped process execution object that returns immutable result data.

**AdapterMetadata and Adapter Runtime Helpers:**
- Purpose: Centralize shared adapter response assembly, common command handling, and request parsing.
- Examples: `resolving/containerization/runtime/adapter_runtime.py`
- Pattern: Shared helper module plus per-ecosystem adapter specialization.

**Graph Normalization Guard:**
- Purpose: Enforce a minimum graph contract before the gateway accepts adapter success payloads.
- Examples: `resolving/containerization/runtime/launcher_normalization.py`
- Pattern: Post-backend structural validation with computed fallback metrics.

**Ecosystem Backend Models:**
- Purpose: Represent dependency graphs in the data structures most natural to each backend, then convert into the shared graph model.
- Examples: `resolving/containerization/images/go/internal/resolver/resolver.go`, `resolving/containerization/images/cargo/src/graph.rs`, `resolving/containerization/images/maven/src/main/java/cn/edu/zju/nirvana/adapter/MavenSingleresolving.java`, `resolving/containerization/images/npm/src/idealTree.cpp`
- Pattern: Polyglot backend internals behind a normalized adapter seam.

## Entry Points

**User CLI:**
- Location: `main.py`
- Triggers: Direct shell execution such as `python3 main.py resolve ...`
- Responsibilities: Parse arguments, build the request envelope, select the registry, invoke `GatewayService`, print final JSON, and set exit code.

**Docker Proxy Launcher:**
- Location: `resolving/containerization/docker_gateway_proxy.py`
- Triggers: Registry commands from `resolving/config/resolvers.container.yaml`
- Responsibilities: Read request JSON from stdin, run `docker compose`, forward stdout/stderr, and emit infrastructure errors when the container service fails before producing adapter JSON.

**Container Runtime Adapters:**
- Location: `resolving/containerization/runtime/npm_adapter.py`, `resolving/containerization/runtime/maven_adapter.py`, `resolving/containerization/runtime/cargo_adapter.py`, `resolving/containerization/runtime/go_adapter.py`, `resolving/containerization/runtime/default_adapter.py`
- Triggers: Docker Compose service entrypoints in `resolving/containerization/docker-compose.yml`
- Responsibilities: Parse stdin, handle `health` and `capabilities`, call native backends for resolver commands, normalize backend output, and emit shared responses.

**Native Backend Commands:**
- Location: `resolving/containerization/images/go/cmd/go_resolver/main.go`, `resolving/containerization/images/cargo/src/bin/cargo_resolver.rs`, `resolving/containerization/images/maven/src/main/java/cn/edu/zju/nirvana/adapter/MavenresolvingAdapterMain.java`, `resolving/containerization/images/npm/src/main.cpp`
- Triggers: Subprocess launches from runtime adapters.
- Responsibilities: Execute dependency resolution using ecosystem-native logic and produce backend-native stdout consumed by the adapter.

## Error Handling

**Strategy:** Validate early, fail closed, and map every error into the shared JSON error envelope before the response leaves the gateway or adapter boundary.

**Patterns:**
- Validate incoming requests in both `resolving/gateway/contract.py` and `resolving/containerization/runtime/adapter_runtime.py` so malformed payloads are rejected before backend launch.
- Encode gateway-level failures as typed exceptions in `resolving/gateway/errors.py`, then convert them into error envelopes in `resolving/gateway/service.py`.
- Represent process execution failures explicitly with `timeout`, `stdout`, `stderr`, and `exit_code` in `resolving/gateway/models.py`.
- Treat invalid adapter JSON or schema drift as `PROTOCOL_ERROR` in `resolving/gateway/response.py`.
- Let each adapter classify backend-native failures into shared codes such as `VERSION_NOT_FOUND`, `DATA_SOURCE_UNAVAILABLE`, `TIMEOUT`, or `BACKEND_CRASHED`, as shown in `resolving/containerization/runtime/go_adapter.py`, `resolving/containerization/runtime/cargo_adapter.py`, `resolving/containerization/runtime/maven_adapter.py`, and `resolving/containerization/runtime/npm_adapter.py`.
- Preserve `raw` backend details only when `return_raw` is enabled. The toggle is enforced in both `resolving/gateway/response.py` and `resolving/containerization/runtime/adapter_runtime.py`.

## Cross-Cutting Concerns

**Logging:** The Python orchestration path relies on captured stdout/stderr rather than a centralized logging framework. `resolving/gateway/runner.py` and `resolving/containerization/docker_gateway_proxy.py` preserve process output, while adapters optionally surface that output under `raw`.

**Validation:** Keep validation at every boundary. Use `resolving/gateway/contract.py` for request and response envelopes, adapter-local input checks in `resolving/containerization/runtime/*_adapter.py`, and graph-shape validation in `resolving/containerization/runtime/launcher_normalization.py`.

**Authentication:** Not detected in the active resolver runtime. `main.py`, `resolving/gateway/`, and `resolving/containerization/` do not implement user authentication, API tokens, or service-to-service auth.

---

*Architecture analysis: 2026-03-18*
