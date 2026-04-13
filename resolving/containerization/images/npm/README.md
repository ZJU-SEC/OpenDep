# npm Resolver Image

`resolving/containerization/images/npm/` packages the native npm backend used by `resolver-npm`.

## What It Does

The npm resolver image:

- compiles the native C++ resolver binary with CMake
- exposes the raw backend CLI for direct image runs
- serves `online` and `indexed` resolver workflows through the adapter-backed Compose service

## Use Through the Resolver CLI

Examples:

```bash
docker compose -f resolving/containerization/docker-compose.yml build resolver-npm
python3 main.py health --ecosystem npm
python3 main.py capabilities --ecosystem npm

python3 main.py resolve --ecosystem npm --name left-pad --version 1.3.0 --format graph --npm-mode online
python3 main.py resolve --ecosystem npm --name left-pad --version 1.3.0 --format graph --npm-mode indexed --npm-index-dsn 'postgresql://opendep:opendep@host.docker.internal:55432/opendep_preprocess' --npm-index-table npm_metadata
```

If you want indexed mode, populate `npm_metadata` first through [`pre-process/npm/README.md`](../../../../pre-process/npm/README.md).