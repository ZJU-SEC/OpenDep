# Cargo Pre-process Workspace

`pre-process/cargo/` manages the shared Cargo metadata source used by the indexed resolver path. Instead of loading Cargo metadata into PostgreSQL, it clones [`crates.io-index`](https://github.com/rust-lang/crates.io-index), refreshes that clone, and prepares a resolver-consumable `local-registry`.

## What It Does

The Cargo preprocess workspace provides three entrypoints:

- `clone` / `update`
- `prepare-local-registry`

In practice, that means: keep a managed `crates.io-index` clone and materialize
a shared `local-registry` layout for indexed resolution.


## Managed Files and Paths

The Docker workflow overrides the data root to:

- `/cargo-preprocess-data`

backed by the named Docker volume:

- `resolver-cargo-cache`

Within a data root, the managed layout is:

- managed index clone: `<data-root>/crates.io-index/`
- prepared registry: `<data-root>/local-registry/`

You can override the shared Docker volume name with `CARGO_DATA_VOLUME_NAME`, but the preprocess and resolver stacks must use the same value.

## Resolver-side Configuration

The preprocess and resolver stacks share one Docker volume, but they mount it
at different container paths:

- preprocess writes to `/cargo-preprocess-data`
- resolver reads the same volume at `/cargo-data`

## Workflow

Build the preprocess image:

```bash
docker compose -f pre-process/cargo/docker-compose.yml build cargo-preprocess
```

Bootstrap the shared Cargo metadata for `indexed` mode:

```bash
docker compose -f pre-process/cargo/docker-compose.yml run --rm cargo-preprocess clone --pretty
docker compose -f pre-process/cargo/docker-compose.yml run --rm cargo-preprocess prepare-local-registry --force --pretty
```

Build the resolver image:

```bash
docker compose -f resolving/containerization/docker-compose.yml build resolver-cargo
```

Check resolver health:

```bash
python3 main.py health --ecosystem cargo --cargo-mode indexed
```

Then run a resolve:

```bash
python3 main.py resolve --ecosystem cargo --name rand --version 0.8.5 --format graph --cargo-mode indexed
```

## Refreshing Shared Metadata

```bash
docker compose -f pre-process/cargo/docker-compose.yml run --rm cargo-preprocess update --pretty
docker compose -f pre-process/cargo/docker-compose.yml run --rm cargo-preprocess prepare-local-registry --force --pretty
```
