---
layout: default
title: Architecture
description: OpenDep's gateway, resolver containers, request path, shared data contracts, and extension model.
permalink: /architecture/
---

OpenDep separates the user-facing interface, gateway logic, containerized resolver services, and preprocessing pipelines. This modular design keeps the command-line interface stable while allowing ecosystem-specific resolver behavior behind the gateway.

## Repository Layout

```text
code/
  main.py                         # unified CLI entrypoint
  resolving/                      # resolver gateway and runtime stack
    gateway/                      # validation, routing, dispatch, response normalization
    config/                       # resolver registry
    containerization/             # Docker Compose resolver services and adapters
    spec/                         # shared request and response schemas
  pre-process/                    # ecosystem metadata preprocessing
    common/                       # shared helpers and PostgreSQL assets
    pip/
    npm/
    go/
    cargo/
    maven/
```

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

## Main Components

| Component | Role |
| --- | --- |
| CLI | Parses user commands and builds normalized request payloads |
| Gateway | Validates requests, selects resolver backend, and normalizes responses |
| Resolver registry | Describes available resolver services, commands, and formats |
| Containerized resolvers | Execute ecosystem-specific resolution logic |
| Runtime adapters | Convert backend-native output into the OpenDep response contract |
| Preprocess pipelines | Prepare local metadata stores or shared caches for indexed/cache-backed resolution |
| Specification | Defines shared request and response schemas |

## Gateway Responsibilities

The resolving gateway is responsible for:

- Validating and normalizing incoming request data.
- Loading the active resolver registry.
- Checking command and format compatibility before launching a backend.
- Selecting the correct resolver for the requested ecosystem.
- Invoking the configured backend launcher.
- Normalizing backend output into the shared response envelope.

## Container Resolver Services

| Ecosystem | Compose service | Commands | Formats | Mode or contract |
| --- | --- | --- | --- | --- |
| pip | `resolver-pip` | `resolve`, `health`, `capabilities` | `graph` | `online` or `indexed` |
| npm | `resolver-npm` | `resolve`, `health`, `capabilities` | `graph` | `online` or `indexed` |
| Go | `resolver-go` | `resolve`, `list`, `health`, `capabilities` | `graph`, `full` | `online` or `indexed` |
| Cargo | `resolver-cargo` | `resolve`, `health`, `capabilities` | `graph`, `full` | `online` or `indexed` |
| Maven | `resolver-maven` | `resolve`, `health`, `capabilities` | `graph` | shared `.m2` cache |

## Shared Data Contracts

| Ecosystem | Shared data contract |
| --- | --- |
| pip | In indexed mode, reads from PostgreSQL table `pip_metadata`; online mode can reuse resolver cache volume |
| npm | In indexed mode, reads from PostgreSQL table `npm_metadata` through an adapter-managed local HTTP shim |
| Go | In indexed mode, reads from PostgreSQL table `go_metadata` |
| Cargo | Reads a prepared `local-registry/` from Docker volume `resolver-cargo-cache` in indexed mode |
| Maven | Reuses warmed `.m2/repository` data from Docker volume `resolver-maven-m2-cache` |

## Extension Model

The architecture is designed so that new ecosystems or resolver backends can be added without changing the user-facing command pattern.

To extend OpenDep, developers usually inspect or modify:

- `resolving/config/resolvers.container.json`
- `resolving/containerization/docker-compose.yml`
- `resolving/containerization/runtime/<ecosystem>_adapter.py`
- `resolving/containerization/images/<ecosystem>/`
- `resolving/spec/request.schema.json`
- `resolving/spec/response.schema.json`

The new backend should return data that can be normalized into the shared OpenDep response envelope.

## Suggested Figure

<figure class="figure">
  <img src="{{ '/assets/img/architecture.png' | relative_url }}" alt="OpenDep dependency resolution workflow">
  <figcaption>OpenDep dependency resolution workflow. The host-side CLI and gateway provide a unified interface, while containerized ecosystem-specific backends perform resolution and return normalized dependency graph results.</figcaption>
</figure>
