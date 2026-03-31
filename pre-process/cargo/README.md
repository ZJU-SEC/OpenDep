# Cargo Pre-process Workspace

This workspace is not a traditional crawler pipeline.
For Cargo, the upstream [`crates.io-index`](https://github.com/rust-lang/crates.io-index) is already the authoritative metadata source, so the refactor direction is to manage that index cleanly and adapt the active resolver to consume it more efficiently.

The working task list for this migration lives in [tasks.md](/Users/xingyu/project/Paper/OpenDep/pre-process/cargo/tasks.md).

## Current Direction

- Keep `crates.io-index` as the source of truth.
- First stabilize the active resolver path on `local-registry`, then add preprocess machinery around shared index lifecycle.
- Treat `pre-process/cargo/` as an index manager:
  - clone
  - update
  - status
  - prepare a resolver-consumable local-registry layout
- Do not introduce PostgreSQL for Cargo in the first refactor.
- Do not replace Cargo's own solver with a custom dependency solver.

## Phase C Index Manager

Phase C introduces a minimal Cargo index manager under:

- [build.py](/Users/xingyu/project/Paper/OpenDep/pre-process/cargo/build.py)
- [docker-entrypoint.sh](/Users/xingyu/project/Paper/OpenDep/pre-process/cargo/docker-entrypoint.sh)
- [docker-compose.yml](/Users/xingyu/project/Paper/OpenDep/pre-process/cargo/docker-compose.yml)

The manager currently supports:

- `clone`
- `update`
- `status`
- `prepare-local-registry`

### Managed data layout

By default, the Cargo preprocess workspace now manages data under:

- `pre-process/cargo/data/`

Within that root, the default layout is:

- managed git clone: `pre-process/cargo/data/crates.io-index/`
- prepared local-registry: `pre-process/cargo/data/local-registry/`

The current resolver bootstrap path under:

- `resolving/containerization/images/cargo/crates.io-index/`

is still a temporary Phase B compatibility path.
Phase C introduced the managed data layout, and Phase D now wires the prepared `local-registry` into the active resolver runtime.

## Active Resolver Path

The current resolver path is:

- [cargo_adapter.py](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/runtime/cargo_adapter.py)
- `/usr/local/bin/cargo-resolver`
- [resolver.rs](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/images/cargo/src/resolver.rs)

The active runtime configuration now points Cargo at a `local-registry` source staged under the dedicated Cargo runtime root:

- [config.toml](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/images/cargo/.cargo/config.toml#L4)

That config currently uses:

```toml
[source.mirror]
local-registry = "/opt/opendep/cargo-runtime/local-registry"
```

The current refactor-stage image build now copies a repository-local `crates.io-index` checkout into the runtime-local `local-registry` layout in:

- [Dockerfile](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/images/cargo/Dockerfile)

The adapter now runs the native backend from an explicit Cargo runtime root rather than relying on `/app/.cargo` discovery:

- [cargo_adapter.py](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/runtime/cargo_adapter.py)

## Phase A Baseline

### Legacy refresh behavior

Before the runtime source migration, repeated resolve requests triggered Cargo refresh work even though the source lived on the local filesystem.
In practice, resolver runs currently emit stderr like:

```text
Updating `mirror` index
Running `git fetch --force --update-head-ok 'file:///app/crates.io-index/' ...
```

The repository-root baseline commands that reproduced this behavior were:

```bash
python3 main.py resolve --ecosystem cargo --name anyhow --version 1.0.56 --format graph --return-raw
python3 main.py resolve --ecosystem cargo --name rand --version 0.8.5 --format graph --return-raw
python3 main.py resolve --ecosystem cargo --name tokio --version 1.38.0 --format graph --return-raw
```

Those requests were used as the pre-migration baseline.

### Current double-resolve behavior

The active resolver currently performs two resolves per request:

- [resolver.rs](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/images/cargo/src/resolver.rs#L14) calls `collect_enabled_features(...)`
- [resolver.rs](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/images/cargo/src/resolver.rs#L19) then calls `run_resolve(...)` again for the final graph
- [resolver.rs](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/images/cargo/src/resolver.rs#L49) shows the first resolve inside `collect_enabled_features(...)`

That means the current git-style index refresh work is paid twice for a single logical resolve request.

### Confirmed local-registry findings

Resolver-side experiments have already established the following:

- A root-only local-registry subset fails because the resolver cannot discover missing transitive dependencies from absent index entries.
- A complete dependency-closure local-registry subset succeeds for the OpenDep resolver path.
- For the current OpenDep graph resolver path, an index-only local-registry can succeed without `.crate` files when the dependency-closure index entries are present.
- Generic Cargo CLI behavior should not be treated as the primary validation target for this migration, because `cargo metadata` and related workflows may still require `.crate` artifacts even when the OpenDep resolver path does not.
- A full-index `local-registry` runtime layout with otherwise unchanged resolver logic removes the repeated `Updating 'mirror' index` and `git fetch ...` stderr noise while preserving baseline graph metrics.

### Baseline validation set

The current baseline set for later regression checks is:

- `anyhow@1.0.56`
- `rand@0.8.5`
- `tokio@1.38.0`

These samples cover:

- a moderate dependency tree
- a commonly used crate with mixed optional feature behavior
- a feature-heavy root crate that stresses the current "resolve all features" path

## Non-goals for the First Mainline Cargo Refactor

The first Cargo refactor PR should explicitly avoid:

- PostgreSQL-backed Cargo metadata storage
- a custom Cargo dependency solver
- full `.crate` artifact management
- query-scoped index snapshot generation
- dependency-edge analytics tables
- broad cleanup of every historical Cargo helper in the same PR

## Planned Outcome

The mainline migration should proceed in this order:

1. formalize the resolver runtime migration to `local-registry`
2. build `pre-process/cargo/` into a proper index manager for clone, update, status, and local-registry preparation
3. integrate preprocess-managed shared Cargo metadata into `resolver-cargo`
4. replace the temporary repository-local snapshot bootstrap with either image-side clone or preprocess-managed shared data
5. only then remove the current double resolve by reading root features directly from the index

## Development Note

During the active Cargo refactor, keeping an untracked checkout at `resolving/containerization/images/cargo/crates.io-index/` is the temporary committed bootstrap path because it keeps iteration faster than image-build-time `git clone`.
That repository-local snapshot is still not the intended final architecture.
Before the Cargo refactor is closed, the bootstrap path should be replaced by either image-side clone or preprocess-managed shared Cargo metadata.

## Current Bootstrap Step

The current Phase B bootstrap assumes the repository-local snapshot exists at:

- `resolving/containerization/images/cargo/crates.io-index/`

The canonical way to refresh that snapshot from upstream is:

```bash
bash pre-process/cargo/refresh_local_snapshot.sh
```

After refreshing the snapshot, rebuild the Cargo resolver image from the repository root:

```bash
docker compose -f resolving/containerization/docker-compose.yml build resolver-cargo
```

That image-side snapshot is still kept as a baked fallback.
Once the shared preprocess-managed mount is ready, the resolver prefers that shared `local-registry` without needing another image rebuild for later metadata refreshes.

## Phase C Usage

### Local commands

Clone the managed index into the default Cargo preprocess data root:

```bash
python3 pre-process/cargo/build.py clone --pretty
```

Show the managed index and local-registry status:

```bash
python3 pre-process/cargo/build.py status --pretty
```

Update an existing managed clone:

```bash
python3 pre-process/cargo/build.py update --pretty
```

Prepare a resolver-consumable local-registry from the managed clone:

```bash
python3 pre-process/cargo/build.py prepare-local-registry --force --pretty
```

If needed, you can override the managed paths explicitly:

```bash
python3 pre-process/cargo/build.py clone \
  --data-root /tmp/opendep-cargo-data \
  --index-url https://github.com/rust-lang/crates.io-index.git \
  --pretty
```

### Docker commands

Build the Cargo preprocess image:

```bash
docker compose -f pre-process/cargo/docker-compose.yml build cargo-preprocess
```

Run the same manager operations through Docker:

```bash
docker compose -f pre-process/cargo/docker-compose.yml run --rm cargo-preprocess clone --pretty

docker compose -f pre-process/cargo/docker-compose.yml run --rm cargo-preprocess status --pretty

docker compose -f pre-process/cargo/docker-compose.yml run --rm cargo-preprocess update --pretty

docker compose -f pre-process/cargo/docker-compose.yml run --rm cargo-preprocess prepare-local-registry --force --pretty
```

## Phase D Shared Runtime Integration

`resolver-cargo` now mounts the preprocess-managed local-registry by default from:

- `pre-process/cargo/data/local-registry/`

through:

- [docker-compose.yml](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/docker-compose.yml)

Inside the resolver container, the adapter uses this precedence model:

- prefer `/cargo-preprocess/local-registry` when it contains `index/config.json`
- otherwise fall back to the baked image snapshot under `/opt/opendep/cargo-runtime/image-local-registry`

That means the Docker image still has a self-contained fallback, but the normal Phase D workflow is now:

1. Prepare or refresh the shared local-registry in `pre-process/cargo/data/local-registry/`.
2. Run the resolver through the normal compose-backed entrypoints.
3. Let the adapter bind `/opt/opendep/cargo-runtime/local-registry` to the shared mount automatically.

### Recommended shared workflow

Bootstrap shared Cargo metadata:

```bash
python3 pre-process/cargo/build.py clone --pretty
python3 pre-process/cargo/build.py prepare-local-registry --force --pretty
```

Build the resolver image once so the baked fallback still exists:

```bash
docker compose -f resolving/containerization/docker-compose.yml build resolver-cargo
```

Then verify the resolver is actively using the shared mount:

```bash
python3 main.py health --ecosystem cargo
```

The health payload should report:

- `runtime_registry_source = shared`
- `runtime_registry_active_path = /cargo-preprocess/local-registry`

Run a normal resolve afterward:

```bash
python3 main.py resolve --ecosystem cargo --name rand --version 0.8.5 --format graph --return-raw
```

### Refresh shared metadata without rebuilding the resolver image

After the initial resolver image build, later metadata refreshes should only require:

```bash
python3 pre-process/cargo/build.py update --pretty
python3 pre-process/cargo/build.py prepare-local-registry --force --pretty
```

Then rerun health or resolve:

```bash
python3 main.py health --ecosystem cargo
python3 main.py resolve --ecosystem cargo --name anyhow --version 1.0.56 --format graph --return-raw
```

No `resolver-cargo` image rebuild is required for that refresh path because the container reads from the mounted preprocess-managed `local-registry`.

### Override the shared mount path

If the shared local-registry lives somewhere else on the host, set:

```bash
export CARGO_PREPROCESS_LOCAL_REGISTRY_HOST_PATH=/absolute/path/to/local-registry
```

before running `docker compose ...` or `python3 main.py ...`.
If that override path is missing or incomplete, the resolver automatically falls back to the baked image snapshot and health will show `runtime_registry_source = baked`.
