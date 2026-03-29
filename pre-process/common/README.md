# Shared Pre-process Modules

This directory is reserved for cross-ecosystem helpers used by preprocessing and database-loading jobs.

## Quick start

Start the shared preprocessing PostgreSQL container from the repository root:

```bash
docker compose \
  --env-file pre-process/common/database/.env.example \
  -f pre-process/common/database/docker-compose.yml \
  up -d
```

If you want custom local settings, copy `pre-process/common/database/.env.example` to
`pre-process/common/database/.env`, edit the values, and replace the `--env-file` path.

The shared DB stack also includes a one-shot Python migration service that applies new SQL migrations from `pre-process/common/database/initdb/` into the shared PostgreSQL database.

## Subdirectories

- `database/`: shared PostgreSQL container config, SQL migration files, Python migration-runner config, connection management, transaction helpers, batch writers, SQL helpers
- `models/`: normalized record definitions and shared internal contracts
- `utils/`: logging, retry, serialization, path, and small helper utilities
