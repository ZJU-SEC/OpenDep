# Go Resolver Image

`resolving/containerization/images/go/` packages the native Go backend used by `resolver-go`.

## What It Does

The Go resolver image:

- compiles a standalone `go-resolver` binary
- supports both direct backend runs and the adapter-backed resolver service
- resolves dependency graphs or returns Go build-list style output

## Use Through the Resolver CLI

If you want indexed mode, populate `go_metadata` first through
[`pre-process/go/README.md`](../../../../pre-process/go/README.md).

Examples:

```bash
docker compose -f resolving/containerization/docker-compose.yml build resolver-go
python3 main.py health --ecosystem go
python3 main.py capabilities --ecosystem go

python3 main.py resolve --ecosystem go --name github.com/rogpeppe/godef --version v1.1.2 --format graph --go-mode online
python3 main.py list --ecosystem go --name github.com/rogpeppe/godef --version v1.1.2 --go-mode online

python3 main.py resolve --ecosystem go --name github.com/rogpeppe/godef --version v1.1.2 --go-mode indexed --go-index-dsn 'postgresql://opendep:opendep@host.docker.internal:55432/opendep_preprocess' --go-index-table go_metadata
python3 main.py list --ecosystem go --name github.com/rogpeppe/godef --version v1.1.2 --go-mode indexed --go-index-dsn 'postgresql://opendep:opendep@host.docker.internal:55432/opendep_preprocess' --go-index-table go_metadata

```