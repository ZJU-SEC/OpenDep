# Coding Conventions

**Analysis Date:** 2026-03-18

## Naming Patterns

**Files:**
- Python modules use `snake_case.py`, for example `Resolver/gateway/response.py` and `Resolver/containerization/runtime/go_adapter.py`.
- Go packages use short lowercase directory names such as `internal/source`, `internal/output`, and `internal/parser` under `Resolver/containerization/images/go/`.
- Rust modules and binaries use `snake_case.rs`, for example `Resolver/containerization/images/cargo/src/bin/cargo_resolver.rs`.
- Java files use `PascalCase.java`, matching class names in `Resolver/containerization/images/maven/src/main/java/`.
- C++ sources use lowercase names with `.cpp` / `.hpp`, for example `dataset.cpp`, `idealTree.cpp`, and `config.hpp` in `Resolver/containerization/images/npm/src/`.

**Functions / Methods:**
- Python functions and methods use `snake_case`, for example `build_request`, `validate_request`, and `default_config_path`.
- Go exported functions use `PascalCase` while internal helpers use `camelCase`, for example `NewProxySource`, `FetchGoMod`, and `resolveModule`.
- Rust functions use `snake_case`, for example `resolve_graph_of_version_once` and `parse_args`.
- Java methods use `camelCase`, for example `newRepositorySystemSession` and `generateDependencyTreeJson`.

**Variables / Constants:**
- Python constants are `UPPER_SNAKE_CASE`, for example `DESCRIPTION`, `EPILOG`, and `SUPPORTED_COMMANDS`.
- Environment-backed adapter constants are also `UPPER_SNAKE_CASE`, such as `BACKEND_BINARY`, `PROXY_BASE_URL`, and `DEFAULT_TIMEOUT_MS`.
- C++ compile-time switches are macro-style `UPPER_SNAKE_CASE`, for example `USE_OFFICIAL`, `DETECT_QUEUE_LOOP`, and `QUEUE_LOOP_LIMIT`.

**Types:**
- Python classes use `PascalCase`, for example `GatewayService`, `ProcessRunner`, and `ProcessRunResult`.
- Rust structs use `PascalCase`, for example `CliConfig` and `VersionInfo`.
- Go types use `PascalCase`, for example `ProxySource`.

## Code Style

**Formatting:**
- No repo-wide formatter configuration such as `pyproject.toml`, `ruff.toml`, `rustfmt.toml`, `.golangci.yml`, or `.editorconfig` is committed at the repository root.
- Python code uses 4-space indentation, type hints, and `from __future__ import annotations` in nearly every module under `Resolver/gateway/` and `Resolver/containerization/runtime/`.
- Go code appears to follow standard `gofmt` layout and import grouping, as seen in `Resolver/containerization/images/go/cmd/go_resolver/main.go`.
- Rust code appears to follow idiomatic `rustfmt` style with grouped `use` statements and compact CLI parsing in `Resolver/containerization/images/cargo/src/bin/cargo_resolver.rs`.
- C++ code uses 2-space indentation and preprocessor-heavy configuration in `Resolver/containerization/images/npm/src/`.

**Linting:**
- No committed lint command or lint config was found for Python, Go, Rust, Java, or C++.
- Style appears to be enforced by convention and by each language toolchain rather than by a repository-wide CI gate.

## Import Organization

**Order:**
1. Python standard library imports first.
2. Local package imports second, usually from `Resolver.gateway` or `Resolver.containerization.runtime`.
3. Go standard library imports first, then internal and external packages.
4. Rust `use` statements group standard library items separately from crate imports.

**Grouping:**
- Python files often insert a blank line between bootstrap path logic and local imports, as in `main.py` and `Resolver/containerization/docker_gateway_proxy.py`.
- Several Python entry modules add `PROJECT_ROOT` or parent paths into `sys.path` before importing local packages.
- Java packages follow package-path alignment rooted at `cn.edu.zju...`.

