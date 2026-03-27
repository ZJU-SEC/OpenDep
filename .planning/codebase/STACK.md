# Technology Stack

**Analysis Date:** 2026-03-18

## Languages

**Primary:**
- Python 3.x - Host-side CLI, gateway, Docker proxy, and container adapters in `main.py`, `resolving/gateway/`, `resolving/containerization/docker_gateway_proxy.py`, and `resolving/containerization/runtime/`.
- Go 1.24.0 - Native Go resolver backend defined by `resolving/containerization/images/go/go.mod` and implemented under `resolving/containerization/images/go/`.

**Secondary:**
- Rust 2021 - Cargo resolver backend in `resolving/containerization/images/cargo/` with manifest data in `resolving/containerization/images/cargo/Cargo.toml`.
- Java 11 - Maven resolver backend declared in `resolving/containerization/images/maven/pom.xml` and implemented under `resolving/containerization/images/maven/src/main/java/`.
- C++20 - npm resolver backend built from `resolving/containerization/images/npm/CMakeLists.txt` and `resolving/containerization/images/npm/src/`.
- JSON and Markdown - Registry/config/spec and operational documentation in `resolving/config/`, `resolving/spec/`, and the various `README.md` files.

## Runtime

**Environment:**
- Host Python runtime selected through `${PYTHON}` placeholder expansion in `resolving/gateway/config.py` and used by the resolver registry files in `resolving/config/resolvers.container.yaml` and `resolving/config/resolvers.yaml`.
- Docker Engine plus `docker compose` are required for the active execution path; the gateway launches containers via `resolving/containerization/docker_gateway_proxy.py`.
- Linux-based container runtimes are defined for `resolver-pip`, `resolver-npm`, `resolver-go`, `resolver-cargo`, and `resolver-maven` in `resolving/containerization/docker-compose.yml`.

**Package Manager / Build Manager:**
- No root-level Python package manifest is present. The Python host layer relies on the standard library plus in-repo modules.
- Go modules are managed through `resolving/containerization/images/go/go.mod`.
- Rust dependencies are managed through `resolving/containerization/images/cargo/Cargo.toml` with `resolving/containerization/images/cargo/Cargo.lock` committed.
- Maven dependencies and build plugins are managed through `resolving/containerization/images/maven/pom.xml`.
- The npm backend uses CMake 3.22 with vendored native dependencies in `resolving/containerization/images/npm/third_party/`.

## Frameworks

**Core:**
- Custom Python CLI and orchestration layer rather than a web framework, centered on `GatewayService`, `GatewayDispatcher`, and `ProcessRunner` in `resolving/gateway/`.
- Docker Compose as the service orchestration layer for backend execution, configured in `resolving/containerization/docker-compose.yml`.

**Testing:**
- JUnit Jupiter 5.9.2 for the Maven backend, declared in `resolving/containerization/images/maven/pom.xml`.
- No repository-wide Python, Go, or Rust test runner configuration is committed at the root.

**Build / Dev:**
- Dockerfiles per ecosystem in `resolving/containerization/images/{pip,npm,go,cargo,maven}/Dockerfile`.
- Maven compiler, assembly, and surefire plugins in `resolving/containerization/images/maven/pom.xml`.
- Go toolchain build flow driven by `resolving/containerization/images/go/Dockerfile`.
- Cargo build flow driven by `resolving/containerization/images/cargo/Dockerfile`.
- CMake-based native build for npm in `resolving/containerization/images/npm/CMakeLists.txt` and `resolving/containerization/images/npm/src/CMakeLists.txt`.

## Key Dependencies

**Critical:**
- `golang.org/x/mod v0.25.0` - Go module parsing and normalization for the Go backend in `resolving/containerization/images/go/go.mod`.
- `cargo 0.63.0` - Core Rust library used by the Cargo backend in `resolving/containerization/images/cargo/Cargo.toml`.
- `serde` and `serde_json` - JSON serialization for Rust backend output in `resolving/containerization/images/cargo/Cargo.toml`.
- `org.eclipse.aether` 1.0.0.v20140518 and `maven-aether-provider` 3.1.0 - Maven dependency resolution backbone in `resolving/containerization/images/maven/pom.xml`.
- Vendored `hiredis`, `redis-plus-plus`, `fmt`, `abseil-cpp`, and `re2` - Native npm backend dependencies referenced by `resolving/containerization/images/npm/CMakeLists.txt`.

**Infrastructure:**
- Docker / Docker Compose - Required to run the integrated backends from the gateway path in `resolving/containerization/docker_gateway_proxy.py`.
- Java runtime - Required for the Maven adapter and backend jar defined in `resolving/containerization/runtime/maven_adapter.py`.
- Persistent cache volumes `resolver-cargo-home-cache` and `resolver-maven-m2-cache` in `resolving/containerization/docker-compose.yml`.

## Configuration

**Environment:**
- resolving registry definitions live in `resolving/config/resolvers.container.yaml` and `resolving/config/resolvers.yaml`.
- Service-level environment configuration is centralized in `resolving/containerization/docker-compose.yml`, including `GO_PROXY_BASE_URL`, `CARGO_HOME`, `CARGO_REGISTRY_MODE`, `MAVEN_BACKEND_JAR`, `MAVEN_MAIN_CLASS`, and `NPM_BACKEND_BINARY`.
- The placeholder adapter reads `RESOLVER_*` variables and `PLACEHOLDER_MESSAGE` from `resolving/containerization/runtime/default_adapter.py`.
- No `.env`, `.env.example`, or similar root environment file is present.

**Build:**
- Compose wiring: `resolving/containerization/docker-compose.yml`
- Host path resolution and placeholder expansion: `resolving/gateway/config.py`
- Shared protocol reference: `resolving/spec/request.schema.json` and `resolving/spec/response.schema.json`

## Platform Requirements

**Development:**
- Python 3, Docker, and `docker compose` on the host, as described in `README.md`.
- Network access for first-time metadata fetches and backend image builds.
- Toolchains are isolated inside containers for the active backends; direct host builds are optional rather than required.

**Production / Operational:**
- Container-first deployment model for the active backends `npm`, `maven`, `cargo`, and `go`.
- The `pip` path remains a placeholder service in `resolving/containerization/docker-compose.yml` and is not production-ready.
- The host entrypoint remains `main.py`; the repository is not structured as a long-running daemon or HTTP service.

---

*Stack analysis: 2026-03-18*
*Update after major dependency or runtime changes*
