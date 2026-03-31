# Cargo Pre-process and Resolver Refactor Tasks

## Selected Direction

- Upstream `crates.io-index` remains the source of truth for Cargo package metadata.
- v1 should solve the resolver's per-request registry refresh behavior first by moving the runtime source shape from the current git-style file registry to `local-registry`.
- v1 should preserve the existing Cargo-native dependency solving path in `resolving/containerization/images/cargo/src/resolver.rs` while the source migration is being stabilized.
- v1 should not introduce PostgreSQL for Cargo preprocessing.
- v1 should not replace Cargo's dependency solver with a custom semver solver.
- v1 should not require `.crate` artifacts for the first mainline resolver migration.
- `pre-process/cargo` should become an index manager, not a crawler and not a database-backed metadata pipeline.
- During the active refactor, the committed image bootstrap path may continue staging a repository-local `crates.io-index` checkout into the resolver image to keep iteration fast.
- The current refactor-stage runtime root is `/opt/opendep/cargo-runtime`, and the committed Cargo config should resolve exclusively through that runtime root.
- Before the Cargo refactor is closed, that temporary repository-local snapshot bootstrap should be replaced by either:
  - in-image `git clone`
  - preprocess-managed shared Cargo metadata
- Query-scoped index snapshots are a possible later optimization, but they are not part of the first mainline refactor.

## Constraints and Findings Already Confirmed

- The active runtime path is:
  - `resolving/containerization/runtime/cargo_adapter.py`
  - `/usr/local/bin/cargo-resolver`
  - `resolving/containerization/images/cargo/src/resolver.rs`
- The current refactor-stage runtime layout is:
  - Cargo config under `/opt/opendep/cargo-runtime/.cargo/config.toml`
  - staged `local-registry` under `/opt/opendep/cargo-runtime/local-registry`
  - backend process launched with `cwd=/opt/opendep/cargo-runtime`
- The current legacy Cargo source configuration is a git-style file registry:
  - `registry = "file:///app/crates.io-index/"`
- That source shape triggers repeated refresh work during resolve:
  - `Updating 'mirror' index`
  - `git fetch --force --update-head-ok 'file:///app/crates.io-index/' ...`
- The current resolver performs two resolves per request:
  - one resolve to collect root features
  - one resolve to build the final dependency graph
- Resolver-side experiments have already shown:
  - a root-only local-registry subset fails because transitive dependency index entries are missing
  - a dependency-closure-complete local-registry subset succeeds for the current OpenDep resolver without `.crate` files
  - generic Cargo CLI behavior should not be used as the primary validation target for this migration
- A full-index `local-registry` runtime experiment with otherwise unchanged resolver logic has already shown:
  - `anyhow@1.0.56` still resolves to `12` nodes and `11` edges
  - `rand@0.8.5` still resolves to `20` nodes and `31` edges
  - `tokio@1.38.0` still resolves to `56` nodes and `71` edges
  - repeated runs no longer emit `Updating 'mirror' index`
  - repeated runs no longer emit `git fetch ... file:///app/crates.io-index/ ...`
- Reusing a repository-local `crates.io-index` checkout keeps iteration faster while the refactor is active, but it also inflates Docker build context size significantly, so it should remain a temporary bootstrap choice rather than the final architecture.
- The current committed Dockerfile expects that repository-local snapshot to exist before build at:
  - `resolving/containerization/images/cargo/crates.io-index/`

## Working Assumptions

- `pre-process/cargo` should manage:
  - clone
  - update
  - status
  - preparation of a resolver-consumable `local-registry`
- `resolving/cargo` should consume prepared Cargo metadata; it should not be responsible for refreshing git state during request handling.
- During migration, the resolver should support a clear bootstrap story:
  - repository-local snapshot staging as the temporary refactor-stage bootstrap
  - baked-in image clone or preprocess-managed shared data as the closing-state bootstrap
- While Phase B remains active, it is acceptable to optimize for local iteration speed over formal bootstrap completeness.
- The workflow should stay Docker-first, consistent with the rest of `pre-process/`.
- The migration should be delivered in small, reviewable phases.
- Each completed phase should be committed independently.

## Task Breakdown

### Phase A. Freeze Scope and Record the Baseline

- [x] Add `pre-process/cargo/tasks.md` and record the selected Cargo refactor direction.
- [x] Record the current git-style registry behavior and why it triggers per-request refresh work.
- [x] Record the current double-resolve behavior in `resolver.rs`.
- [x] Record the local-registry experiment outcome:
  - incomplete index subset fails on missing transitive dependencies
  - dependency-closure-complete index subset succeeds for the OpenDep resolver without `.crate` files
- [x] Define a small baseline validation set for later regression checks:
  - `anyhow@1.0.56`
  - `rand@0.8.5`
  - `tokio@1.38.0`
- [x] Record the non-goals for the first Cargo refactor PR so the scope stays narrow.

### Phase B. Formalize `resolving/cargo` Runtime Migration to `local-registry`

