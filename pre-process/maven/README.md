# Maven Pre-process Workspace

`pre-process/maven/` warms Maven `pom` files and required `maven-metadata.xml` into the shared `.m2/repository` so the Maven resolver under `resolving/` can reuse the same cache.

## What It Does

The Maven preprocess workspace currently:

- warms Maven `pom` files into the shared `.m2` repository
- fetches and stores required `maven-metadata.xml`

Maven preprocess does not write to a shared preprocess PostgreSQL table. Its handoff to the resolver is the shared Docker volume `resolver-maven-m2-cache`.

## Shared `.m2` Handoff

Maven preprocess and the Maven resolver both use the same repository root:

- preprocess repository root: `/root/.m2/repository`
- resolver repository root: `/root/.m2/repository`
- shared Docker volume: `resolver-maven-m2-cache`

## Workflow

Use the preprocess compose file for indexing and warm-up:

- `pre-process/maven/docker-compose.yml`

Use the resolver entrypoints separately when you want to consume the warmed
cache:

- `python3 main.py ...`
- `resolving/containerization/docker-compose.yml`

### 1. Build Images

```bash
docker compose -f pre-process/maven/docker-compose.yml build maven-preprocess
```

### 2. Run Package-List Indexing

For Maven package-list indexing, use one package name per line in `groupId:artifactId` form. Example file: [`package-list.txt`](examples/package-list.txt)

Recommended command:

```bash
docker compose -f pre-process/maven/docker-compose.yml run --rm \
  maven-preprocess index-all \
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
docker compose -f pre-process/maven/docker-compose.yml run --rm \
  maven-preprocess index-all \
  --package junit:junit \
  --package org.apache.logging.log4j:log4j-core \
  --sync-mode incremental \
  --state-file /workspace/tmp/maven-index.state.jsonl \
  --pretty
```

### 3. Run the Resolver Against the Same `.m2`

The preprocess compose file and the resolver stack share the same Docker
volume name:

- `resolver-maven-m2-cache`

So after indexing or warming through `pre-process/maven/`, the resolver can
consume the same `.m2` data immediately.

Build the resolver image if needed:

```bash
docker compose -f resolving/containerization/docker-compose.yml build resolver-maven
```

Run the user-facing resolver path:

```bash
python3 main.py resolve --ecosystem maven --name org.apache.logging.log4j:log4j-core --version 2.23.1 --format graph
```



### 4. `sync-mode`

- `incremental`: recommended default; processes newly discovered coordinates
  and repairs missing or invalid local `.m2` entries
- `new-only`: only processes coordinates not yet completed in `state-file`
- `repair-missing`: repairs only missing or invalid local POM or metadata
  entries
- `full`: ignores incremental filtering and replans the full inventory
