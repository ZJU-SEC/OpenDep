# Cargo Pre-process Workspace

`pre-process/cargo/` manages the shared Cargo metadata source used by the resolver. Instead of loading Cargo metadata into PostgreSQL, it clones [`crates.io-index`](https://github.com/rust-lang/crates.io-index), refreshes that clone, and prepares a resolver-consumable `local-registry`.

## What It Does

The Cargo preprocess workspace currently provides four operations:

- `clone` / `update`
- `prepare-local-registry`

In practice, that means: keep a managed `crates.io-index` clone and materialize a shared `local-registry` layout for the resolver


## Managed Files and Paths

The Docker workflow overrides the data root to:

- `/cargo-preprocess-data`

backed by the named Docker volume:

- `opendep-cargo-preprocess-data`

Within a data root, the managed layout is:

- managed index clone: `<data-root>/crates.io-index/`
- prepared registry: `<data-root>/local-registry/`

You can override the shared Docker volume name with `CARGO_PREPROCESS_DATA_VOLUME_NAME`, but the preprocess and resolver stacks must use the same value.

## Resolver-side Configuration

The active Cargo resolver reads from a preprocess-managed `local-registry`.

The resolver-side Cargo config points at:

```toml
[source.mirror]
local-registry = "/cargo-preprocess-data/local-registry"
```

## Workflow

Build the preprocess image:

```bash
docker compose -f pre-process/cargo/docker-compose.yml build cargo-preprocess
```

Bootstrap the shared Cargo metadata:

```bash
docker compose -f pre-process/cargo/docker-compose.yml run --rm cargo-preprocess clone --pretty
docker compose -f pre-process/cargo/docker-compose.yml run --rm cargo-preprocess prepare-local-registry --force --pretty
```

Build the resolver image:

```bash
docker compose -f resolving/containerization/docker-compose.yml build resolver-cargo
```

Check that the resolver sees the shared registry:

```bash
python3 main.py health --ecosystem cargo
```

Then run a resolve:

```bash
python3 main.py resolve --ecosystem cargo --name rand --version 0.8.5 --format graph
```

## Refreshing Shared Metadata

```bash
docker compose -f pre-process/cargo/docker-compose.yml run --rm cargo-preprocess update --pretty
docker compose -f pre-process/cargo/docker-compose.yml run --rm cargo-preprocess prepare-local-registry --force --pretty
```
