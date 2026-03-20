# Codebase Concerns

**Analysis Date:** 2026-03-18

## Tech Debt

**pip integration remains a placeholder path:**
- Issue: The `pip` resolver is wired into the stack but still uses the generic placeholder adapter and placeholder image.
- Files: `Resolver/containerization/docker-compose.yml`, `Resolver/containerization/runtime/default_adapter.py`, `Resolver/containerization/images/pip/Dockerfile`
- Why: The architecture reserves the ecosystem slot before a real backend has been implemented.
- Impact: `pip` appears in configs and capabilities wiring, but cannot perform real dependency resolution.
- Fix approach: Replace the placeholder container image and runtime command with a real pip backend plus adapter-specific normalization.

**Registry files use `.yaml` names but JSON syntax:**
- Issue: `Resolver/config/resolvers.container.yaml` and `Resolver/config/resolvers.yaml` are parsed with `json.load(...)`.
- Why: Historical file naming was retained while the content format changed.
- Impact: Editors, tooling, and contributors can misread the expected format and make invalid edits.
- Fix approach: Either rename the files to `.json` or switch the loader to actual YAML parsing and document one format only.

**Cargo batch utilities are coupled to a local Postgres default:**
- Issue: The Cargo batch path hardcodes `host=localhost dbname=crates user=postgres password=postgres`.
- Files: `Resolver/containerization/images/cargo/src/batch/config.rs`, `Resolver/containerization/images/cargo/src/batch/db.rs`
- Why: Legacy batch tooling was written for a local research workflow rather than the containerized interactive resolver path.
- Impact: The repo contains dormant database-coupled code that is easy to misread as production-ready.
- Fix approach: Isolate batch tooling behind explicit feature flags, move credentials to environment variables, or remove the unused path from the active image.

## Known Bugs

**Direct npm backend invocation lacks argument count guards:**
- Symptoms: Running the native npm resolver binary without enough positional arguments can read `argv[1]` and `argv[2]` unsafely.
- Trigger: Invoke the native program directly rather than through the adapter contract.
- Files: `Resolver/containerization/images/npm/src/main.cpp`
- Workaround: Use the Python gateway or npm adapter path, which supplies the expected arguments.
- Root cause: `main(int argc, char* argv[])` does not validate `argc` before indexing arguments.

**Mapper-scale repository includes large vendored trees that slow automated exploration:**
- Symptoms: Repository analysis and naive file scans can stall or spend disproportionate time in `third_party/`.
- Trigger: Broad scans over `Resolver/containerization/images/npm/third_party/`.
- Files: `Resolver/containerization/images/npm/third_party/`
- Workaround: Exclude vendored directories during analysis, search, and planning unless native dependency internals are the target.
- Root cause: The npm backend vendors several large native libraries directly into the repository.

## Security Considerations

**Hardcoded database credentials in Cargo batch config:**
- Risk: The checked-in default Postgres connection string encourages insecure local usage and accidental reuse in other environments.
- Files: `Resolver/containerization/images/cargo/src/batch/config.rs`
- Current mitigation: None in the committed code beyond the fact that the interactive Compose service does not provision that database path.
- Recommendations: Move credentials to environment variables or remove the default entirely.

**Resolver execution is config-driven subprocess execution:**
- Risk: The gateway runs the command arrays declared in resolver config files through `subprocess.run(...)`.
- Files: `Resolver/gateway/runner.py`, `Resolver/gateway/config.py`, `Resolver/config/resolvers.container.yaml`
- Current mitigation: Config files are local, in-repo, and path normalization resolves relative commands into project paths.
- Recommendations: Treat alternate `--config` files as trusted inputs only and add validation or allowlists if untrusted configs ever become a use case.

## Performance Bottlenecks

**Container startup on every resolver request:**
- Problem: The host path launches `docker compose run` for each request instead of talking to a long-lived service.
- Files: `Resolver/containerization/docker_gateway_proxy.py`
- Measurement: No benchmark is committed, but process and container startup overhead is unavoidable for every call.
- Cause: The architecture favors isolation and simplicity over persistent backend workers.
- Improvement path: Move to long-lived services or a pooled execution model if request volume increases.

