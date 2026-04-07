# Shared Pre-process Database

This directory contains the shared PostgreSQL setup used by preprocess jobs. It provides the database service, SQL migrations, and a Python migration runner.

This README only covers PostgreSQL-backed preprocess paths. In the current stack, Maven and Cargo use shared filesystem contracts instead of shared preprocess tables.

The intended deployment model is:

- all PostgreSQL-backed ecosystems share one PostgreSQL instance
- each PostgreSQL-backed ecosystem writes to its own table
- `pre-process/` is responsible for preparing and loading data
- `resolving/` reads the indexed data from the configured ecosystem table

## Current table plan

- `pip` -> `pip_metadata`
- `npm` -> `npm_metadata`, `npm_sync_state`, `npm_tombstones`
- `maven` -> no shared PostgreSQL table in the current stack; uses shared `.m2` cache volume `resolver-maven-m2-cache`
- `cargo` -> no shared PostgreSQL table in the current stack; uses a managed `crates.io-index` clone to prepare `local-registry` for indexed resolution
- `go` -> `go_metadata`

## Files

- `docker-compose.yml` - shared PostgreSQL container definition
- `.env.example` - example environment variables for local startup
- `Dockerfile.migrations` - migration-runner image definition
- `requirements-migrations.txt` - Python dependencies for the migration runner
- `docker-entrypoint-migrations.sh` - CLI entrypoint for yoyo commands
- `yoyo.ini` - yoyo configuration pointing at the shared migration directory
- `initdb/00-pip-metadata.sql` - pip migration file
- `initdb/10-go-metadata.sql` - Go migration file
- `initdb/20-npm-metadata.sql` - npm migration file
- `initdb/21-npm-sync-state.sql` - npm `_changes` checkpoint migration file
- `initdb/22-npm-tombstones.sql` - npm delete-tombstone migration file

## Start the database

From the repository root:

```bash
docker compose \
  --env-file pre-process/common/database/.env.example \
  -f pre-process/common/database/docker-compose.yml \
  up -d
```

This starts:

- `preprocess-db` - the shared PostgreSQL service
- `preprocess-db-migrate` - a one-shot Python migration runner based on `yoyo-migrations`

The migration runner reads SQL files from
`pre-process/common/database/initdb/` and records applied migrations in yoyo's
tracking tables. On later startups it only applies files that have not yet
been recorded.

If you want a local editable env file:

```bash
cp pre-process/common/database/.env.example pre-process/common/database/.env
docker compose \
  --env-file pre-process/common/database/.env \
  -f pre-process/common/database/docker-compose.yml \
  up -d
```

To stop the container:

```bash
docker compose \
  --env-file pre-process/common/database/.env.example \
  -f pre-process/common/database/docker-compose.yml \
  down
```

## Default connection settings

Default local settings in the example config are:

- host: `127.0.0.1`
- port: `55432`
- database: `opendep_preprocess`
- user: `opendep`
- password: `opendep`

Example DSN:

```text
postgresql://opendep:opendep@127.0.0.1:55432/opendep_preprocess
```

If you access this PostgreSQL instance from another Docker container that is not
in the same Compose project, do not use `127.0.0.1` as the hostname. Use the
host-published port instead, for example:

```text
postgresql://opendep:opendep@host.docker.internal:55432/opendep_preprocess
```

## pip integration

The pip preprocessing and indexed resolver paths should target:

- database: `opendep_preprocess`
- table: `pip_metadata`
- schema file: `pre-process/common/database/initdb/00-pip-metadata.sql`

For the pip resolver, the matching environment variables are:

```text
PIP_INDEX_DSN=postgresql://opendep:opendep@127.0.0.1:55432/opendep_preprocess
PIP_INDEX_TABLE=pip_metadata
```

## go integration

The Go preprocessing and indexed resolver paths target:

- database: `opendep_preprocess`
- table: `go_metadata`
- schema file: `pre-process/common/database/initdb/10-go-metadata.sql`

## npm integration

The npm preprocessing and indexed resolver paths target:

- database: `opendep_preprocess`
- table: `npm_metadata`
- schema file: `pre-process/common/database/initdb/20-npm-metadata.sql`
- checkpoint table: `npm_sync_state`
- checkpoint schema file: `pre-process/common/database/initdb/21-npm-sync-state.sql`
- tombstone table: `npm_tombstones`
- tombstone schema file: `pre-process/common/database/initdb/22-npm-tombstones.sql`