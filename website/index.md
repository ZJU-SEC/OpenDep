---
layout: default
title: OpenDep
description: A policy-aware dependency resolution framework for ecosystem-scale software dependency analysis.
hero: true
hero_title: OpenDep
hero_subtitle: A policy-aware dependency resolution framework for ecosystem-scale software dependency analysis.
permalink: /
---

## Project Summary

OpenDep is a Docker-based, multi-ecosystem dependency resolution framework for generating dependency graphs consistently with ecosystem-specific resolution policies. It is designed for reproducible software supply-chain research and large-scale dependency analysis rather than ordinary project-level package installation.

This website provides a concise project overview, installation instructions, runnable examples, indexed-mode preprocessing workflows, architecture notes, and extension guidance for readers who want to reproduce or build upon the work.

## Paper

**Untangling Intricate Dependencies: Characterizing and Resolving Software Package Dependencies**

Modern software development relies heavily on package reuse, but dependency analysis is difficult because different package managers use different declaration syntax, version-selection policies, conflict-resolution strategies, and metadata models. OpenDep addresses this problem by providing a policy-aware framework for dependency graph generation across multiple package ecosystems.

The paper makes three main contributions:

- A systematic characterization of dependency declaration and resolution policies across ten mainstream package managers.
- OpenDep, an accurate and scalable dependency resolution framework for ecosystem-level analysis.
- A public dependency dataset containing over 56 million package versions and over 4 billion dependency relationships.

## Artifact Scope

The released code artifact provides a unified command-line interface through:

```bash
python3 main.py
```

The current artifact supports five ecosystems:

| Ecosystem | Main modes | Output formats | Indexed or cache contract |
| --- | --- | --- | --- |
| pip | `online`, `indexed` | `graph` | PostgreSQL table `pip_metadata` |
| npm | `online`, `indexed` | `graph` | PostgreSQL table `npm_metadata` |
| Go | `online`, `indexed` | `graph`, `full` | PostgreSQL table `go_metadata` |
| Cargo | `online`, `indexed` | `graph`, `full` | shared Docker volume `resolver-cargo-cache` |
| Maven | shared-cache mode | `graph` | shared Docker volume `resolver-maven-m2-cache` |

The paper characterizes a broader design space across ten package managers, while the released resolver implementation focuses on the five ecosystems above.

## Why OpenDep

Existing dependency datasets and analysis tools often rely on approximate or opaque resolution pipelines. Official package managers are accurate references, but they are optimized for installing dependencies for individual projects, not for high-throughput ecosystem-level analysis.

OpenDep provides:

- A unified resolver interface across multiple ecosystems.
- A normalized JSON response format for dependency graph analysis.
- Docker-based resolver backends for reproducible local execution.
- Online and indexed/cache-based workflows depending on ecosystem support.
- A preprocessing pipeline for preparing local metadata stores or shared caches.

## Quick Example

Build the resolver images:

```bash
docker compose -f resolving/containerization/docker-compose.yml build
```

Check that a resolver is reachable:

```bash
python3 main.py capabilities --ecosystem pip
python3 main.py health --ecosystem pip
```

Resolve a pip package in online mode:

```bash
python3 main.py resolve \
  --ecosystem pip \
  --name requests \
  --version 2.32.5 \
  --format graph \
  --pip-mode online
```

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

## Links

- Code repository: [TODO_CODE_REPOSITORY_URL]({{ site.repository_url }})
- DOI: [https://doi.org/10.5281/zenodo.14214124]({{ site.doi_url }})
- License: Apache License 2.0