- [x] Run an isolated experiment showing that changing only the runtime source shape to `local-registry` removes registry refresh logs while preserving baseline graph outputs.
- [x] Replace the current git-style file registry configuration with an official `local-registry` runtime configuration.
- [x] Keep `resolving/containerization/images/cargo/src/resolver.rs` behavior unchanged during this phase.
- [x] Keep staging a repository-local `crates.io-index` snapshot into a resolver-consumable `local-registry` layout while the refactor is still moving quickly.
- [x] Make the runtime Cargo config loading path deterministic instead of depending on accidental `/app/.cargo` discovery.
- [x] Document that the repository-local snapshot bootstrap is temporary and must be replaced before the Cargo refactor is considered complete.
- [x] Add or document a single canonical bootstrap step for refreshing the repository-local snapshot used by the current Docker build:
  - `bash pre-process/cargo/refresh_local_snapshot.sh`
- [x] Validate again through `main.py resolve --ecosystem cargo ... --return-raw` that:
  - baseline graph metrics remain stable
  - `raw.stderr` no longer contains `Updating 'mirror' index`
  - `raw.stderr` no longer contains `git fetch ... file:///app/crates.io-index/ ...`

- [ ] Before closing the Cargo refactor, replace the temporary repository-local snapshot bootstrap with either:
  - in-image `git clone`
  - preprocess-managed shared data

### Phase C. Build `pre-process/cargo` as an Official Index Manager

- [x] Expand `pre-process/cargo/` from a placeholder into a real index-management workspace.
- [x] Add a Docker-friendly entrypoint for Cargo index operations.
- [x] Define the managed data layout for:
  - the upstream git clone
  - the prepared resolver-consumable `local-registry`
- [x] Support cloning the upstream `crates.io-index`.
- [x] Support updating an existing clone.
- [x] Support reporting local status, such as current revision, dirty state, and last update time.
- [x] Support preparing a resolver-consumable `local-registry` layout from the managed index.
- [x] Keep the implementation intentionally narrow:
  - no PostgreSQL schema
  - no dependency-edge tables
  - no custom dependency solver
  - no crawler-style daemon workflow
- [x] Add README examples for clone, update, status, and `prepare-local-registry`.

### Phase D. Integrate Shared Cargo Metadata Between `pre-process/cargo` and `resolving/cargo`

- [x] Mount a preprocess-managed Cargo `local-registry` into `resolver-cargo` so metadata refreshes no longer require rebuilding the resolver image.
- [x] Decide the runtime precedence model:
  - prefer mounted preprocess-managed `local-registry`
  - fall back to baked-in image data when no external mount is present
- [x] Wire the mount and configuration path through `resolving/containerization/docker-compose.yml`.
- [x] Document the operator workflow for:
  - bootstrapping shared Cargo metadata
  - refreshing shared Cargo metadata
  - running the resolver against the shared mount
- [x] Validate end-to-end that a preprocess refresh can change resolver-visible Cargo metadata without rebuilding the resolver image.

### Phase E. Remove the Double Resolve and Read Root Features from the Index

- [ ] Add a helper that locates the correct registry index entry for a `(crate, version)` pair.
- [ ] Parse root crate feature names directly from index metadata instead of running a first resolve.
- [ ] Support both `features` and `features2` when collecting the root feature set.
- [ ] Account for optional dependency feature exposure as needed for compatibility with current graph results.
- [ ] Keep the final graph-building path on the existing Cargo-native resolve implementation.
- [ ] Add tests or fixture-based validation for index-entry parsing.
- [ ] Verify that representative graph outputs remain unchanged after this refactor.
- [ ] Verify that repeated resolver runs now perform one resolve instead of two.

### Phase F. Cleanup, Hardening, and Follow-up Design

- [ ] Simplify the Cargo image bootstrap logic once shared `local-registry` mode is stable.
- [ ] Review whether the baked-in image clone should remain:
  - as the default bootstrap fallback
  - or only as an optional compatibility path
- [ ] Make the runtime Cargo source selection logic explicit in documentation and code comments where needed.
- [ ] Isolate or document legacy Cargo image code that is no longer on the active resolver path.
- [ ] Validate whether a full-index `local-registry` remains acceptable in practice for the resolver workload.
- [ ] If full-index `local-registry` proves too heavy, design a later query-scoped index snapshot optimization.
- [ ] If future Cargo workflows need more than dependency-graph resolution, re-evaluate whether `.crate` artifacts need to become part of the managed data contract.

## Acceptance Criteria

- Repeated Cargo resolves no longer emit git-style registry refresh logs.
- Representative dependency-graph results remain stable across the source migration.
- The current refactor-stage runtime root and `local-registry` layout are explicit rather than relying on accidental `/app/.cargo` discovery.
- The resolver has a documented non-ad-hoc bootstrap path by the end of the refactor, either:
  - image-side clone
  - preprocess-managed shared data
- `pre-process/cargo` manages Cargo index lifecycle without introducing a Cargo-specific database schema.
- `resolver-cargo` can consume a preprocess-managed shared `local-registry` with a clear fallback to baked-in data.
- After the resolver optimization phase, Cargo requests perform one resolve instead of two.
- The migration preserves the Docker-first developer workflow already used in this repository.

## Explicitly Deferred From the First Mainline Cargo Refactor

- PostgreSQL-backed Cargo metadata storage
- a custom Cargo dependency solver
- full artifact management for `.crate` files
- query-scoped index snapshot generation
- batch analytics tables for dependency edges
- crawler-style continuous sync
- cleanup of every historical Cargo image helper in the same PR
