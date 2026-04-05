# resolving Specification

`resolving/spec/` documents the shared request and response contract exchanged between `main.py`, the gateway, and the container adapters.

## What It Covers

- [`resolving/spec/request.schema.json`](request.schema.json) — request schema reference
- [`resolving/spec/response.schema.json`](response.schema.json) — response schema reference
- [`resolving/spec/examples/request/`](examples/request/) — sample request payloads
- [`resolving/spec/examples/response/`](examples/response/) — sample response payloads

## Error Codes

Adapters should map backend-native failures into the shared taxonomy whenever possible.

| Code | Meaning |
| --- | --- |
| `INVALID_ARGUMENT` | The request is malformed or missing required fields. |
| `UNSUPPORTED_COMMAND` | The requested command is not supported by the selected resolver. |
| `UNSUPPORTED_ECOSYSTEM` | No resolver is registered for the requested ecosystem. |
| `UNSUPPORTED_OPTION` | A request option is invalid for the selected resolver. |
| `PACKAGE_NOT_FOUND` | The package or module name could not be found. |
| `VERSION_NOT_FOUND` | The package exists, but the requested version could not be found. |
| `RESOLUTION_CONFLICT` | Dependency solving failed because the requested graph is incompatible. |
| `DATA_SOURCE_UNAVAILABLE` | The backend could not reach or use its upstream metadata source. |
| `BACKEND_MISCONFIGURED` | A required binary, jar, runtime, or config file is missing. |
| `TIMEOUT` | The backend did not finish before the configured timeout. |
| `BACKEND_CRASHED` | The backend process exited unexpectedly or with an unclassified failure. |
| `PROTOCOL_ERROR` | The backend or adapter returned output that violates the expected contract. |
| `INTERNAL_ERROR` | An unexpected contract or gateway-layer failure occurred. |

When `return_raw` is enabled, adapters may preserve backend-native details in
`raw` so callers can inspect stderr, exit codes, or native payloads without
changing the shared default schema.

## Result Shapes

The response envelope stays consistent, but `result` changes by command.

### Shared response envelope

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

### `resolve`

`resolve` returns graph-oriented data under `result`, typically including:

- `root`
- `nodes`
- `edges`
- `semantics`
- `metrics`

Current format support:

- `graph` across all five ecosystems
- `full` for `cargo` and `go`

Example root objects:

Go graph results use `path`:

```json
{
  "id": "go:k8s.io/apimachinery@v0.35.2",
  "path": "k8s.io/apimachinery",
  "version": "v0.35.2"
}
```

pip graph results use `ecosystem` and `name`:

```json
{
  "id": "pip:requests@2.32.5",
  "ecosystem": "pip",
  "name": "requests",
  "version": "2.32.5"
}
```

### `list`

`list` is currently implemented for Go and returns data under `result.list`.

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

### `health`

`health` returns a resolver-specific object under `result.health`.

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

### `capabilities`

`capabilities` returns a resolver-specific object under `result.capabilities`.

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