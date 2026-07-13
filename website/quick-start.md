---
layout: default
title: Quick Start
description: Build OpenDep resolver images, check resolver health, and run a minimal dependency-resolution example.
permalink: /quick-start/
---

This page gives the shortest path to run OpenDep locally. The commands assume that the user is in the root directory of the code artifact.

## Prerequisites

Before running OpenDep, make sure the host machine has:

- Python 3 available as `python3`
- Docker installed
- Docker daemon running
- Docker Compose available through `docker compose`
- Internet access for image builds and online resolver runs

## 1. Build Resolver Images

From the artifact root:

```bash
docker compose -f resolving/containerization/docker-compose.yml build
```

This builds the containerized resolver services used by the unified OpenDep CLI.

## 2. Check Resolver Availability

Check supported features:

```bash
python3 main.py capabilities --ecosystem pip
```

Check runtime health:

```bash
python3 main.py health --ecosystem pip
```

If the commands return a JSON response with `"status": "ok"`, the resolver path is working.

## 3. Run a Minimal Online Example

The simplest way to run OpenDep is online mode, which queries upstream package metadata during resolution.

```bash
python3 main.py resolve \
  --ecosystem pip \
  --name requests \
  --version 2.32.5 \
  --format graph \
  --pip-mode online
```

The response is a normalized JSON object. A successful response has this general structure:

```json
{
  "schema_version": "1.0",
  "status": "ok",
  "ecosystem": "pip",
  "result": {
    "root": {},
    "nodes": [],
    "edges": [],
    "metrics": {}
  },
  "diagnostics": [],
  "timing": {}
}
```

## Minimal Examples for All Supported Ecosystems

### pip

```bash
python3 main.py resolve \
  --ecosystem pip \
  --name requests \
  --version 2.32.5 \
  --format graph \
  --pip-mode online
```

### npm

```bash
python3 main.py resolve \
  --ecosystem npm \
  --name mocha \
  --version 10.0.0 \
  --format graph \
  --npm-mode online
```

### Go

```bash
python3 main.py resolve \
  --ecosystem go \
  --name github.com/rogpeppe/godef \
  --version v1.1.2 \
  --format graph \
  --go-mode online
```

### Cargo

```bash
python3 main.py resolve \
  --ecosystem cargo \
  --name rand \
  --version 0.8.5 \
  --format graph \
  --cargo-mode online
```

### Maven

```bash
python3 main.py resolve \
  --ecosystem maven \
  --name org.apache.logging.log4j:log4j-core \
  --version 2.23.1 \
  --format graph
```

Maven does not expose an `online` or `indexed` command-line switch in the current artifact. It resolves through the shared Maven cache contract used by the resolver container.

## Useful Help Commands

```bash
python3 main.py --help
python3 main.py resolve --help
python3 main.py health --help
python3 main.py capabilities --help
python3 main.py list --help
```

## Next Step

For reproducible and large-scale workflows, see the Preprocessing and Indexed Mode page.
