# resolving Registry Configuration

This directory stores the resolver registry files used by the gateway CLI and
service layer. Each registry declares which backend handles an ecosystem, how
it is launched, and which capabilities the gateway can advertise before
process startup.

## Files

- `resolving/config/resolvers.container.yaml` — the primary registry for the current container resolver stack
- `resolving/config/resolvers.yaml` — a legacy host-process registry kept for comparison with older resolver wiring

## Primary Registry

The current five-ecosystem stack is declared in
[`resolving/config/resolvers.container.yaml`](resolvers.container.yaml).

| Ecosystem | Compose service path | Commands | Formats | Features |
| --- | --- | --- | --- | --- |
| `pip` | `resolver-pip` via `docker_gateway_proxy.py` | `resolve`, `health`, `capabilities` | `graph` | `raw`, `markers`, `extras`, `cache`, `indexed`, `live` |
| `npm` | `resolver-npm` via `docker_gateway_proxy.py` | `resolve`, `health`, `capabilities` | `graph` | `raw`, `peer-dependencies`, `directory-tree` |
| `maven` | `resolver-maven` via `docker_gateway_proxy.py` | `resolve`, `health`, `capabilities` | `graph` | `raw`, `scopes`, `managed-dependencies` |
| `cargo` | `resolver-cargo` via `docker_gateway_proxy.py` | `resolve`, `health`, `capabilities` | `graph`, `full` | `raw`, `features`, `registry`, `cache` |
| `go` | `resolver-go` via `docker_gateway_proxy.py` | `resolve`, `list`, `health`, `capabilities` | `graph`, `full` | `raw`, `replace`, `exclude`, `buildlist` |

The registry is also the pre-start capability source used by
`main.py capabilities`.

## Notes

- The files currently use JSON syntax even though they keep the historical `.yaml` suffix.
- `main.py` auto-selects the container registry for the current five
  ecosystems unless `--config` is supplied explicitly.
- `resolvers.container.yaml` is the primary source for commands, formats,
  timeout defaults, and pre-start feature flags.
- Runtime `capabilities` responses may include extra detail beyond the static
  registry, such as `metadata_modes` or more specific indexed-backend feature
  labels.
- `resolvers.yaml` remains a legacy comparison artifact and is not the normal
  entrypoint for the current stack.
- Registry paths are resolved by `resolving/gateway/config.py`.
- Specification documents live under `resolving/spec/`.
