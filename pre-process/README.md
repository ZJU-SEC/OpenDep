# Pre-process Workspace

This directory hosts the preprocessing and index-warming entrypoints for the five resolver ecosystems used by OpenDep.

## Current Ecosystem Alignment

| Ecosystem | Primary input unit | Persistent contract | Main entrypoints | Incremental controls | Resolver handoff |
| --- | --- | --- | --- | --- | --- |
| `pip` | package specs or local release artifacts | PostgreSQL `pip_metadata` | `build`, `extract`, `load` | `--backfill`, `--skip-existing`, `--state-file`, `--failure-log` | indexed pip resolver reads `pip_metadata` |
| `npm` | package names or `_changes` batches | PostgreSQL `npm_metadata`, `npm_sync_state`, `npm_tombstones` | `build`, `sync sync-once`, `sync sync-follow` | `--skip-existing`, `_changes` checkpoints, follow mode polling | indexed npm resolver serves packuments from PostgreSQL through a local HTTP shim |
| `maven` | package names or explicit coordinates | shared `.m2` cache volume `resolver-maven-m2-cache` | `warm`, `index-all` | `--sync-mode`, `--state-file`, `--failure-log`, sharding | resolver reuses the warmed `.m2` repository directly |
| `cargo` | managed `crates.io-index` clone | managed data root with `crates.io-index/` and prepared `local-registry/`, typically volume `resolver-cargo-cache` | `clone`, `update`, `prepare-local-registry` | idempotent clone or refresh flow, `--force` for replacement or dirty-reset steps | indexed resolver reads `local-registry/` |
| `go` | `module` or `module@version` requests | PostgreSQL `go_metadata` | `build` | `--skip-existing`, version expansion, fetch concurrency | indexed Go resolver reads `go_metadata`, with online fallback still available |

## Directory Conventions

- `common/`: shared helpers, shared record models, and shared PostgreSQL assets
- `adapters/`: bridges from CLI input, manifests, inventories, registries, or legacy sources into the preprocess flow
- `pipeline/`: ecosystem-specific planning, normalization, enrichment, warming, or staging logic
- `loaders/`: persistence paths such as PostgreSQL upsert or repository layout writes

## Note

- Batch jobs that may run for a long time usually expose resume-oriented state files and structured failure logs.


## Ecosystem Docs

- [`pre-process/pip/README.md`](pip/README.md)
- [`pre-process/npm/README.md`](npm/README.md)
- [`pre-process/maven/README.md`](maven/README.md)
- [`pre-process/cargo/README.md`](cargo/README.md)
- [`pre-process/go/README.md`](go/README.md)
