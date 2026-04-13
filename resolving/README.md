# resolving

`resolving/` is the resolver subsystem behind the repository-root `main.py` entrypoint.

## What It Does

The resolver subsystem is responsible for:

- defining the shared request and response contract
- loading the active resolver registry
- selecting the correct backend for an ecosystem and command
- launching the configured resolver service
- normalizing backend output into a shared response envelope

## Request Path

The current container-backed request path is:

```text
main.py
  -> resolving/gateway/
  -> resolving/config/
  -> resolving/containerization/docker_gateway_proxy.py
  -> docker compose run <resolver-service>
  -> resolving/containerization/runtime/<ecosystem>_adapter.py
  -> resolving/containerization/images/<ecosystem>/
  -> normalized response
```

## Current Support

The current container registry
[`resolving/config/resolvers.container.json`](config/resolvers.container.json)
advertises:

| Ecosystem | Commands | Formats | Runtime contract |
| --- | --- | --- | --- |
| `pip` | `resolve`, `health`, `capabilities` | `graph` | `online` or `indexed` metadata, with PostgreSQL-backed `pip_metadata` in indexed mode |
| `npm` | `resolve`, `health`, `capabilities` | `graph` | `online` or `indexed` metadata, with PostgreSQL-backed `npm_metadata` served through an adapter-managed local HTTP shim in indexed mode |
| `maven` | `resolve`, `health`, `capabilities` | `graph` | shared `.m2` cache contract through `resolver-maven-m2-cache` |
| `cargo` | `resolve`, `health`, `capabilities` | `graph`, `full` | `indexed` reads the shared Cargo `local-registry`; `online` resolves against crates.io and reuses the same shared volume for Cargo cache data |
| `go` | `resolve`, `list`, `health`, `capabilities` | `graph`, `full` | `online` or `indexed` metadata, with PostgreSQL-backed `go_metadata` in indexed mode |