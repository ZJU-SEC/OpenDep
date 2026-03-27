# Cargo resolving Image

This directory contains the Rust backend image for Cargo dependency resolution.
The image build compiles the native resolver binary and installs it as the image entrypoint.

## Directory structure

Key files and directories:

- `resolving/containerization/images/cargo/Dockerfile` — image definition
- `resolving/containerization/images/cargo/Cargo.toml` — Rust package manifest
- `resolving/containerization/images/cargo/Cargo.lock` — locked dependency graph for the Rust build
- `resolving/containerization/images/cargo/.cargo/config.toml` — Cargo configuration used during image build and runtime
- `resolving/containerization/images/cargo/src/bin/` — native CLI entry binaries
- `resolving/containerization/images/cargo/src/batch/` — batch-oriented code paths and helpers
- `resolving/containerization/images/cargo/src/lib.rs` — shared library entry for the crate
- `resolving/containerization/images/cargo/src/resolver.rs` — dependency resolution logic
- `resolving/containerization/images/cargo/src/graph.rs` — graph-model construction helpers
- `resolving/containerization/images/cargo/src/model.rs` — shared data structures
- `resolving/containerization/images/cargo/src/util.rs` — utility helpers

## Build the image

Run from the repository root:

```bash
docker build -f resolving/containerization/images/cargo/Dockerfile -t cargo-resolver:latest .
```

## Run the image

The image entrypoint is `/usr/local/bin/cargo-resolver`.
The shared Cargo cache is typically mounted to `/cargo-home`.

Example native run:

```bash
docker run --rm -v resolver-cargo-home-cache:/cargo-home cargo-resolver:latest resolve rand 0.8.5 --format full --pretty
```

## Notes

- The image build clones a local `crates.io-index` copy into the image.
- The named volume `resolver-cargo-home-cache` is recommended for repeated runs.
- The native binary currently supports the `resolve` command.