**Path Conventions:**
- Python import paths are absolute within the repo package namespace, for example `from Resolver.gateway.response import GatewayResponseFactory`.
- Go uses package-local internal imports rooted at `github.com/package-dependency/go-resolver/...`.

## Error Handling

**Patterns:**
- Python host code uses custom exception classes derived from `GatewayError` in `Resolver/gateway/errors.py`, then catches them at the service boundary in `Resolver/gateway/service.py`.
- Gateway request and response validation return lists of string errors rather than raising directly in `Resolver/gateway/contract.py`.
- Runtime adapters convert backend failures into structured `error_response(...)` payloads in `Resolver/containerization/runtime/adapter_runtime.py`.
- Native backends mostly report operational failures through stderr plus non-zero exit codes.

**Error Types:**
- Gateway-facing error codes use shared string constants such as `INVALID_ARGUMENT`, `PROTOCOL_ERROR`, `TIMEOUT`, and `BACKEND_MISCONFIGURED`.
- Retryability is tracked explicitly in Python and adapter payloads rather than inferred from exception class alone.

## Logging

**Framework:**
- The Python host path primarily uses direct `print()` output for final JSON payloads rather than a logger.
- Rust batch utilities use `simplelog` in `Resolver/containerization/images/cargo/src/batch/config.rs`.
- Java backend logging uses SLF4J plus Logback from `Resolver/containerization/images/maven/pom.xml` and `Resolver/containerization/images/maven/src/main/resources/logback.xml`.
- The npm backend uses `fmt::print` and stderr logging in `Resolver/containerization/images/npm/src/main.cpp` and `dataset.cpp`.

**Patterns:**
- Structured JSON output is emitted only at adapter or CLI boundaries.
- Internal Python modules keep side effects low and return dictionaries or dataclass values instead of logging heavily.
- Logging is sparse overall; most modules prioritize payload generation over observability hooks.

## Comments

**When to Comment:**
- Comments are generally sparse and used for configuration toggles, build notes, or edge-case warnings.
- The C++ backend contains inline TODO and XXX markers in files such as `Resolver/containerization/images/npm/src/dataset.cpp` and `Resolver/containerization/images/npm/src/node.hpp`.
- Java code uses Javadoc-style comments on some helper classes such as `Booter.java`.

**TODO Style:**
- There is no single enforced TODO format. Existing TODOs are plain inline comments without issue IDs.

## Function Design

**Size:**
- Python gateway functions are generally small and single-purpose, especially in `Resolver/gateway/service.py`, `registry.py`, `router.py`, and `models.py`.
- Adapter modules contain medium-sized orchestration functions that validate input, invoke subprocesses, and normalize errors.
- Native backends mix concise CLI wrappers with larger domain logic modules deeper in their respective trees.

**Parameters / Returns:**
- Python code prefers dictionaries for protocol payloads and small dataclasses for process results.
- Adapters commonly return `(result, raw, error)` tuples to keep subprocess normalization explicit.
- Go and Rust CLI layers favor explicit positional CLI parsing and typed structs.

## Module Design

**Exports:**
- Python modules export classes and helper functions directly; there is no barrel-export pattern.
- Go keeps public constructors or helpers close to the consuming package.
- Rust exposes shared APIs from `Resolver/containerization/images/cargo/src/lib.rs` and keeps CLI entrypoints in `src/bin/`.

**Boundaries:**
- The Python gateway is intentionally thin and ecosystem-agnostic.
- Ecosystem-specific semantics live inside `Resolver/containerization/runtime/<ecosystem>_adapter.py` and the native backend directories under `Resolver/containerization/images/`.
- Documentation files under `README.md` and `Resolver/**/README.md` are part of the repo’s operating conventions and are worth updating alongside behavior changes.

---

*Convention analysis: 2026-03-18*
*Update when style or code organization patterns change*
