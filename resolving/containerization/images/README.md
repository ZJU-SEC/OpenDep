# resolving Backend Images

`resolving/containerization/images/` contains the ecosystem-specific backend images used by the current container resolver stack.

## What It Contains

Each ecosystem subdirectory owns the files needed to build one backend image for one ecosystem. In practice, these directories contain:

- a `Dockerfile`
- backend source code and build metadata
- ecosystem-specific helper scripts or configuration files
- optional compatibility notes for local workflows

## Current Images

| Ecosystem | Backend form | Directory | Runtime contract |
| --- | --- | --- | --- |
| `pip` | Python backend module | `resolving/containerization/images/pip/` | `online` or `indexed` metadata flow |
| `npm` | native C++ binary | `resolving/containerization/images/npm/` | `online` or `indexed` packument flow through the adapter |
| `maven` | Java resolver jar | `resolving/containerization/images/maven/` | shared `.m2` cache contract |
| `cargo` | native Rust binary | `resolving/containerization/images/cargo/` | `indexed` local-registry or `online` crates.io network flow over one shared Cargo data root |
| `go` | native Go binary | `resolving/containerization/images/go/` | `online` or `indexed` module metadata flow |

## How These Images Are Used

- The image directories own backend build logic.
- The Compose services in [`resolving/containerization/docker-compose.yml`](../docker-compose.yml) wrap these images with adapters from [`resolving/containerization/runtime/`](../runtime/).
- The user-facing entrypoint remains `python3 main.py`.

## Ecosystem READMEs

- [`resolving/containerization/images/pip/README.md`](pip/README.md)
- [`resolving/containerization/images/npm/README.md`](npm/README.md)
- [`resolving/containerization/images/maven/README.md`](maven/README.md)
- [`resolving/containerization/images/cargo/README.md`](cargo/README.md)
- [`resolving/containerization/images/go/README.md`](go/README.md)
