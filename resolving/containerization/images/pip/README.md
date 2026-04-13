# pip Resolver Image

`resolving/containerization/images/pip/` packages the pip resolver backend used by `resolver-pip`.

## What It Does

The pip resolver image:

- provides a Python backend CLI for direct image runs
- supports `online` and `indexed` metadata modes
- serves normalized `resolve`, `health`, and `capabilities` responses through the adapter-backed service

## Use Through the Resolver CLI

If you want indexed mode, populate `pip_metadata` first through [`pre-process/pip/README.md`](../../../../pre-process/pip/README.md).

Examples:

```bash
docker compose -f resolving/containerization/docker-compose.yml build resolver-pip
python3 main.py health --ecosystem pip
python3 main.py capabilities --ecosystem pip

python3 main.py resolve --ecosystem pip --name requests --version 2.32.5 --format graph --pip-mode online
python3 main.py resolve --ecosystem pip --name requests --version 2.32.5 --format graph --pip-mode indexed --pip-index-dsn 'postgresql://opendep:opendep@host.docker.internal:55432/opendep_preprocess' --pip-index-table pip_metadata
```