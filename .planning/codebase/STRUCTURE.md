# Codebase Structure

**Analysis Date:** 2026-03-18

## Directory Layout

```text
OpenDep/
├── .planning/codebase/                    # Generated codebase mapping documents
├── .legacy/Crawler/                      # Archived crawler implementations by ecosystem
├── Crawler/                              # Placeholder for future crawler work, not active runtime code
├── Resolver/                             # Active resolver subsystem
│   ├── config/                           # Resolver registry files
│   ├── containerization/                 # Docker proxy, compose wiring, adapters, and backend images
│   ├── gateway/                          # Host-side Python gateway orchestration
│   ├── spec/                             # Shared request/response protocol docs and examples
│   └── README.md                         # Resolver subsystem overview
├── README.md                             # Repository-level architecture and usage guide
└── main.py                               # User-facing CLI entrypoint
```

## Directory Purposes

**`.planning/codebase/`:**
- Purpose: Store generated repository reference documents such as `ARCHITECTURE.md` and `STRUCTURE.md`.
- Contains: Planning artifacts only.
- Key files: `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/STRUCTURE.md`

**`.legacy/Crawler/`:**
- Purpose: Preserve older crawler projects without coupling them to the active resolver runtime.
- Contains: Language-specific crawler implementations such as `.legacy/Crawler/go-dependency-crawler/`, `.legacy/Crawler/js-dependency-crawler/`, `.legacy/Crawler/maven-dependency-crawler/`, `.legacy/Crawler/pip-dependency-crawler/`, and `.legacy/Crawler/cargo-dependency-crawler/`.
- Key files: `.legacy/Crawler/go-dependency-crawler/main.go`, `.legacy/Crawler/pip-dependency-crawler/main.py`, `.legacy/Crawler/maven-dependency-crawler/pom.xml`

**`Crawler/`:**
- Purpose: Reserve the namespace for future crawler work while keeping it out of the current runtime.
- Contains: Placeholder documentation only.
- Key files: `Crawler/README.md`

**`Resolver/`:**
- Purpose: Hold every active subsystem used by `main.py`.
- Contains: Registry config, gateway code, protocol docs, Docker wiring, adapters, and backend implementations.
- Key files: `Resolver/README.md`, `Resolver/gateway/service.py`, `Resolver/config/resolvers.container.yaml`

**`Resolver/config/`:**
- Purpose: Declare which resolver handles each ecosystem and how it is launched.
- Contains: Registry files and config documentation.
- Key files: `Resolver/config/resolvers.container.yaml`, `Resolver/config/resolvers.yaml`, `Resolver/config/README.md`

**`Resolver/gateway/`:**
- Purpose: Own the host-side Python orchestration layer.
- Contains: Validation, resolver lookup, routing, process execution, and response normalization.
- Key files: `Resolver/gateway/service.py`, `Resolver/gateway/dispatcher.py`, `Resolver/gateway/router.py`, `Resolver/gateway/runner.py`, `Resolver/gateway/response.py`, `Resolver/gateway/contract.py`

**`Resolver/containerization/`:**
- Purpose: Own the active container-first backend execution strategy.
- Contains: Docker Compose service wiring, gateway proxy, container runtime adapters, and ecosystem-specific image directories.
- Key files: `Resolver/containerization/docker-compose.yml`, `Resolver/containerization/docker_gateway_proxy.py`, `Resolver/containerization/runtime/adapter_runtime.py`

**`Resolver/containerization/runtime/`:**
- Purpose: Hold Python adapters that translate the shared request envelope into ecosystem-specific backend invocations.
- Contains: Shared helper modules plus one adapter per ecosystem.
- Key files: `Resolver/containerization/runtime/go_adapter.py`, `Resolver/containerization/runtime/cargo_adapter.py`, `Resolver/containerization/runtime/maven_adapter.py`, `Resolver/containerization/runtime/npm_adapter.py`, `Resolver/containerization/runtime/default_adapter.py`

