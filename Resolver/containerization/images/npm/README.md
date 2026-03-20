# npm Resolver Image

This directory contains the native C++ backend image for npm dependency resolution.
The image build compiles the resolver binary with CMake and installs it as the image entrypoint.

## Directory structure

Key files and directories:

- `Resolver/containerization/images/npm/Dockerfile` — image definition
- `Resolver/containerization/images/npm/CMakeLists.txt` — top-level CMake build configuration
- `Resolver/containerization/images/npm/src/` — native resolver source tree
- `Resolver/containerization/images/npm/src/CMakeLists.txt` — source-level build configuration
- `Resolver/containerization/images/npm/src/main.cpp` — native CLI entrypoint
- `Resolver/containerization/images/npm/src/config.hpp` — backend configuration defaults
- `Resolver/containerization/images/npm/third_party/` — vendored third-party dependencies used by the native build
- `Resolver/containerization/images/npm/readme.txt` — compatibility pointer for older tooling or local workflows

## Build the image

Run from the repository root:

```bash
docker build -f Resolver/containerization/images/npm/Dockerfile -t npm-resolver:latest .
```

## Run the image

The image entrypoint is `/usr/local/bin/npm-resolver`.
It expects a package name and package version.

Example native run:

```bash
docker run --rm npm-resolver:latest is-odd 3.0.1
```

## Notes

- The native program prints backend-native progress and result sections to stdout.
- Registry-related defaults can be adjusted in `Resolver/containerization/images/npm/src/config.hpp` before rebuilding.
