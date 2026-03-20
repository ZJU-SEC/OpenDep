# pip Resolver Image

This directory contains the Python backend image for pip dependency resolution.
Unlike the native binary or jar based backends used by some other ecosystems, the pip image packages a Python backend module plus the container runtime adapter and exposes the adapter as the image default command.

## Directory structure

Key files and directories:

- `Resolver/containerization/images/pip/Dockerfile` — image definition
- `Resolver/containerization/images/pip/backend/` — Python backend source tree
- `Resolver/containerization/images/pip/backend/cli.py` — backend CLI entrypoint
- `Resolver/containerization/images/pip/backend/resolver_core/` — dependency solving core built on `resolvelib`
- `Resolver/containerization/images/pip/backend/metadata_sources/` — `live` and `indexed` metadata source implementations
- `Resolver/containerization/images/pip/backend/inspectors/` — wheel and sdist dependency extraction logic
- `Resolver/containerization/images/pip/backend/stores/` — indexed-store abstractions and PostgreSQL implementation
- `Resolver/containerization/images/pip/backend/indexer/` — offline metadata indexing flow
- `Resolver/containerization/images/pip/examples/` — example adapter request payloads
- `Resolver/containerization/images/pip/tests/` — Python-side regression tests
- `Resolver/containerization/images/pip/pip-refactoring.md` — refactoring design record
- `Resolver/containerization/images/pip/pip-tasks.md` — task tracking record
- `Resolver/containerization/images/pip/arch.md` — architecture notes and migration context

## Build the image

Run from the repository root:

```bash
docker build -f Resolver/containerization/images/pip/Dockerfile -t pip-resolver:latest .
```

## Run the image

The image default command is `python3 Resolver/containerization/runtime/pip_adapter.py`.
It expects a normalized JSON request on standard input, following the shared container adapter contract.

Example `health` run:

```bash
printf '%s\n' '{"schema_version":"1.0","request_id":"health-1","trace_id":"trace-1","command":"health","ecosystem":"pip"}' \
  | docker run --rm -i pip-resolver:latest
```

Example `resolve` run in `live` mode:

```bash
printf '%s\n' "$(cat Resolver/containerization/images/pip/examples/resolve-live-request.json)" \
  | docker run --rm -i -e PIP_METADATA_MODE=live pip-resolver:latest
```

Example `resolve` run in `indexed` mode:

```bash
printf '%s\n' "$(cat Resolver/containerization/images/pip/examples/resolve-indexed-request.json)" \
  | docker run --rm -i -e PIP_METADATA_MODE=indexed -e PIP_INDEX_DSN='postgresql://user:password@host:5432/opendep_pip' pip-resolver:latest
```

If you want to bypass the adapter and invoke the backend module directly, override the container command:

```bash
docker run --rm pip-resolver:latest python3 -m Resolver.containerization.images.pip.backend describe
```

## Notes

- The backend supports two metadata modes:
  - `live` fetches package metadata and artifacts on demand without requiring a database.
  - `indexed` reads pre-extracted metadata from the configured indexed store.
- For `resolve`, `package.version` is optional in the protocol; if omitted, the backend currently selects the latest non-yanked stable release it can see from the metadata source.
- The backend CLI currently supports `health`, `describe`, `resolve`, and `index`.
- The image is focused on dependency resolution only; it does not include path conflict detection, module path simulation, `InstSimulator`, or `detect_MC.py` migration.
- In the compose setup, `live` mode typically uses the mounted cache directory `/resolver-pip-cache`.
- The current indexed-store implementation is PostgreSQL-backed through `PostgresIndexStore`.
- Python-side regression tests can be run with `python3 -m unittest discover -s Resolver/containerization/images/pip/tests`.