**npm backend metadata fetch path is network-heavy and partially mirror-specific:**
- Problem: The C++ npm backend fetches package metadata over HTTP and only caches in memory for the lifetime of a single process.
- Files: `Resolver/containerization/images/npm/src/dataset.cpp`, `Resolver/containerization/images/npm/src/dataset.hpp`
- Cause: The active `USE_OFFICIAL` path issues remote registry requests and the cache is cleared before process exit.
- Improvement path: Add durable caching or a service-level cache, and make registry selection configurable without recompilation.

## Fragile Areas

**Cross-language protocol normalization boundary:**
- Why fragile: The end-to-end flow crosses Python, Go, Rust, Java, and C++ boundaries, with adapters responsible for translating native output into the shared resolver schema.
- Common failures: Small backend output changes can surface as `PROTOCOL_ERROR` or malformed graph payloads.
- Safe modification: Change one adapter/backend pair at a time and validate against `Resolver/spec/request.schema.json` and `Resolver/spec/response.schema.json`.
- Test coverage: Thin. Automated coverage is concentrated in the Maven backend only.

**Path bootstrap and import setup in Python entrypoints:**
- Why fragile: Several Python entrypoints mutate `sys.path` at runtime before importing repo-local packages.
- Files: `main.py`, `Resolver/containerization/docker_gateway_proxy.py`, `Resolver/containerization/runtime/*.py`
- Common failures: Moving files or changing relative depth can break startup without immediate type-check feedback.
- Safe modification: Preserve the current parent-path assumptions or convert the repo to an installable package before refactoring imports.
- Test coverage: No committed Python startup tests were found.

## Scaling Limits

**Current execution model is single-request, subprocess-oriented:**
- Current capacity: Suitable for developer-invoked CLI usage and small-scale manual runs.
- Limit: Higher request throughput will pay repeated subprocess and container launch costs.
- Symptoms at limit: Slow request latency, higher CPU churn, and noisy repeated warmup work.
- Scaling path: Introduce persistent workers, cache warming, or service processes behind the gateway.

## Dependencies at Risk

**Frozen vendored native dependencies in npm backend:**
- Risk: The C++ resolver vendors specific snapshots such as `fmt-9.1.0`, `redis-plus-plus-1.3.7`, `abseil-cpp-20230125.0`, and `re2-2023-02-01`.
- Files: `Resolver/containerization/images/npm/third_party/`, `Resolver/containerization/images/npm/CMakeLists.txt`
- Impact: Security or compatibility updates require manual vendor refreshes instead of simple package-manager upgrades.
- Migration plan: Replace vendored snapshots with a managed dependency strategy or formalize a refresh procedure.

**Older Maven resolver stack:**
- Risk: The Maven backend depends on `org.eclipse.aether` `1.0.0.v20140518` and `maven-aether-provider` `3.1.0`.
- Files: `Resolver/containerization/images/maven/pom.xml`
- Impact: Upgrading Java or repository behavior may be harder than with a newer dependency resolver stack.
- Migration plan: Evaluate a modern Maven Resolver upgrade path before expanding Maven-specific functionality.

## Missing Critical Features

**No real pip backend:**
- Problem: The repository advertises a `pip` path structurally but not functionally.
- Current workaround: Use the active ecosystems `npm`, `maven`, `cargo`, or `go`.
- Blocks: Python package dependency resolution through the unified CLI.
- Implementation complexity: Medium to high, because it requires both native/backend behavior and adapter normalization work.

## Test Coverage Gaps

**Python gateway and adapter flow:**
- What's not tested: Request validation, resolver selection, subprocess timeout handling, adapter normalization, and raw payload behavior in the Python orchestration path.
- Risk: Protocol regressions or startup failures can slip through until manual CLI use.
- Priority: High.
- Difficulty to test: Moderate; subprocess boundaries need stubs or fixtures.

**Go, Cargo, and npm active backends:**
- What's not tested: The active non-Java backend implementations do not have visible committed unit test suites in the repository.
- Risk: Backend-specific regressions may only be caught through manual smoke testing or live Docker runs.
- Priority: High.
- Difficulty to test: Moderate to high depending on whether tests stay pure or require external registries.

---

*Concerns audit: 2026-03-18*
*Update as issues are fixed or new risks are discovered*
