# Cargo resolving Image

This directory contains the Rust backend image for Cargo dependency resolution.
The image build compiles the native resolver binary and installs it as the image entrypoint.

## Directory structure

Key files and directories:

- `resolving/containerization/images/cargo/Dockerfile` — image definition
- `resolving/containerization/images/cargo/Cargo.toml` — Rust package manifest
- `resolving/containerization/images/cargo/Cargo.lock` — locked dependency graph for the Rust build
- `resolving/containerization/images/cargo/.cargo/config.toml` — runtime Cargo configuration template staged into the dedicated Cargo runtime root
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
bash pre-process/cargo/refresh_local_snapshot.sh
docker build -f resolving/containerization/images/cargo/Dockerfile -t cargo-resolver:latest .
```

## Run the image

The image entrypoint is `/usr/local/bin/cargo-resolver`.
The shared Cargo cache is typically mounted to `/cargo-home`.

Example native run:

```bash
docker run --rm -v resolver-cargo-home-cache:/cargo-home cargo-resolver:latest resolve rand 0.8.5 --format full --pretty
```

## Shared local-registry mode

The active compose-based resolver path now supports a preprocess-managed shared Cargo `local-registry`.
The intended operator flow is:

1. Prepare `pre-process/cargo/data/local-registry/` through the Cargo preprocess workspace.
2. Build the resolver image once so it still contains a baked fallback snapshot.
3. Run `resolver-cargo` through [docker-compose.yml](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/docker-compose.yml), which mounts the shared local-registry into `/cargo-preprocess/local-registry`.
4. Let [cargo_adapter.py](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/runtime/cargo_adapter.py) repoint `/opt/opendep/cargo-runtime/local-registry` to the shared mount when it is present.

Example preprocess bootstrap:

```bash
python3 pre-process/cargo/build.py clone --pretty
python3 pre-process/cargo/build.py prepare-local-registry --force --pretty
docker compose -f resolving/containerization/docker-compose.yml build resolver-cargo
python3 main.py health --ecosystem cargo
```

When the shared mount is available, health should report:

- `runtime_registry_source = shared`
- `runtime_registry_active_path = /cargo-preprocess/local-registry`

Later preprocess refreshes do not require rebuilding the resolver image:

```bash
python3 pre-process/cargo/build.py update --pretty
python3 pre-process/cargo/build.py prepare-local-registry --force --pretty
python3 main.py resolve --ecosystem cargo --name tokio --version 1.38.0 --format graph --return-raw
```

If the shared mount is absent or incomplete, the adapter falls back automatically to the baked image registry snapshot.

## Notes

- The current refactor-stage Dockerfile copies a repository-local `crates.io-index` checkout into the image, then stages it as a baked `local-registry` fallback under `/opt/opendep/cargo-runtime/image-local-registry`.
- The runtime path `/opt/opendep/cargo-runtime/local-registry` is now a bind-time symlink target chosen by the adapter:
  - shared preprocess-managed data first
  - baked image fallback second
- The current refactor-stage build expects that checkout to exist at `resolving/containerization/images/cargo/crates.io-index/` in the repository working tree.
- The resolver runtime is launched from the dedicated Cargo runtime root instead of relying on accidental `/app/.cargo` config discovery.
- The repository-local `resolving/containerization/images/cargo/crates.io-index/` checkout is a temporary refactor-stage bootstrap input. The intended closing-state design is to replace it with either image-side clone or preprocess-managed shared Cargo metadata.
- The named volume `resolver-cargo-home-cache` is recommended for repeated runs.
- The native binary currently supports the `resolve` command.
