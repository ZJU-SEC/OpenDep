# Testing Patterns

**Analysis Date:** 2026-03-18

## Test Framework

**Runner:**
- There is no repository-wide automated test runner configured at the root.
- The only clearly committed active unit test suite is the Maven backend’s JUnit Jupiter setup in `resolving/containerization/images/maven/pom.xml`.
- The Maven test runner is `maven-surefire-plugin` 2.22.2, configured in `resolving/containerization/images/maven/pom.xml`.

**Assertion Library:**
- JUnit Jupiter assertions are used in `resolving/containerization/images/maven/src/test/java/cn/edu/zju/maven/dependency/resolver/core/DependencyTreeGenerateTest.java`.
- Assertions include `assertThrows`, `assertTrue`, and `assertNotNull`.

**Run Commands:**
```bash
cd resolving/containerization/images/maven && mvn test
python3 main.py capabilities --ecosystem go
python3 main.py health --ecosystem npm
python3 main.py resolve --ecosystem maven --name org.apache.logging.log4j:log4j-core --version 2.23.1 --format graph
python3 main.py list --ecosystem go --name github.com/kubernetes/apimachinery --version v0.35.2
```

## Test File Organization

**Location:**
- Automated tests currently live primarily in `resolving/containerization/images/maven/src/test/java/`.
- The active test file discovered in this repo is `resolving/containerization/images/maven/src/test/java/cn/edu/zju/maven/dependency/resolver/core/DependencyTreeGenerateTest.java`.
- No Python tests were found under `resolving/gateway/` or the root CLI.
- No Go `_test.go` files were found under `resolving/containerization/images/go/`.

**Naming:**
- Java tests use `*Test.java`, matching the production class under test.
- The repository relies heavily on README-documented smoke tests instead of a consistent cross-language naming scheme.

**Structure:**
```text
resolving/containerization/images/maven/
├── src/main/java/...                         # Java implementation
└── src/test/java/.../DependencyTreeGenerateTest.java
```

## Test Structure

**Suite Organization:**
- The Maven suite uses plain JUnit methods with descriptive `@DisplayName` annotations.
- Parameterized coverage is present through `@ParameterizedTest` and `@ValueSource`.
- Timeout behavior is tested with `@Timeout`.

**Patterns:**
- Tests are mostly behavior-oriented and call the real dependency-generation methods rather than mock-heavy seams.
- Arrange/act/assert is followed informally inside the Java test methods.
- Cleanup is handled manually where global state is touched, for example resetting timeout values after timeout tests.

## Mocking

**Framework:**
- No dedicated mocking framework is visible in the committed active tests.
- The Maven test file exercises concrete code paths directly rather than using mocks or stubs.

**What to Mock:**
- The current repo does not establish a shared mocking convention.
- If new Python gateway tests are added, subprocess and Docker invocations in `resolving/gateway/runner.py` and `resolving/containerization/docker_gateway_proxy.py` are the obvious boundaries to fake.

**What NOT to Mock:**
- Pure request/response validation helpers such as `resolving/gateway/contract.py`.
- Normalization helpers that can be tested with direct inputs and outputs.

## Fixtures and Factories

**Test Data:**
- Existing Java tests inline representative Maven coordinates such as `org.apache.commons:commons-lang3:3.12.0`.
- No shared fixture directory, factory module, or snapshot store was found for the active code paths.

**Location:**
- Request/response examples that can support manual or future automated tests live under `resolving/spec/examples/request/` and `resolving/spec/examples/response/`.

## Coverage

**Requirements:**
- No repo-wide coverage target or enforcement mechanism is committed.
- There is no evidence of CI blocking on minimum coverage.

**Configuration:**
- Maven’s test execution is configured.
- Python, Go, Rust, and C++ coverage tooling is not configured in the checked-in repository.

## Test Types

**Unit Tests:**
- Present mainly for the Maven backend.
- Focus areas include valid artifacts, invalid coordinates, null input, empty input, parameterized valid artifacts, and timeout handling.

**Integration / Smoke Tests:**
- The main documented verification path is manual CLI execution from `README.md`.
- Smoke tests operate through the real gateway plus container runtime, especially for `capabilities`, `health`, `resolve`, and Go `list`.

**E2E Tests:**
- No dedicated end-to-end test harness is present.
- The closest equivalent is running `python3 main.py` against live Compose-backed services.

## Common Patterns

**Async / Timeout Testing:**
- Timeout testing is explicitly present only in the Maven unit suite.
- Python and adapter timeouts are implemented in code but are not covered by a committed automated test suite.

**Error Testing:**
- Maven tests use `assertThrows(...)` for invalid inputs and timeout behavior.
- Python gateway error handling would be straightforward to test with table-driven payloads, but those tests are currently missing.

**Snapshot Testing:**
- Not used in the committed active code paths.

## Testing Gaps

**High-Risk Untested Areas:**
- `main.py` argument parsing and request construction.
- `resolving/gateway/runner.py` subprocess behavior and timeout handling.
- `resolving/containerization/runtime/*.py` adapter normalization for Go, Cargo, npm, and placeholder pip.
- Native Go, Rust, and C++ backends in the active resolver path.

**Practical Guidance for New Tests:**
- Add Python unit tests around request validation, resolver selection, and timeout/error normalization before changing gateway behavior.
- Add adapter-level tests that stub subprocess output instead of requiring live Docker for every case.
- Preserve the existing Maven JUnit style when extending the Java backend.

---

*Testing analysis: 2026-03-18*
*Update when test patterns or commands change*
