# npm Resolver Image

This directory contains the native C++ backend image for npm dependency
resolution. The image build compiles the resolver binary with CMake and
installs it as the image entrypoint.

## Current Command Alignment

| Path | Entry | Commands | Formats | Modes |
| --- | --- | --- | --- | --- |
| direct image run | native binary `/usr/local/bin/npm-resolver` | raw backend `resolve` only | backend-native output | registry URL supplied through `NPM_REGISTRY_BASE_URL` |
| compose service | `resolver-npm` with `runtime/npm_adapter.py` | `resolve`, `health`, `capabilities` | `graph` | `online`, `indexed` |

## Directory structure

Key files and directories:

- `resolving/containerization/images/npm/Dockerfile` — image definition
- `resolving/containerization/images/npm/CMakeLists.txt` — top-level CMake build configuration
- `resolving/containerization/images/npm/src/` — native resolver source tree
- `resolving/containerization/images/npm/src/CMakeLists.txt` — source-level build configuration
- `resolving/containerization/images/npm/src/main.cpp` — native CLI entrypoint
- `resolving/containerization/images/npm/src/config.hpp` — backend configuration defaults
- `resolving/containerization/images/npm/third_party/` — vendored third-party dependencies used by the native build
- `resolving/containerization/images/npm/readme.txt` — compatibility pointer for older tooling or local workflows

## Build the image

Run from the repository root:

```bash
docker build -f resolving/containerization/images/npm/Dockerfile -t npm-resolver:latest .
```

## Run the image

The image entrypoint is `/usr/local/bin/npm-resolver`.
It expects a package name and package version.

Example native run:

```bash
docker run --rm npm-resolver:latest is-odd 3.0.1
```

You can also override the online registry base URL for the native binary:

```bash
docker run --rm \
  -e NPM_REGISTRY_BASE_URL=https://registry.npmjs.org \
  npm-resolver:latest \
  @types/node 20.14.10
```

## Compose Service Path

The raw image entrypoint only exposes the native resolver CLI.
The gateway-facing `online` and `indexed` metadata modes are provided by the
compose service `resolver-npm`, which overrides the entrypoint to
`python3 resolving/containerization/runtime/npm_adapter.py`.

Example `online` resolve through the user-facing CLI:

```bash
python3 main.py resolve --ecosystem npm --name left-pad --version 1.3.0 --format graph --npm-mode online
```

Example `indexed` resolve through the same adapter path:

```bash
python3 main.py resolve --ecosystem npm --name left-pad --version 1.3.0 --format graph --npm-mode indexed --npm-index-dsn 'postgresql://opendep:opendep@host.docker.internal:55432/opendep_preprocess' --npm-index-table npm_metadata
```

Example `health` check:

```bash
python3 main.py health --ecosystem npm --npm-mode indexed --npm-index-dsn 'postgresql://opendep:opendep@host.docker.internal:55432/opendep_preprocess' --npm-index-table npm_metadata
```

## Notes

- The native program prints backend-native progress and result sections to stdout.
- The native backend now reads `NPM_REGISTRY_BASE_URL` at runtime, so the registry source no longer has to be compiled into the image.
- Scoped package names are URL-escaped before fetch, so requests such as `@types/node` work in both online mode and adapter-managed indexed mode.
- In indexed mode, the Python adapter starts a local HTTP shim backed by
  PostgreSQL and points the native binary at that shim through
  `NPM_REGISTRY_BASE_URL`.
- Indexed fallback to the online registry is enabled by default on the adapter path.
