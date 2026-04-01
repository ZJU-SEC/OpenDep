# Shared Pre-process Modules

This directory contains cross-ecosystem helpers used by preprocess and database-loading jobs.

## Quick start

Start the shared preprocessing PostgreSQL container from the repository root:

```bash
docker compose \
  --env-file pre-process/common/database/.env.example \
  -f pre-process/common/database/docker-compose.yml \
  up -d
```

If you want custom local settings, copy `pre-process/common/database/.env.example` to `pre-process/common/database/.env`, edit the values, and replace the `--env-file` path.