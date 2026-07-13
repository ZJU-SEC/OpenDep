---
layout: default
title: Usage
description: Command-line interface, ecosystem support, resolver modes, and normalized JSON output.
permalink: /usage/
---

OpenDep provides a unified command-line interface through:

```bash
python3 main.py
```

The CLI routes requests through the resolving gateway, selects the configured resolver backend for the requested ecosystem, launches the containerized resolver service, and returns a normalized JSON response.

## Command Pattern

```bash
python3 main.py <command> --ecosystem <ecosystem> [options]
```

Supported commands:

| Command | Purpose |
| --- | --- |
| `resolve` | Resolve a dependency graph for a package or module |
| `list` | List dependency entries when supported |
| `health` | Check resolver and backend health |
| `capabilities` | Show supported commands, formats, and features |

## Common Options

| Option | Meaning |
| --- | --- |
| `--ecosystem` | Target ecosystem: `pip`, `npm`, `go`, `cargo`, or `maven` |
| `--name` | Package, module, or coordinate name |
| `--version` | Package or module version |
| `--format` | Requested output format, usually `graph` |
| `--timeout-ms` | Optional request timeout in milliseconds |
| `--return-raw` | Preserve backend-native stdout, stderr, and payload details |

## Ecosystem Support Matrix

| Ecosystem | Modes | Commands | Formats | Indexed contract |
| --- | --- | --- | --- | --- |
| pip | `online`, `indexed` | `resolve`, `health`, `capabilities` | `graph` | PostgreSQL table `pip_metadata` |
| npm | `online`, `indexed` | `resolve`, `health`, `capabilities` | `graph` | PostgreSQL table `npm_metadata` |
| Go | `online`, `indexed` | `resolve`, `list`, `health`, `capabilities` | `graph`, `full` | PostgreSQL table `go_metadata` |
| Cargo | `online`, `indexed` | `resolve`, `health`, `capabilities` | `graph`, `full` | shared `local-registry/` inside Docker volume `resolver-cargo-cache` |
| Maven | shared-cache mode | `resolve`, `health`, `capabilities` | `graph` | shared `.m2` cache volume `resolver-maven-m2-cache` |

## Resolver Mode Options

### pip

```bash
--pip-mode online
--pip-mode indexed
--pip-index-dsn "$INDEX_DSN"
--pip-index-table pip_metadata
```

### npm

```bash
--npm-mode online
--npm-mode indexed
--npm-index-dsn "$INDEX_DSN"
--npm-index-table npm_metadata
--npm-registry-base-url https://registry.npmjs.org
```

### Go

```bash
--go-mode online
--go-mode indexed
--go-index-dsn "$INDEX_DSN"
--go-index-table go_metadata
```

### Cargo

```bash
--cargo-mode online
--cargo-mode indexed
```

### Maven

Maven currently uses the shared `.m2` cache contract and does not require an explicit mode option.

## Response Format

OpenDep normalizes backend-specific outputs into a shared JSON response envelope.

Successful responses include:

- `schema_version`
- `request_id`
- `trace_id`
- `status`
- `ecosystem`
- `resolver`
- `result`
- `diagnostics`
- `raw`
- `timing`

For `resolve`, the `result` object usually contains:

- `root`
- `nodes`
- `edges`
- `semantics`
- `metrics`

Example simplified response:

```json
{
  "schema_version": "1.0",
  "request_id": "...",
  "trace_id": "...",
  "status": "ok",
  "ecosystem": "pip",
  "resolver": "...",
  "result": {
    "root": {
      "id": "pip:requests@2.32.5",
      "ecosystem": "pip",
      "name": "requests",
      "version": "2.32.5"
    },
    "nodes": [],
    "edges": [],
    "metrics": {}
  },
  "diagnostics": [],
  "raw": null,
  "timing": {}
}
```

## Raw Backend Output

To preserve backend-native details:

```bash
python3 main.py resolve \
  --ecosystem pip \
  --name requests \
  --version 2.32.5 \
  --format graph \
  --pip-mode online \
  --return-raw
```

This is useful for debugging resolver behavior or inspecting backend-specific stderr/stdout.
