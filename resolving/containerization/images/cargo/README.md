# Cargo Resolver Image

`resolving/containerization/images/cargo/` packages the Rust backend used by `resolver-cargo`.

## What It Does

The Cargo resolver image:

- compiles the native resolver binary
- supports `indexed` and `online` metadata modes over one shared Cargo data root
- reuses one persistent shared volume for both `local-registry` and Cargo's online cache data
- serves normalized `resolve`, `health`, and `capabilities` responses through the adapter-backed service

## Use Through the Resolver CLI

Prepare the shared Cargo volume first if you plan to use `indexed` mode, using [`pre-process/cargo/README.md`](../../../../pre-process/cargo/README.md).

Example bootstrap:

```bash
docker compose -f pre-process/cargo/docker-compose.yml run --rm cargo-preprocess clone --pretty
docker compose -f pre-process/cargo/docker-compose.yml run --rm cargo-preprocess prepare-local-registry --force --pretty
docker compose -f resolving/containerization/docker-compose.yml build resolver-cargo
python3 main.py health --ecosystem cargo
```

Gateway-facing examples:

```bash
python3 main.py capabilities --ecosystem cargo
python3 main.py resolve --ecosystem cargo --name rand --version 0.8.5 --format graph --cargo-mode indexed
python3 main.py resolve --ecosystem cargo --name rand --version 0.8.5 --format graph --cargo-mode online
```