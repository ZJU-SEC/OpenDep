# External Integrations

**Analysis Date:** 2026-03-18

## APIs & External Services

**Docker / Compose Runtime:**
- The gateway invokes external Compose services through `docker compose run --rm --no-deps -T` in `Resolver/containerization/docker_gateway_proxy.py`.
  - Integration method: Local Docker CLI subprocess call.
  - Auth: None in code; relies on host Docker permissions.
  - Services used: `resolver-pip`, `resolver-npm`, `resolver-go`, `resolver-cargo`, `resolver-maven` from `Resolver/containerization/docker-compose.yml`.

**Go Module Proxy:**
- The Go backend fetches module metadata from a configurable Go proxy in `Resolver/containerization/images/go/internal/source/proxy.go`.
  - Integration method: HTTP GET requests for `@v/<version>.mod` files.
  - Default endpoint: `https://proxy.golang.org`, sourced from `GO_PROXY_BASE_URL`.
  - Auth: None.

**Cargo Registry Mirror:**
- The Cargo backend is configured to use a local file-backed mirror in `Resolver/containerization/images/cargo/.cargo/config.toml`.
  - Integration method: `file:///app/crates.io-index/` mirror replacing `crates-io`.
  - Auth: None.
  - Runtime note: The image README states the Dockerfile clones a local `crates.io-index` copy during image build.

**Maven Central:**
- The Maven backend constructs a single remote repository pointing to Maven Central in `Resolver/containerization/images/maven/src/main/java/cn/edu/zju/maven/dependency/resolver/core/utils/Booter.java`.
  - Integration method: Eclipse Aether repository client.
  - Endpoint: `https://repo.maven.apache.org/maven2/`
  - Auth: None in the checked-in code.

**npm Registry Metadata:**
- The npm native backend fetches package metadata using libcurl in `Resolver/containerization/images/npm/src/dataset.cpp`.
  - Integration method: HTTP GET via libcurl.
  - Active endpoint in code: `https://registry.npmmirror.com/<package>`
  - Alternate modes in code: local CouchDB (`http://127.0.0.1:8080`) and Redis-backed lookup are compiled options in `Resolver/containerization/images/npm/src/config.hpp`.

## Data Storage

**Local / Persistent Caches:**
- Maven uses the named Docker volume `resolver-maven-m2-cache` mounted at `/root/.m2` in `Resolver/containerization/docker-compose.yml`.
- Cargo uses the named Docker volume `resolver-cargo-home-cache` mounted at `/cargo-home` in `Resolver/containerization/docker-compose.yml`.
- Go currently does not declare a dedicated persistent volume in the Compose stack.
- The npm backend keeps an in-process cache in `DataSet.cache` inside `Resolver/containerization/images/npm/src/dataset.hpp`; there is no active Compose-managed persistent npm cache.

**Local File Storage:**
- Resolver registry and protocol definitions are stored in-repo under `Resolver/config/` and `Resolver/spec/`.
- The Cargo mirror source is local-file based inside the image at `/app/crates.io-index/`, configured in `Resolver/containerization/images/cargo/.cargo/config.toml`.

**Database Usage:**
- The active gateway path does not provision an application database.
- The Cargo codebase includes PostgreSQL-backed batch utilities under `Resolver/containerization/images/cargo/src/batch/`, with a default connection string in `Resolver/containerization/images/cargo/src/batch/config.rs`.
- That PostgreSQL path is not wired by `Resolver/containerization/docker-compose.yml` for the interactive resolver service.

## Authentication & Identity

**Auth Provider:**
- None. The checked-in resolver flow is a local CLI plus container stack and does not implement user authentication.

**OAuth Integrations:**
- None present in `main.py`, `Resolver/gateway/`, or `Resolver/containerization/`.

## Monitoring & Observability

**Error Reporting:**
- The Python gateway and adapters return structured error envelopes defined in `Resolver/gateway/response.py` and `Resolver/containerization/runtime/adapter_runtime.py`.
- Native backends primarily expose errors through stdout/stderr and process exit codes.

**Logging:**
- Python host code emits JSON payloads with `print()` in `main.py` and `Resolver/containerization/runtime/adapter_runtime.py`.
- Rust batch tooling uses `simplelog` file and terminal logging in `Resolver/containerization/images/cargo/src/batch/config.rs`.
- Java backend logging is configured with Logback in `Resolver/containerization/images/maven/src/main/resources/logback.xml`.
- The npm backend prints progress and result sections with `fmt::print` in `Resolver/containerization/images/npm/src/main.cpp`.

**Analytics / Tracing:**
- No external analytics, tracing, or hosted observability service is configured in the repository.

## CI/CD & Deployment

**Hosting / Runtime Model:**
- The active deployment model is local or server-side Docker Compose execution rather than a hosted PaaS configuration.
- The repository does not include checked-in GitHub Actions, CI pipeline YAML, or deployment manifests outside the Compose stack.

**Build Pipeline:**
- Backend images are built from the Dockerfiles in `Resolver/containerization/images/`.
- The user-facing run path is documented in `README.md` and `Resolver/containerization/README.md`.

## Environment Configuration

**Development:**
- Critical environment variables are injected via `Resolver/containerization/docker-compose.yml`.
- The gateway also supports `--config` overrides in `main.py` to point at alternate resolver registry files.
- Secrets management is effectively absent; no secret store integration or `.env` file is checked in.

**Staging / Production:**
- No separate staging or production configuration files are present.
- Environment differences appear to be expected via alternate registry files or Compose overrides rather than a dedicated deployment system.

## Webhooks & Callbacks

**Incoming:**
- None.

**Outgoing:**
- None.

---

*Integration audit: 2026-03-18*
*Update when adding or removing external systems*
