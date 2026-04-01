# resolving Backend Images

This directory contains the ecosystem-specific image definitions used by the
container resolver stack. Each subdirectory owns the files needed to build one
backend image for one ecosystem.

## Purpose

The `resolving/containerization/images/` tree is the backend-image layer of
the OpenDep resolver architecture. Its responsibilities are:

- define how each ecosystem-specific backend image is built
- keep language-specific toolchains isolated from the host machine
- package native resolver binaries, jars, or language-specific backend runtimes into runnable container images
- provide the image layer that is later wrapped by the container adapters in `resolving/containerization/runtime/`

## Relationship to the container stack

Within the broader container path:

- `resolving/containerization/images/` provides backend images
- `resolving/containerization/runtime/` provides adapter entrypoints and response normalization
- `resolving/containerization/docker-compose.yml` wires the images into named services
- `main.py` and the gateway call those services through the resolver registry

## Directory layout

The current ecosystem directories are:

- `resolving/containerization/images/npm/`
- `resolving/containerization/images/maven/`
- `resolving/containerization/images/cargo/`
- `resolving/containerization/images/go/`
- `resolving/containerization/images/pip/`

Each ecosystem directory may contain:

- a `Dockerfile`
- backend source code and build metadata
- ecosystem-specific helper scripts or configuration files
- optional compatibility notes or legacy transition files

## Design intent

These image directories are split by ecosystem because each backend uses a
different language toolchain and dependency model. That keeps the build logic
local and makes it easier to evolve one backend without affecting the others.

## Current Image Alignment

| Ecosystem | Backend form | Image directory | Current runtime contract |
| --- | --- | --- | --- |
| `pip` | Python backend module | `resolving/containerization/images/pip/` | `live` or `indexed` metadata flow |
| `npm` | native C++ binary | `resolving/containerization/images/npm/` | `online` or `indexed` packument flow, with indexed mode served through the adapter shim |
| `maven` | Java resolver jar | `resolving/containerization/images/maven/` | shared `.m2` cache contract |
| `cargo` | native Rust binary | `resolving/containerization/images/cargo/` | preprocess-managed shared `local-registry` plus Cargo home cache |
| `go` | native Go binary | `resolving/containerization/images/go/` | `online` or `indexed` module metadata flow |

## Notes

- `npm`, `maven`, `cargo`, `go`, and `pip` are the current container
  backends.
- The image directories own backend build logic; compose services still use
  adapters from `resolving/containerization/runtime/` as the default service
  entrypoints.
- Build and run instructions are documented in each ecosystem subdirectory README.
