# resolving Specification

This directory contains the shared protocol artifacts for the OpenDep resolver
stack. These files document the request/response model exchanged between
`main.py`, the gateway, and the container adapters.

## Scope

The specification in this directory covers:

- `resolving/spec/request.schema.json` — request schema reference
- `resolving/spec/response.schema.json` — response schema reference
- `resolving/spec/examples/request/` — sample request payloads
- `resolving/spec/examples/response/` — sample response payloads

The current example set now includes sample payloads for:

- `resolve`
- `list`
- `health`
- `capabilities`

These schema and example files define the shared request/response envelope,
not the full per-ecosystem capability matrix. Actual command, format, and
feature support is advertised by the primary resolver registry in
[`resolving/config/resolvers.container.yaml`](../config/resolvers.container.yaml).

## Current Capability Alignment

The primary registry for the current container stack advertises:

| Ecosystem | Commands | Formats | Features |
| --- | --- | --- | --- |
| `pip` | `resolve`, `health`, `capabilities` | `graph` | `raw`, `markers`, `extras`, `cache`, `indexed`, `live` |
| `npm` | `resolve`, `health`, `capabilities` | `graph` | `raw`, `peer-dependencies`, `directory-tree` |
| `maven` | `resolve`, `health`, `capabilities` | `graph` | `raw`, `scopes`, `managed-dependencies` |
| `cargo` | `resolve`, `health`, `capabilities` | `graph`, `full` | `raw`, `features`, `registry`, `cache` |
| `go` | `resolve`, `list`, `health`, `capabilities` | `graph`, `full` | `raw`, `replace`, `exclude`, `buildlist` |

The shared request schema allows `resolve`, `list`, `health`, and
`capabilities` globally, but not every resolver implements every command.
Callers should treat registry-backed `capabilities` output as the source of
truth for a selected ecosystem.

## Error Codes

The resolver specification uses a shared cross-ecosystem error taxonomy.
Individual backends may have richer native error states, but adapters should map them into these codes whenever possible.

### Core taxonomy

| Code                      | Meaning                                                                     |
| ------------------------- | --------------------------------------------------------------------------- |
| `INVALID_ARGUMENT`        | The request is malformed or missing required fields.                        |
| `UNSUPPORTED_COMMAND`     | The requested command is not supported by the selected resolver.            |
| `UNSUPPORTED_ECOSYSTEM`   | No resolver is registered for the requested ecosystem.                      |
| `UNSUPPORTED_OPTION`      | A request option is invalid for the selected resolver.                      |
| `PACKAGE_NOT_FOUND`       | The package or module name could not be found.                              |
| `VERSION_NOT_FOUND`       | The package exists, but the requested version could not be found.           |
| `RESOLUTION_CONFLICT`     | Dependency solving failed because the requested graph is incompatible.      |
| `DATA_SOURCE_UNAVAILABLE` | The backend could not reach or use its upstream metadata source.            |
| `BACKEND_MISCONFIGURED`   | A required binary, jar, runtime, or config file is missing.                 |
| `TIMEOUT`                 | The backend did not finish before the configured timeout.                   |
| `BACKEND_CRASHED`         | The backend process exited unexpectedly or with an unclassified failure.    |
| `PROTOCOL_ERROR`          | The backend or adapter returned output that violates the expected contract. |
| `INTERNAL_ERROR`          | An unexpected contract or gateway-layer failure occurred.                   |

### Adapter guidance

Adapters should preserve backend-native details in `raw` when `return_raw` is enabled.
That lets callers inspect stderr, exit codes, or backend payloads without leaking ecosystem-specific structures into the shared contract by default.

## Result Model

The resolver specification uses a common response envelope, but the shape of `result` depends on the command.

### Shared response envelope

Successful responses always include:

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

Many successful responses also include top-level `metrics` when the adapter can expose them directly.

### `resolve` result

`resolve` is graph-oriented.
The normalized result usually includes:

- `root`
- `nodes`
- `edges`
- `semantics`
- `metrics`

The requested `options.format` is ecosystem-specific.
In the current stack:

- `graph` is supported across all five ecosystems
- `full` is currently advertised by `cargo` and `go`

Example root object:

```json
{
  "id": "go:k8s.io/apimachinery@v0.35.2",
  "path": "k8s.io/apimachinery",
  "version": "v0.35.2"
}
```

### `list` result

`list` is currently implemented for Go. Its result is exposed under
`result.list`.

Example:

```json
{
  "list": {
    "root": {
      "path": "github.com/rogpeppe/godef",
      "version": "v1.1.2"
    },
    "entries": [
      {
        "path": "9fans.net/go",
        "version": "v0.0.0-20181112161441-237454027057"
      }
    ],
    "metrics": {
      "entry_count": 9
    }
  }
}
```

### `health` result

`health` returns a command-specific object under `result.health`.
The exact checks are resolver-specific.

Example:

```json
{
  "health": {
    "state": "ok",
    "checks": [
      {"name": "backend_binary", "status": "ok"}
    ]
  }
}
```

### `capabilities` result

`capabilities` returns a command-specific object under `result.capabilities`.

Example:

```json
{
  "capabilities": {
    "commands": ["resolve", "list", "health", "capabilities"],
    "formats": ["graph", "full"],
    "features": ["raw", "replace", "exclude", "buildlist", "indexed-postgres"],
    "metadata_modes": ["online", "indexed"],
    "platform": false
  }
}
```

That object is the runtime-advertised capability summary for the selected
resolver.
For the current container registry, only Go includes `list`, and only Cargo and
Go advertise the `full` format.
Adapter responses may also include extra runtime detail that is not present in
the static registry file, such as `metadata_modes` or more specific feature
labels for indexed backends.

### Raw preservation

When `return_raw` is enabled, adapters may preserve backend-native output in `raw`, including:

- `stdout`
- `stderr`
- `exit_code`
- `backend_payload`

### Metrics

Adapters may copy useful counts to top-level `metrics` for convenience.
For graph-style results, this commonly includes values such as `node_count` and `edge_count`.
For Go `list`, this currently includes `entry_count`.

## Notes

- The current Python validation logic in `resolving/gateway/contract.py` is implemented directly in code.
- These schema, examples, and markdown files remain the documentation source
  for the intended request/response protocol.
- The request schema includes `resolve`, `list`, `health`, and `capabilities`.
- The shared request schema intentionally leaves `options` open-ended so
  ecosystem-specific mode flags and indexed-store settings can pass through the
  gateway without changing the top-level envelope shape.
