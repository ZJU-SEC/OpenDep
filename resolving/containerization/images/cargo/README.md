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
docker build -f resolving/containerization/images/cargo/Dockerfile -t cargo-resolver:latest .
```

The current Docker build assumes repository-root context.
It compiles the native resolver binary and stages the runtime Cargo config under `/opt/opendep/cargo-runtime/.cargo/config.toml`.
The shared preprocess-managed data under `pre-process/cargo/data/` and the legacy local path `resolving/containerization/images/cargo/crates.io-index/` are excluded from the Docker build context by the repository-root `.dockerignore`.

## Run the image

The image entrypoint is `/usr/local/bin/cargo-resolver`.
The runtime working directory is `/opt/opendep/cargo-runtime`, and the shared Cargo cache is typically mounted to `/cargo-home`.

Example native run:

```bash
docker run --rm \
  -v opendep-cargo-preprocess-data:/cargo-preprocess-data:ro \
  -v resolver-cargo-home-cache:/cargo-home \
  cargo-resolver:latest \
  resolve rand 0.8.5 --format full --pretty
```

## Active and legacy entrypoints

The active resolver path for containerized request handling is:

- [cargo_resolver.rs](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/images/cargo/src/bin/cargo_resolver.rs)
- [resolver.rs](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/images/cargo/src/resolver.rs)
- [registry_index.rs](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/images/cargo/src/registry_index.rs)

The crate default run target now points at `cargo_resolver`, so a plain `cargo run` matches the active CLI path.

The following code still exists in the Cargo image source tree but is not on the active `resolver-cargo` request path:

- [main.rs](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/images/cargo/src/main.rs)
- [get_deps.rs](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/images/cargo/src/bin/get_deps.rs)
- [count_deps.rs](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/images/cargo/src/bin/count_deps.rs)
- [complete_deps.rs](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/images/cargo/src/bin/complete_deps.rs)
- [batch/](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/images/cargo/src/batch)

## Shared local-registry mode

The active compose-based resolver path now supports a preprocess-managed shared Cargo `local-registry`.
The intended operator flow is:

1. Prepare the shared Docker volume `opendep-cargo-preprocess-data` through the Cargo preprocess workspace.
2. Build the resolver image.
3. Run `resolver-cargo` through [docker-compose.yml](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/docker-compose.yml), which mounts that same volume at `/cargo-preprocess-data`.
4. Let [cargo_adapter.py](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/runtime/cargo_adapter.py) validate that the preprocess-managed mount is present before serving requests.

Example preprocess bootstrap:

```bash
docker compose -f pre-process/cargo/docker-compose.yml run --rm cargo-preprocess clone --pretty
docker compose -f pre-process/cargo/docker-compose.yml run --rm cargo-preprocess prepare-local-registry --force --pretty
docker compose -f resolving/containerization/docker-compose.yml build resolver-cargo
python3 main.py health --ecosystem cargo
```

When the shared mount is available, health should report:

- `runtime_registry_source = preprocess-shared`
- `runtime_registry_active_path = /cargo-preprocess-data/local-registry`

Later preprocess refreshes do not require rebuilding the resolver image:

```bash
docker compose -f pre-process/cargo/docker-compose.yml run --rm cargo-preprocess update --pretty
docker compose -f pre-process/cargo/docker-compose.yml run --rm cargo-preprocess prepare-local-registry --force --pretty
python3 main.py resolve --ecosystem cargo --name tokio --version 1.38.0 --format graph --return-raw
```

If the shared mount is absent or incomplete, the adapter now fails fast and reports a misconfiguration instead of silently falling back to image-baked data.

Health output now makes the source selection more explicit by reporting:

- `preprocess_registry_mount`
- `runtime_registry_source`
- `runtime_registry_active_path`
- `runtime_registry_config_sha256`

## Notes

- The current Dockerfile no longer bakes a Cargo registry snapshot into the image. The runtime metadata contract is the preprocess-managed shared volume mounted at `/cargo-preprocess-data/local-registry`.
- The adapter no longer performs shared-versus-baked source selection. It validates the mounted preprocess data and fails fast when that contract is not satisfied.
- The resolver runtime is launched from the dedicated Cargo runtime root instead of relying on accidental `/app/.cargo` config discovery.
- A legacy local `resolving/containerization/images/cargo/crates.io-index/` checkout is no longer used by the build and can be removed from a developer workspace.
- The named volume `resolver-cargo-home-cache` is recommended for repeated runs.
- The shared metadata volume defaults to `opendep-cargo-preprocess-data`. Override it consistently in both compose stacks with `CARGO_PREPROCESS_DATA_VOLUME_NAME` if needed.
- The native binary currently supports the `resolve` command.
