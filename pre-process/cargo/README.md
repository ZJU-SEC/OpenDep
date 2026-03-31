# Cargo Pre-process Workspace

This workspace is for Rust crate preprocessing and database-loading logic.

- `adapters/`: adapt outputs from the existing `cargo` crawler or resolver paths
- `pipeline/`: clean and normalize crate metadata, features, and dependency edges
- `loaders/`: write processed `cargo` data into the database

Crates.io officially maintains a [git repo](https://github.com/rust-lang/crates.io-index) that manages meta information about all packages, including dependencies. So all we need to do is clone the git repo locally to get efficient access to all the dependency information.

```bash
git clone git@github.com:rust-lang/crates.io-index.git
```