# Codebase Structure

**Analysis Date:** 2026-03-18

## Directory Layout

```text
OpenDep/
├── .planning/codebase/                    # Generated codebase mapping documents
├── .legacy/Crawler/                      # Archived crawler implementations by ecosystem
├── Crawler/                              # Placeholder for future crawler work, not active runtime code
├── resolving/                             # Active resolver subsystem
│   ├── config/                           # resolving registry files
│   ├── containerization/                 # Docker proxy, compose wiring, adapters, and backend images
│   ├── gateway/                          # Host-side Python gateway orchestration
│   ├── spec/                             # Shared request/response protocol docs and examples
│   └── README.md                         # resolving subsystem overview
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

**`resolving/`:**
- Purpose: Hold every active subsystem used by `main.py`.
- Contains: Registry config, gateway code, protocol docs, Docker wiring, adapters, and backend implementations.
- Key files: `resolving/README.md`, `resolving/gateway/service.py`, `resolving/config/resolvers.container.yaml`

**`resolving/config/`:**
- Purpose: Declare which resolver handles each ecosystem and how it is launched.
- Contains: Registry files and config documentation.
- Key files: `resolving/config/resolvers.container.yaml`, `resolving/config/resolvers.yaml`, `resolving/config/README.md`

**`resolving/gateway/`:**
- Purpose: Own the host-side Python orchestration layer.
- Contains: Validation, resolver lookup, routing, process execution, and response normalization.
- Key files: `resolving/gateway/service.py`, `resolving/gateway/dispatcher.py`, `resolving/gateway/router.py`, `resolving/gateway/runner.py`, `resolving/gateway/response.py`, `resolving/gateway/contract.py`

**`resolving/containerization/`:**
- Purpose: Own the active container-first backend execution strategy.
- Contains: Docker Compose service wiring, gateway proxy, container runtime adapters, and ecosystem-specific image directories.
- Key files: `resolving/containerization/docker-compose.yml`, `resolving/containerization/docker_gateway_proxy.py`, `resolving/containerization/runtime/adapter_runtime.py`

**`resolving/containerization/runtime/`:**
- Purpose: Hold Python adapters that translate the shared request envelope into ecosystem-specific backend invocations.
- Contains: Shared helper modules plus one adapter per ecosystem.
- Key files: `resolving/containerization/runtime/go_adapter.py`, `resolving/containerization/runtime/cargo_adapter.py`, `resolving/containerization/runtime/maven_adapter.py`, `resolving/containerization/runtime/npm_adapter.py`, `resolving/containerization/runtime/default_adapter.py`

**`resolving/containerization/images/`:**
- Purpose: Hold backend source code and image build files by ecosystem.
- Contains: Per-ecosystem subdirectories `resolving/containerization/images/go/`, `resolving/containerization/images/cargo/`, `resolving/containerization/images/maven/`, `resolving/containerization/images/npm/`, and `resolving/containerization/images/pip/`.
- Key files: `resolving/containerization/images/go/cmd/go_resolver/main.go`, `resolving/containerization/images/cargo/src/bin/cargo_resolver.rs`, `resolving/containerization/images/maven/pom.xml`, `resolving/containerization/images/npm/CMakeLists.txt`

**`resolving/spec/`:**
- Purpose: Document the wire contract and provide concrete payload examples.
- Contains: JSON schemas and request/response examples.
- Key files: `resolving/spec/request.schema.json`, `resolving/spec/response.schema.json`, `resolving/spec/examples/request/go-resolve.json`, `resolving/spec/examples/response/go-resolve-success.json`

## Key File Locations

**Entry Points:**
- `main.py`: Use this as the only direct user-facing CLI entrypoint.
- `resolving/containerization/docker_gateway_proxy.py`: Use this when a registry entry needs to forward a request into Docker Compose.
- `resolving/containerization/runtime/go_adapter.py`: Container entrypoint for the Go resolver service.
- `resolving/containerization/runtime/cargo_adapter.py`: Container entrypoint for the Cargo resolver service.
- `resolving/containerization/runtime/maven_adapter.py`: Container entrypoint for the Maven resolver service.
- `resolving/containerization/runtime/npm_adapter.py`: Container entrypoint for the npm resolver service.
- `resolving/containerization/runtime/default_adapter.py`: Placeholder container entrypoint for incomplete integrations such as `pip`.
- `resolving/containerization/images/go/cmd/go_resolver/main.go`: Native Go backend entrypoint.
- `resolving/containerization/images/cargo/src/bin/cargo_resolver.rs`: Native Cargo backend entrypoint.
- `resolving/containerization/images/maven/src/main/java/cn/edu/zju/nirvana/adapter/MavenresolvingAdapterMain.java`: Native Maven adapter entrypoint inside the jar.
- `resolving/containerization/images/npm/src/main.cpp`: Native npm backend entrypoint.

**Configuration:**
- `resolving/config/resolvers.container.yaml`: Primary active resolver registry.
- `resolving/config/resolvers.yaml`: Legacy host-process registry kept for fallback/comparison.
- `resolving/containerization/docker-compose.yml`: Service definitions, adapter entrypoints, and persistent cache volumes.
- `resolving/gateway/config.py`: Path resolution and registry normalization logic.
- `README.md`: Top-level usage and subsystem overview.

**Core Logic:**
- `resolving/gateway/service.py`: Top-level gateway API for handling a request.
- `resolving/gateway/dispatcher.py`: Dispatch pipeline coordinator.
- `resolving/gateway/router.py`: Command and format compatibility checks.
- `resolving/gateway/runner.py`: Subprocess launcher and timeout handling.
- `resolving/gateway/response.py`: Adapter response validation and raw-payload handling.
- `resolving/containerization/runtime/adapter_runtime.py`: Shared response and request helpers for adapters.
- `resolving/containerization/runtime/launcher_normalization.py`: Shared graph result validation helper.
- `resolving/containerization/images/go/internal/resolver/resolver.go`: Go dependency graph expansion engine.
- `resolving/containerization/images/go/internal/output/graph.go`: Go graph result serializer.
- `resolving/containerization/images/cargo/src/lib.rs`: Rust graph-building facade used by the Cargo CLI.
- `resolving/containerization/images/maven/src/main/java/cn/edu/zju/nirvana/adapter/MavenSingleresolving.java`: Maven graph JSON builder.

**Testing:**
- `resolving/containerization/images/maven/src/test/java/cn/edu/zju/maven/dependency/resolver/core/DependencyTreeGenerateTest.java`: Current committed backend test example.
- `resolving/spec/examples/request/`: Manual request fixtures for exercising adapters and the CLI.
- `resolving/spec/examples/response/`: Manual response fixtures for validating expected payload shapes.

## Naming Conventions

**Files:**
- Use `snake_case.py` for Python modules in `resolving/gateway/` and `resolving/containerization/runtime/`, as shown by `resolving/gateway/service.py` and `resolving/containerization/runtime/go_adapter.py`.
- Name runtime adapter files `<ecosystem>_adapter.py`, as in `resolving/containerization/runtime/npm_adapter.py` and `resolving/containerization/runtime/cargo_adapter.py`.
- Keep root-level CLI entrypoints simple and conventional. The repository entrypoint is `main.py`, while native backends use language-native entry names such as `main.go`, `main.cpp`, or `cargo_resolver.rs`.
- Keep registry files grouped by purpose rather than ecosystem. The active registry is `resolving/config/resolvers.container.yaml`, not one file per ecosystem.

**Directories:**
- Use subsystem directories at the top level. Active runtime code lives in `resolving/`; inactive or future crawler code lives in `Crawler/` and `.legacy/Crawler/`.
- Use one directory per ecosystem under `resolving/containerization/images/`.
- Use language-native package layouts inside each backend. Go uses `cmd/`, `internal/`, and `mvs/`; Java uses `src/main/java/...`; Rust uses `src/` and `src/bin/`; C++ keeps sources under `src/`.
- Keep Java package directories fully qualified, as in `resolving/containerization/images/maven/src/main/java/cn/edu/zju/...`.

## Where to Add New Code

**New Feature:**
- Primary code: Put gateway-facing request orchestration in `resolving/gateway/` if the feature changes validation, routing, or response assembly.
- Tests: Put backend-owned tests in the backend subtree that owns the feature. The existing example is `resolving/containerization/images/maven/src/test/java/`. If a new subsystem introduces tests, keep them adjacent to that subsystem instead of placing them at repository root.

**New Ecosystem Integration:**
- Registry entry: Add it to `resolving/config/resolvers.container.yaml`.
- Container service wiring: Add it to `resolving/containerization/docker-compose.yml`.
- Adapter implementation: Create `resolving/containerization/runtime/<ecosystem>_adapter.py`.
- Native backend: Create `resolving/containerization/images/<ecosystem>/` with its own build metadata and entrypoint.
- Contract examples: Add sample payloads under `resolving/spec/examples/request/` and `resolving/spec/examples/response/`.

**New Gateway Behavior:**
- Implementation: Add or modify modules under `resolving/gateway/`.
- Shared validation: Update `resolving/gateway/contract.py` and the schema docs in `resolving/spec/` together.

**Utilities:**
- Shared gateway helpers: Put them in `resolving/gateway/`.
- Shared adapter helpers: Put them in `resolving/containerization/runtime/`.
- Backend-specific helpers: Keep them inside the owning backend subtree such as `resolving/containerization/images/go/internal/` or `resolving/containerization/images/cargo/src/`.

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

**`resolving/containerization/images/npm/third_party/`:**
- Purpose: Vendored third-party C++ dependencies used by the npm backend build.
- Generated: No
- Committed: Yes

**`resolving/containerization/images/cargo/.cargo/`:**
- Purpose: Cargo-specific local build configuration for the Rust backend image.
- Generated: No
- Committed: Yes

**`resolving/spec/examples/`:**
- Purpose: Hand-authored protocol fixtures that double as executable reference payloads for manual verification.
- Generated: No
- Committed: Yes

---

*Structure analysis: 2026-03-18*
