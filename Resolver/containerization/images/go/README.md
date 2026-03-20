# Go Resolver Image

This directory contains the native Go backend image for Go module dependency resolution.
The image build compiles a standalone `go-resolver` binary and installs it as the image entrypoint.

## Directory structure

Key files and directories:

- `Resolver/containerization/images/go/Dockerfile` — image definition
- `Resolver/containerization/images/go/go.mod` — Go module definition
- `Resolver/containerization/images/go/cmd/go_resolver/` — CLI entrypoint source
- `Resolver/containerization/images/go/internal/resolver/` — graph resolution logic
- `Resolver/containerization/images/go/internal/source/` — module source and proxy fetch logic
- `Resolver/containerization/images/go/internal/output/` — graph and list output formatting
- `Resolver/containerization/images/go/internal/parser/` — parser helpers
- `Resolver/containerization/images/go/internal/model/` — shared data structures
- `Resolver/containerization/images/go/mvs/` — module version selection helpers

## Build the image

Run from the repository root:

```bash
docker build -f Resolver/containerization/images/go/Dockerfile -t go-resolver:latest .
```

## Run the image

The image entrypoint is `/usr/local/bin/go-resolver`.
It supports both `resolve` and `list`.

Example `resolve` run:

```bash
docker run --rm go-resolver:latest resolve github.com/rogpeppe/godef v1.1.2 --format graph
```

Example `list` run:

```bash
docker run --rm go-resolver:latest list github.com/rogpeppe/godef v1.1.2
```

## Notes

- The backend fetches module metadata from the configured Go proxy.
- No dedicated persistent Docker volume is currently required for the Go image.