**`Resolver/containerization/images/`:**
- Purpose: Hold backend source code and image build files by ecosystem.
- Contains: Per-ecosystem subdirectories `Resolver/containerization/images/go/`, `Resolver/containerization/images/cargo/`, `Resolver/containerization/images/maven/`, `Resolver/containerization/images/npm/`, and `Resolver/containerization/images/pip/`.
- Key files: `Resolver/containerization/images/go/cmd/go_resolver/main.go`, `Resolver/containerization/images/cargo/src/bin/cargo_resolver.rs`, `Resolver/containerization/images/maven/pom.xml`, `Resolver/containerization/images/npm/CMakeLists.txt`

**`Resolver/spec/`:**
- Purpose: Document the wire contract and provide concrete payload examples.
- Contains: JSON schemas and request/response examples.
- Key files: `Resolver/spec/request.schema.json`, `Resolver/spec/response.schema.json`, `Resolver/spec/examples/request/go-resolve.json`, `Resolver/spec/examples/response/go-resolve-success.json`

## Key File Locations

**Entry Points:**
- `main.py`: Use this as the only direct user-facing CLI entrypoint.
- `Resolver/containerization/docker_gateway_proxy.py`: Use this when a registry entry needs to forward a request into Docker Compose.
- `Resolver/containerization/runtime/go_adapter.py`: Container entrypoint for the Go resolver service.
- `Resolver/containerization/runtime/cargo_adapter.py`: Container entrypoint for the Cargo resolver service.
- `Resolver/containerization/runtime/maven_adapter.py`: Container entrypoint for the Maven resolver service.
- `Resolver/containerization/runtime/npm_adapter.py`: Container entrypoint for the npm resolver service.
- `Resolver/containerization/runtime/default_adapter.py`: Placeholder container entrypoint for incomplete integrations such as `pip`.
- `Resolver/containerization/images/go/cmd/go_resolver/main.go`: Native Go backend entrypoint.
- `Resolver/containerization/images/cargo/src/bin/cargo_resolver.rs`: Native Cargo backend entrypoint.
- `Resolver/containerization/images/maven/src/main/java/cn/edu/zju/nirvana/adapter/MavenResolverAdapterMain.java`: Native Maven adapter entrypoint inside the jar.
- `Resolver/containerization/images/npm/src/main.cpp`: Native npm backend entrypoint.

**Configuration:**
- `Resolver/config/resolvers.container.yaml`: Primary active resolver registry.
- `Resolver/config/resolvers.yaml`: Legacy host-process registry kept for fallback/comparison.
- `Resolver/containerization/docker-compose.yml`: Service definitions, adapter entrypoints, and persistent cache volumes.
- `Resolver/gateway/config.py`: Path resolution and registry normalization logic.
- `README.md`: Top-level usage and subsystem overview.

**Core Logic:**
- `Resolver/gateway/service.py`: Top-level gateway API for handling a request.
- `Resolver/gateway/dispatcher.py`: Dispatch pipeline coordinator.
- `Resolver/gateway/router.py`: Command and format compatibility checks.
- `Resolver/gateway/runner.py`: Subprocess launcher and timeout handling.
- `Resolver/gateway/response.py`: Adapter response validation and raw-payload handling.
- `Resolver/containerization/runtime/adapter_runtime.py`: Shared response and request helpers for adapters.
- `Resolver/containerization/runtime/launcher_normalization.py`: Shared graph result validation helper.
- `Resolver/containerization/images/go/internal/resolver/resolver.go`: Go dependency graph expansion engine.
- `Resolver/containerization/images/go/internal/output/graph.go`: Go graph result serializer.
- `Resolver/containerization/images/cargo/src/lib.rs`: Rust graph-building facade used by the Cargo CLI.
- `Resolver/containerization/images/maven/src/main/java/cn/edu/zju/nirvana/adapter/MavenSingleResolver.java`: Maven graph JSON builder.

**Testing:**
- `Resolver/containerization/images/maven/src/test/java/cn/edu/zju/maven/dependency/resolver/core/DependencyTreeGenerateTest.java`: Current committed backend test example.
- `Resolver/spec/examples/request/`: Manual request fixtures for exercising adapters and the CLI.
- `Resolver/spec/examples/response/`: Manual response fixtures for validating expected payload shapes.

