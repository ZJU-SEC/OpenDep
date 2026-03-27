# Shared Pre-process Database

This directory contains the shared PostgreSQL container setup used by preprocessing jobs.

The intended deployment model is:

- all ecosystems share one PostgreSQL database instance
- each ecosystem writes to its own table
- `pre-process/` is responsible for preparing and loading data
- `resolving/` reads the indexed data from the configured ecosystem table

## Current table plan

- `pip` -> `pip_projects_metadata`
- `npm` -> reserved for future table
- `maven` -> reserved for future table
- `cargo` -> reserved for future table
- `go` -> reserved for future table

Only the `pip` table is initialized right now.

## Files

- `docker-compose.yml` - shared PostgreSQL container definition
- `.env.example` - example environment variables for local startup
- `initdb/00-pip-projects-metadata.sql` - pip table initialization script

## Start the database

From the repository root:

```bash
docker compose \
  --env-file pre-process/common/database/.env.example \
  -f pre-process/common/database/docker-compose.yml \
  up -d
```

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
- table: `pip_projects_metadata`

For the pip resolver, the matching environment variables are:

```text
PIP_INDEX_DSN=postgresql://opendep:opendep@127.0.0.1:55432/opendep_preprocess
PIP_INDEX_TABLE=pip_projects_metadata
```

## Notes

- The initialization scripts in `initdb/` only run automatically on first container startup with an empty data volume.
- If you need to re-run schema initialization from scratch, remove the database volume first or apply the SQL manually with `psql`.
- Additional ecosystem tables should be added as new SQL files in `initdb/`, instead of creating separate PostgreSQL containers.
