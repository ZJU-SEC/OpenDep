# Maven Pre-process Workspace

`pre-process/maven/` has one job:

- warm Maven `pom` files and required `maven-metadata.xml` into `.m2/repository`
- let the Maven resolver under `resolving/` reuse the same cache
- provide `index-all` as the main command for package-list or inventory indexing

This README only keeps the practical usage flow.
Assume all commands are run from the repository root.

## Shared Cache Contract

- Maven preprocess repository path: `/root/.m2/repository`
- Maven resolver repository path: `/root/.m2/repository`
- Shared Docker volume: `resolver-maven-m2-cache`

Recommended workflow:

1. Run Maven preprocess first and write target POM files into the shared `.m2`
2. Run Maven resolver afterwards and reuse the same `.m2`

## Recommended Workflow

Use the resolver compose file directly, because it already includes:

- `preprocess-maven`
- `resolver-maven`

### 1. Build Images

```bash
docker compose -f resolving/containerization/docker-compose.yml build preprocess-maven resolver-maven
```

### 2. Run Package-List Indexing

For Maven package-list indexing, use one package name per line in `groupId:artifactId` form.

Example file:

[`package-list.txt`](/Users/xingyu/project/Paper/OpenDep/pre-process/maven/examples/package-list.txt)

```text
adarwin:adarwin
org.apache.logging.log4j:log4j-core
junit:junit
```

Recommended command:

```bash
docker compose -f resolving/containerization/docker-compose.yml run --rm \
  preprocess-maven index-all \
  --package-file /workspace/pre-process/maven/examples/package-list.txt \
  --sync-mode incremental \
  --state-file /workspace/tmp/maven-index.state.jsonl \
  --failure-log /workspace/tmp/maven-index.failures.jsonl \
  --pretty
```

Notes:

- `--package-file` reads one Maven package name (`groupId:artifactId`) per line
- the planner fetches each package's remote `maven-metadata.xml` and expands all published versions
- `--sync-mode incremental` is the recommended default
- `--state-file` enables resume support and avoids reprocessing versions already marked completed
- `--failure-log` stores structured failures
- package-list expansion is fault-tolerant per package; if one package metadata lookup fails, the other packages still continue unless you add `--fail-fast`

You can also provide packages directly on the command line:

```bash
docker compose -f resolving/containerization/docker-compose.yml run --rm \
  preprocess-maven index-all \
  --package junit:junit \
  --package org.apache.logging.log4j:log4j-core \
  --sync-mode incremental \
  --state-file /workspace/tmp/maven-index.state.jsonl \
  --pretty
```

### 3. Run the Resolver Against the Same `.m2`

```bash
docker compose -f resolving/containerization/docker-compose.yml run --rm \
  --entrypoint /usr/local/bin/maven-resolver \
  resolver-maven \
  org.apache.logging.log4j:log4j-core:2.23.1
```

## Common Commands

### Incremental Indexing From a Package List

```bash
docker compose -f resolving/containerization/docker-compose.yml run --rm \
  preprocess-maven index-all \
  --package-file /workspace/pre-process/maven/examples/package-list.txt \
  --sync-mode incremental \
  --state-file /workspace/tmp/maven-index.state.jsonl \
  --failure-log /workspace/tmp/maven-index.failures.jsonl \
  --pretty
```

### Full Rescan From a Package List

```bash
docker compose -f resolving/containerization/docker-compose.yml run --rm \
  preprocess-maven index-all \
  --package-file /workspace/pre-process/maven/examples/package-list.txt \
  --sync-mode full \
  --pretty
```

### Repair Missing or Invalid Local Cache Entries

```bash
docker compose -f resolving/containerization/docker-compose.yml run --rm \
  preprocess-maven index-all \
  --package-file /workspace/pre-process/maven/examples/package-list.txt \
  --sync-mode repair-missing \
  --state-file /workspace/tmp/maven-index.state.jsonl \
  --failure-log /workspace/tmp/maven-index.failures.jsonl \
  --pretty
```

### Inventory-Based Indexing

If you already have a coordinate inventory in `groupId:artifactId:version` form, `--inventory` still works:

```bash
docker compose -f resolving/containerization/docker-compose.yml run --rm \
  preprocess-maven index-all \
  --inventory /workspace/path/to/maven-inventory.txt \
  --sync-mode repair-missing \
  --state-file /workspace/tmp/maven-index.state.jsonl \
  --failure-log /workspace/tmp/maven-index.failures.jsonl \
  --pretty
```

### Warm One Coordinate

```bash
docker compose -f resolving/containerization/docker-compose.yml run --rm \
  preprocess-maven warm \
  junit:junit:4.13.2 \
  --pretty
```

### Warm From a Coordinate File

```bash
docker compose -f resolving/containerization/docker-compose.yml run --rm \
  preprocess-maven warm \
  --coordinate-file /workspace/path/to/coordinates.txt \
  --state-file /workspace/tmp/maven-warm.state.jsonl \
  --failure-log /workspace/tmp/maven-warm.failures.jsonl \
  --pretty
```

## `sync-mode`

- `incremental`
  - Recommended default mode
  - Processes newly discovered coordinates and also repairs missing or invalid local `.m2` entries
- `new-only`
  - Focuses only on coordinates not yet completed in `state-file`
- `repair-missing`
  - Repairs only missing or invalid local POM / metadata entries
- `full`
  - Ignores incremental filtering and replans the full inventory

## Standalone Preprocess Compose

You can also run Maven preprocess by itself with `pre-process/maven/docker-compose.yml`.

### Build

```bash
docker compose -f pre-process/maven/docker-compose.yml build maven-preprocess
```

### Run

```bash
docker compose -f pre-process/maven/docker-compose.yml run --rm \
  maven-preprocess index-all \
  --package-file /workspace/pre-process/maven/examples/package-list.txt \
  --sync-mode incremental \
  --state-file /workspace/tmp/maven-index.state.jsonl \
  --failure-log /workspace/tmp/maven-index.failures.jsonl \
  --pretty
```

This standalone compose file still reuses the same volume:

- `resolver-maven-m2-cache`

That means the resolver can still consume the warmed cache afterwards.

## Notes

- Use `/workspace/...` paths for files passed into the container
- The package file or inventory file must be visible inside the container
- The default local repository root is `/root/.m2/repository`
- `SNAPSHOT` is not fully offline-warmed in the current phase and will return `partial`
- `state-file` and `failure-log` should usually be written under mounted paths such as `/workspace/tmp/...`
- For package-list indexing, `state-file` is usually enough for incremental updates; you do not need a separate database just to track completed versions in the current local workflow

## Related Files

- [`docker-compose.yml`](/Users/xingyu/project/Paper/OpenDep/pre-process/maven/docker-compose.yml)
- [`Dockerfile`](/Users/xingyu/project/Paper/OpenDep/pre-process/maven/Dockerfile)
- [`tasks.md`](/Users/xingyu/project/Paper/OpenDep/pre-process/maven/tasks.md)
- [`M2-CONTRACT.md`](/Users/xingyu/project/Paper/OpenDep/pre-process/maven/M2-CONTRACT.md)
