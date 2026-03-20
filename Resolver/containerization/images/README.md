# Resolver Backend Images

This directory contains the ecosystem-specific image definitions used by the containerized resolver stack.
Each subdirectory owns the files needed to build one backend image for a single package ecosystem.

## Purpose

The `Resolver/containerization/images/` tree is the backend-image layer of the OpenDep resolver architecture.
Its responsibilities are:

- define how each ecosystem-specific backend image is built
- keep language-specific toolchains isolated from the host machine
- package native resolver binaries, jars, or placeholder runtimes into runnable container images
- provide the image layer that is later wrapped by the container adapters in `Resolver/containerization/runtime/`

## Relationship to the container stack

Within the broader containerized path:

- `Resolver/containerization/images/` provides backend images
- `Resolver/containerization/runtime/` provides adapter entrypoints and response normalization
- `Resolver/containerization/docker-compose.yml` wires the images into named services
- `main.py` and the gateway call those services through the resolver registry

## Directory layout

The current ecosystem directories are:

- `Resolver/containerization/images/npm/`
- `Resolver/containerization/images/maven/`
- `Resolver/containerization/images/cargo/`
- `Resolver/containerization/images/go/`
- `Resolver/containerization/images/pip/`

Each ecosystem directory may contain:

- a `Dockerfile`
- backend source code and build metadata
- ecosystem-specific helper scripts or configuration files
- optional compatibility notes or legacy transition files

## Design intent

These image directories are intentionally separated by ecosystem because each backend uses a different language toolchain and dependency model.
This keeps the build logic localized and makes it easier to evolve one backend without affecting the others.

## Notes

- `npm`, `maven`, `cargo`, `go`, and `pip` currently correspond to the active integrated container backends.
- `pip` now packages a Python backend plus `runtime/pip_adapter.py`, with both `live` and `indexed` metadata modes.
- Build and run instructions are documented in each ecosystem subdirectory README.
