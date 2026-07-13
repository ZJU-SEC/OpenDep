---
layout: default
title: Artifact Details
description: Reproducibility checklist, troubleshooting notes, citation, license, and artifact links.
permalink: /artifact-details/
---

This page summarizes how to reproduce the artifact demonstration, troubleshoot common issues, cite the work, and build upon the OpenDep codebase.

## Reproducibility Checklist

Use this checklist to validate a local artifact setup:

1. Install Python 3.
2. Install Docker and Docker Compose.
3. Start the Docker daemon.
4. Build resolver images.
5. Run `capabilities` for at least one ecosystem.
6. Run `health` for at least one ecosystem.
7. Run one online `resolve` example.
8. Optionally prepare indexed/cache-backed metadata.
9. Run one indexed/cache-backed `resolve` example.
10. Inspect the normalized JSON response.

## Basic Verification Commands

Build resolver images:

```bash
docker compose -f resolving/containerization/docker-compose.yml build
```

Check capabilities:

```bash
python3 main.py capabilities --ecosystem pip
python3 main.py capabilities --ecosystem npm
python3 main.py capabilities --ecosystem go
python3 main.py capabilities --ecosystem cargo
python3 main.py capabilities --ecosystem maven
```

Check health:

```bash
python3 main.py health --ecosystem pip
python3 main.py health --ecosystem npm
python3 main.py health --ecosystem go
python3 main.py health --ecosystem cargo
python3 main.py health --ecosystem maven
```

## Expected Response Properties

A successful resolver run should return:

- `"status": "ok"`
- the requested `ecosystem`
- resolver metadata under `resolver`
- dependency graph data under `result`
- diagnostic details under `diagnostics`
- timing information under `timing`

For graph resolution, `result` should include graph-oriented data such as:

- `root`
- `nodes`
- `edges`
- `metrics`

## Common Troubleshooting

| Symptom | Suggested check |
| --- | --- |
| `docker compose` is not found | Install Docker Compose v2 or update Docker Desktop |
| Docker build fails immediately | Check that Docker daemon is running |
| Online mode cannot fetch metadata | Check network access from Docker containers |
| pip/npm/Go indexed mode cannot connect to PostgreSQL | Start the shared PostgreSQL container and verify `INDEX_DSN` |
| Container cannot reach host PostgreSQL | Use `host.docker.internal` in the PostgreSQL DSN |
| Maven resolve misses artifacts | Run the Maven cache warm-up command first |
| Cargo indexed mode fails | Run Cargo `clone` and `prepare-local-registry` first |
| Output status is not `ok` | Re-run with `--return-raw` where supported and inspect diagnostics |

## Notes on Reproducibility

Online mode is convenient for quick demonstrations, but it may depend on the current state of upstream package registries. Indexed or cache-backed mode is more appropriate for reproducible and large-scale analysis because the metadata source is prepared explicitly before resolution.

For paper artifact evaluation, we recommend:

- Use online mode for quick smoke tests.
- Use indexed/cache-backed mode for reproducibility-oriented demonstrations.
- Record the code version, Docker image build date, and metadata preprocessing date.
- Preserve the generated JSON output for each command used in the evaluation.

## Building Upon OpenDep

OpenDep is intended to be reusable for future dependency-analysis studies.

Common extension tasks include:

- Adding a new ecosystem resolver.
- Adding a new resolver mode for an existing ecosystem.
- Improving backend response normalization.
- Adding new graph output fields.
- Connecting OpenDep output to downstream supply-chain analysis tools.
- Running large-scale batch resolution over prepared package inventories.

Developers extending OpenDep should keep the shared response contract stable whenever possible so that downstream analysis scripts can continue to consume the output.

## Citation

Please cite the paper if you use OpenDep or the released dataset:

```bibtex
@article{opendep,
  title = {Untangling Intricate Dependencies: Characterizing and Resolving Software Package Dependencies},
  author = {Wang, Xingyu and Shen, Wenbo and Chang, Rui and Liu, Chengwei and Liu, Yang},
  journal = {TODO_BIBTEX_VENUE},
  year = {TODO_YEAR}
}
```

## License

OpenDep is released under the Apache License 2.0.