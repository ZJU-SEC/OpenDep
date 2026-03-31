# Go resolving Image

This directory contains the native Go backend image for Go module dependency resolution.
The image build compiles a standalone `go-resolver` binary and installs it as the image entrypoint.
The backend supports both `online` and `indexed` metadata modes.

## Directory structure

Key files and directories:

- `resolving/containerization/images/go/Dockerfile` — image definition
- `resolving/containerization/images/go/go.mod` — Go module definition
- `resolving/containerization/images/go/cmd/go_resolver/` — CLI entrypoint source
- `resolving/containerization/images/go/internal/resolver/` — graph resolution logic
- `resolving/containerization/images/go/internal/source/` — module source and proxy fetch logic
- `resolving/containerization/images/go/internal/output/` — graph and list output formatting
- `resolving/containerization/images/go/internal/parser/` — parser helpers
- `resolving/containerization/images/go/internal/model/` — shared data structures
- `resolving/containerization/images/go/mvs/` — module version selection helpers

## Build the image

Run from the repository root:

```bash
docker build -f resolving/containerization/images/go/Dockerfile -t go-resolver:latest .
```

## Metadata Modes

- `online`
  - default mode
  - fetches raw `.mod` files from the configured Go proxy
- `indexed`
  - reads stored `raw_mod` payloads from PostgreSQL table `go_metadata`
  - falls back to `online` mode by default when indexed rows are missing

## Run the image

The image entrypoint is `/usr/local/bin/go-resolver`.
It supports both `resolve` and `list`.

Example `resolve` run in `online` mode:

```bash
docker run --rm \
  -e GO_METADATA_MODE=online \
  -e GO_PROXY_BASE_URL=https://proxy.golang.org \
  go-resolver:latest resolve github.com/rogpeppe/godef v1.1.2 --format graph
```

Example `list` run:

```bash
docker run --rm go-resolver:latest list github.com/rogpeppe/godef v1.1.2
```

Example `resolve` run in `indexed` mode:

```bash
docker run --rm \
  -e GO_METADATA_MODE=indexed \
  -e GO_INDEX_DSN='postgresql://opendep:opendep@host.docker.internal:55432/opendep_preprocess' \
  -e GO_INDEX_TABLE='go_metadata' \
  go-resolver:latest resolve github.com/rogpeppe/godef v1.1.2 --format graph
```

## Notes

- The backend can read metadata either from the configured Go proxy or from PostgreSQL.
- Indexed mode falls back to the Go proxy by default when a row is missing.
- No dedicated persistent Docker volume is currently required for the Go image.
