# Pre-process Workspace

This directory hosts preprocessing and database-loading code for dependency datasets.

Its scope is intentionally narrow:

- adapt raw crawler or resolver outputs into a stable internal shape
- normalize ecosystem-specific metadata into shared records
- write processed records into the target database

The directory names follow the active ecosystem identifiers already used in `resolving/`:

- `pip` for Python
- `npm` for JavaScript / Node.js
- `maven` for Java
- `cargo` for Rust
- `go` for Go

## Layout

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

## Directory conventions

- `common/`: shared code used across all ecosystems
- `adapters/`: bridges from legacy scripts, crawler output, or resolver output into the preprocessing flow
- `pipeline/`: ecosystem-specific cleaning, normalization, enrichment, and graph shaping
- `loaders/`: database write paths such as bulk import, upsert, and backfill entrypoints

This is only the initial scaffold so future migrations can happen incrementally without rethinking the directory shape.