## Naming Conventions

**Files:**
- Use `snake_case.py` for Python modules in `Resolver/gateway/` and `Resolver/containerization/runtime/`, as shown by `Resolver/gateway/service.py` and `Resolver/containerization/runtime/go_adapter.py`.
- Name runtime adapter files `<ecosystem>_adapter.py`, as in `Resolver/containerization/runtime/npm_adapter.py` and `Resolver/containerization/runtime/cargo_adapter.py`.
- Keep root-level CLI entrypoints simple and conventional. The repository entrypoint is `main.py`, while native backends use language-native entry names such as `main.go`, `main.cpp`, or `cargo_resolver.rs`.
- Keep registry files grouped by purpose rather than ecosystem. The active registry is `Resolver/config/resolvers.container.yaml`, not one file per ecosystem.

**Directories:**
- Use subsystem directories at the top level. Active runtime code lives in `Resolver/`; inactive or future crawler code lives in `Crawler/` and `.legacy/Crawler/`.
- Use one directory per ecosystem under `Resolver/containerization/images/`.
- Use language-native package layouts inside each backend. Go uses `cmd/`, `internal/`, and `mvs/`; Java uses `src/main/java/...`; Rust uses `src/` and `src/bin/`; C++ keeps sources under `src/`.
- Keep Java package directories fully qualified, as in `Resolver/containerization/images/maven/src/main/java/cn/edu/zju/...`.

## Where to Add New Code

**New Feature:**
- Primary code: Put gateway-facing request orchestration in `Resolver/gateway/` if the feature changes validation, routing, or response assembly.
- Tests: Put backend-owned tests in the backend subtree that owns the feature. The existing example is `Resolver/containerization/images/maven/src/test/java/`. If a new subsystem introduces tests, keep them adjacent to that subsystem instead of placing them at repository root.

**New Ecosystem Integration:**
- Registry entry: Add it to `Resolver/config/resolvers.container.yaml`.
- Container service wiring: Add it to `Resolver/containerization/docker-compose.yml`.
- Adapter implementation: Create `Resolver/containerization/runtime/<ecosystem>_adapter.py`.
- Native backend: Create `Resolver/containerization/images/<ecosystem>/` with its own build metadata and entrypoint.
- Contract examples: Add sample payloads under `Resolver/spec/examples/request/` and `Resolver/spec/examples/response/`.

**New Gateway Behavior:**
- Implementation: Add or modify modules under `Resolver/gateway/`.
- Shared validation: Update `Resolver/gateway/contract.py` and the schema docs in `Resolver/spec/` together.

**Utilities:**
- Shared gateway helpers: Put them in `Resolver/gateway/`.
- Shared adapter helpers: Put them in `Resolver/containerization/runtime/`.
- Backend-specific helpers: Keep them inside the owning backend subtree such as `Resolver/containerization/images/go/internal/` or `Resolver/containerization/images/cargo/src/`.

**Do Not Place Active Runtime Code Here:**
- `Crawler/`: Reserve for future crawler work until the project explicitly revives it.
- `.legacy/Crawler/`: Treat as archived reference code, not as a place for new resolver runtime changes.
- `.planning/codebase/`: Keep for generated documentation only.

## Special Directories

**`.planning/codebase/`:**
- Purpose: Generated repository reference docs for planning and execution workflows.
- Generated: Yes
- Committed: Yes

**`.legacy/Crawler/`:**
- Purpose: Archived crawler implementations kept for reference.
- Generated: No
- Committed: Yes

**`Resolver/containerization/images/npm/third_party/`:**
- Purpose: Vendored third-party C++ dependencies used by the npm backend build.
- Generated: No
- Committed: Yes

**`Resolver/containerization/images/cargo/.cargo/`:**
- Purpose: Cargo-specific local build configuration for the Rust backend image.
- Generated: No
- Committed: Yes

**`Resolver/spec/examples/`:**
- Purpose: Hand-authored protocol fixtures that double as executable reference payloads for manual verification.
- Generated: No
- Committed: Yes

---

*Structure analysis: 2026-03-18*
