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

Local non-Docker commands manage data under:

- `pre-process/cargo/data/`

The Docker-first workflow in [docker-compose.yml](/Users/xingyu/project/Paper/OpenDep/pre-process/cargo/docker-compose.yml) overrides the data root to:

- `/cargo-preprocess-data`

backed by the named Docker volume:

- `opendep-cargo-preprocess-data`

You can override that shared volume name through `CARGO_PREPROCESS_DATA_VOLUME_NAME` in both the preprocess and resolver compose stacks.

Within a given data root, the managed layout is:

- managed git clone: `<data-root>/crates.io-index/`
- prepared local-registry: `<data-root>/local-registry/`

Phase C introduced the managed data layout, and Phase D wires the prepared `local-registry` into the active resolver runtime.
The resolver image no longer depends on a repository-local snapshot under `resolving/containerization/images/cargo/crates.io-index/`.
For the Docker-first shared path, that runtime metadata contract is the shared volume mount under `/cargo-preprocess-data/local-registry/`.

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
local-registry = "/cargo-preprocess-data/local-registry"
```

The resolver image build now only compiles the native backend and stages the runtime Cargo config in:

- [Dockerfile](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/images/cargo/Dockerfile)

The resolver runtime now depends on a preprocess-managed `local-registry` being mounted from the shared Docker volume at `/cargo-preprocess-data/local-registry`.
The adapter runs the native backend from an explicit Cargo runtime root rather than relying on `/app/.cargo` discovery:

- [cargo_adapter.py](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/runtime/cargo_adapter.py)

Phase E also removed the old double-resolve behavior.
The resolver now reads root feature names directly from the staged registry index in:

- [registry_index.rs](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/images/cargo/src/registry_index.rs)

and then performs one final Cargo-native resolve in:

- [resolver.rs](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/images/cargo/src/resolver.rs)

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

### Historical double-resolve behavior

Before Phase E, the resolver performed two resolves per request:

- one resolve to collect root feature names
- one resolve to build the final graph

That older behavior was a major reason the previous git-style registry refresh path was so expensive.
The active resolver no longer does this.
It now reads root feature names directly from [registry_index.rs](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/images/cargo/src/registry_index.rs) and performs one final Cargo-native resolve.

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

## Current Outcome

Phases A through E have now established the active Cargo mainline:

1. the resolver runtime uses `local-registry` instead of a git-style file registry
2. `pre-process/cargo/` manages clone, update, status, and `prepare-local-registry`
3. `resolver-cargo` consumes the shared preprocess-managed `local-registry` as its only metadata source
4. the resolver reads root features from the registry index and performs one final Cargo-native resolve

Phase F focuses on cleanup, documentation hardening, and recording the remaining architectural decisions.

## Current Bootstrap Step

The preprocess-managed `local-registry` is now the only Cargo metadata source used by `resolver-cargo`.
For the shared Docker workflow, prepare that metadata through the preprocess container first:

```bash
docker compose -f pre-process/cargo/docker-compose.yml run --rm cargo-preprocess clone --pretty
docker compose -f pre-process/cargo/docker-compose.yml run --rm cargo-preprocess prepare-local-registry --force --pretty
```

Then build the resolver image from the repository root:

```bash
docker compose -f resolving/containerization/docker-compose.yml build resolver-cargo
```

The repository-root `.dockerignore` intentionally excludes:

- `pre-process/cargo/data/`
- `resolving/containerization/images/cargo/crates.io-index/`

from resolver image builds, because shared preprocess data should be mounted at runtime and legacy local snapshots should not affect the Docker context.

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

Those Docker commands all operate on the shared named volume `opendep-cargo-preprocess-data` by default, so the resolver can consume the same prepared metadata without any host-path bind mount.

## Phase D Shared Runtime Integration

`resolver-cargo` now mounts the preprocess-managed local-registry by default from:

- the named Docker volume `opendep-cargo-preprocess-data`

through:

- [docker-compose.yml](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/docker-compose.yml)

Inside the resolver container, the adapter now expects that shared metadata at a single path:

- `/cargo-preprocess-data/local-registry`

That means the normal Phase D workflow is now:

1. Prepare or refresh the shared local-registry in the Docker volume `opendep-cargo-preprocess-data`.
2. Run the resolver through the normal compose-backed entrypoints.
3. Let the adapter validate the mounted preprocess-managed `local-registry` before serving requests.

### Recommended shared workflow

Bootstrap shared Cargo metadata:

```bash
docker compose -f pre-process/cargo/docker-compose.yml run --rm cargo-preprocess clone --pretty
docker compose -f pre-process/cargo/docker-compose.yml run --rm cargo-preprocess prepare-local-registry --force --pretty
```

Build the resolver image from the repository root:

```bash
docker compose -f resolving/containerization/docker-compose.yml build resolver-cargo
```

Then verify the resolver is actively using the shared mount:

```bash
python3 main.py health --ecosystem cargo
```

The health payload should report:

- `runtime_registry_source = preprocess-shared`
- `runtime_registry_active_path = /cargo-preprocess-data/local-registry`

Run a normal resolve afterward:

```bash
python3 main.py resolve --ecosystem cargo --name rand --version 0.8.5 --format graph --return-raw
```

### Refresh shared metadata without rebuilding the resolver image

After the initial resolver image build, later metadata refreshes should only require:

```bash
docker compose -f pre-process/cargo/docker-compose.yml run --rm cargo-preprocess update --pretty
docker compose -f pre-process/cargo/docker-compose.yml run --rm cargo-preprocess prepare-local-registry --force --pretty
```

Then rerun health or resolve:

```bash
python3 main.py health --ecosystem cargo
python3 main.py resolve --ecosystem cargo --name anyhow --version 1.0.56 --format graph --return-raw
```

No `resolver-cargo` image rebuild is required for that refresh path because the container reads from the mounted preprocess-managed `local-registry`.

### Override the shared volume name

If you want a different shared Docker volume name, set:

```bash
export CARGO_PREPROCESS_DATA_VOLUME_NAME=my-opendep-cargo-data
```

before running either compose stack.
Both [pre-process/cargo/docker-compose.yml](/Users/xingyu/project/Paper/OpenDep/pre-process/cargo/docker-compose.yml) and [resolving/containerization/docker-compose.yml](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/docker-compose.yml) must use the same value.
If the shared volume is missing or incomplete, the resolver fails fast and health reports a degraded state until the mount contract is satisfied.

## Phase F Decisions

The current hardening-stage decisions are:

- The steady-state operational path is a shared preprocess-managed full-index `local-registry`.
- The shared Docker-first contract uses the named volume `opendep-cargo-preprocess-data`, mounted at `/cargo-preprocess-data` inside both the preprocess and resolver containers.
- `resolver-cargo` no longer carries a baked registry snapshot fallback. It consumes the preprocess-managed mount as its only metadata source.
- The old repository-local snapshot refresh script has been retired.
- The Cargo image build should not consume `pre-process/cargo/data/` directly. That data is runtime-mounted only.
- The Cargo image build should not consume a legacy local `resolving/containerization/images/cargo/crates.io-index/` checkout either. If such a checkout still exists on a developer machine, it is now ignored by Docker builds and can be deleted.
- The active resolver entrypoint is:
  - [cargo_resolver.rs](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/images/cargo/src/bin/cargo_resolver.rs)
- The following binaries and modules are not on the active `resolver-cargo` request path:
  - [main.rs](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/images/cargo/src/main.rs)
  - [get_deps.rs](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/images/cargo/src/bin/get_deps.rs)
  - [count_deps.rs](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/images/cargo/src/bin/count_deps.rs)
  - [complete_deps.rs](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/images/cargo/src/bin/complete_deps.rs)
  - [batch/](/Users/xingyu/project/Paper/OpenDep/resolving/containerization/images/cargo/src/batch)

### Full-index `local-registry` viability

The current shared full-index `local-registry` is approximately `4.1G` on disk in this workspace.
That is acceptable for the current mounted runtime path because:

- the resolver no longer copies that directory into every image build
- runtime health and baseline graph resolves remain stable
- representative backend durations remain in the low hundreds of milliseconds

It is not acceptable as a repeatedly copied Docker build-context input.
That is why the current `.dockerignore` excludes `pre-process/cargo/data/`, and why a later query-scoped snapshot optimization remains on the roadmap if the shared full-index layout becomes operationally too heavy.

### Future follow-up boundaries

- Query-scoped index snapshots are still a later optimization, not part of the current mainline.
- `.crate` artifacts are still out of scope for the current graph-only resolver path.
- If future Cargo workflows expand beyond dependency-graph resolution, revisit whether `.crate` files need to become part of the managed data contract.
