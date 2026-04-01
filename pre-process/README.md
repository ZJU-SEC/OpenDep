# Pre-process Workspace

This directory hosts the preprocessing and index-warming entrypoints for the
five resolver ecosystems used by OpenDep.

The current stack uses one workspace layout across ecosystems, with two runtime
contract families:

- PostgreSQL-backed metadata indexing: `pip`, `npm`, `go`
- Shared filesystem or cache contracts: `maven`, `cargo`

## Current Ecosystem Alignment

| Ecosystem | Primary input unit | Persistent contract | Main entrypoints | Incremental controls | Resolver handoff |
| --- | --- | --- | --- | --- | --- |
| `pip` | package specs or local release artifacts | PostgreSQL `pip_metadata` | `build`, `extract`, `load` | `--backfill`, `--skip-existing`, `--state-file`, `--failure-log` | indexed pip resolver reads `pip_metadata` |
| `npm` | package names or `_changes` batches | PostgreSQL `npm_metadata`, `npm_sync_state`, `npm_tombstones` | `build`, `sync sync-once`, `sync sync-follow` | `--skip-existing`, `_changes` checkpoints, follow mode polling | indexed npm resolver serves packuments from PostgreSQL through a local HTTP shim |
| `maven` | package names, inventories, or explicit coordinates | shared `.m2` cache volume `resolver-maven-m2-cache` | `warm`, `index-all` | `--sync-mode`, `--state-file`, `--failure-log`, sharding | resolver reuses the warmed `.m2` repository directly |
| `cargo` | managed `crates.io-index` clone | managed data root with prepared `local-registry` output, typically volume `opendep-cargo-preprocess-data` | `clone`, `update`, `prepare-local-registry` | idempotent clone or refresh flow, `--force` for replacement or dirty-reset steps | resolver mounts the preprocess-managed `local-registry` |
| `go` | `module` or `module@version` requests | PostgreSQL `go_metadata` | `build` | `--skip-existing`, version expansion, fetch concurrency | indexed Go resolver reads `go_metadata`, with online fallback still available |

## Shared Layout

```text
pre-process/
  common/
    database/
    models/
    utils/
  pip/
    adapters/
    pipeline/
    loaders/
  npm/
    adapters/
    pipeline/
    loaders/
  maven/
    adapters/
    pipeline/
    loaders/
  cargo/
    adapters/
    pipeline/
    loaders/
  go/
    adapters/
    pipeline/
    loaders/
```

## Directory Conventions

- `common/`: shared helpers, shared record models, and shared PostgreSQL assets
- `adapters/`: bridges from CLI input, manifests, inventories, registries, or
  legacy sources into the preprocess flow
- `pipeline/`: ecosystem-specific planning, normalization, enrichment, warming,
  or staging logic
- `loaders/`: persistence paths such as PostgreSQL upsert or repository layout
  writes

## Shared Conventions

- The operator workflow is Docker-first across all five ecosystems.
- `pip`, `npm`, and `go` share the PostgreSQL lifecycle described in
  [`pre-process/common/database/README.md`](common/database/README.md).
- `maven` and `cargo` intentionally do not use shared preprocess PostgreSQL
  tables in the current stack.
- Batch jobs that may run for a long time usually expose resume-oriented state
  files and structured failure logs.
- Resolver handoff is ecosystem-specific: database lookup for `pip`, `npm`,
  and `go`; shared warmed cache for `maven`; shared staged `local-registry`
  for `cargo`.

## Ecosystem Docs

- [`pre-process/pip/README.md`](pip/README.md)
- [`pre-process/npm/README.md`](npm/README.md)
- [`pre-process/maven/README.md`](maven/README.md)
- [`pre-process/cargo/README.md`](cargo/README.md)
- [`pre-process/go/README.md`](go/README.md)
