# Cargo Pre-process Workspace

This workspace is for Rust crate preprocessing and database-loading logic.

- `adapters/`: adapt outputs from the existing `cargo` crawler or resolver paths
- `pipeline/`: clean and normalize crate metadata, features, and dependency edges
- `loaders/`: write processed `cargo` data into the database
