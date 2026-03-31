# npm Pre-process Refactor Tasks

## Selected Direction

- v1 targets batch ingestion of explicit npm package names into PostgreSQL.
- PostgreSQL is the only persistent store for the new path.
- The authoritative payload is the raw packument fetched from the npm package document endpoint.
- Future indexed resolving should keep the current npm resolver lookup shape:
  - exact lookup by package name
  - return the raw packument payload
  - continue using the existing npm resolver logic for `dist-tags`, semver range selection, deprecation preference, platform filtering, and dependency extraction
- v1 does not create per-version child tables for dependency edges.
- v1 does not recreate the legacy Scrapy plus CouchDB daemon workflow.
- Continuous `_changes` sync is explicitly deferred until after the batch ingestion path is stable.

## Constraints Already Confirmed

- The archived implementation under `pre-process/npm/.legacy/js-dependency-crawler/` is a Python Scrapy crawler, not a C++ crawler.
- The legacy spider consumes the npm CouchDB `_changes` feed, then fetches full package documents and mirrors them into CouchDB.
- The legacy pipeline stores the full remote package document and keeps the remote revision in `replicate.npmjs.com_rev`.
- The legacy implementation uses a file-based `last_seq` checkpoint instead of a database-backed sync state.
- The legacy delete-handling path is incomplete because deleted events are not currently yielded from the spider into the persistence pipeline.
- The active npm resolver in `resolving/containerization/images/npm/` currently fetches the whole packument by package name and performs version selection locally.
- The active npm resolver reads `versions`, `dist-tags`, `deprecated`, `dependencies`, `optionalDependencies`, `peerDependencies`, `peerDependenciesMeta`, `os`, `cpu`, and `libc` from the packument payload.
- Because of that, the indexed storage contract should optimize for exact package-name lookup plus parser and resolver reuse, not for pre-expanded dependency-edge analytics.

## Legacy-to-v1 Data Mapping

| Legacy or online source field | v1 treatment |
| --- | --- |
| package document `_id` | keep as `name` |
| whole package document JSON | keep as `raw_packument` |
| package document `_rev` or `_changes` revision | keep as `source_rev` when available |
| fetch URL | keep as `source_url` |
| `last_seq` checkpoint file | do not store in v1 primary table; reserve for future `npm_sync_state` work |
| local CouchDB `_rev` | drop in v1 |
| `versions` object | do not split into rows in v1 |
| `dist-tags` object | do not split into rows in v1 |
| dependency maps inside version metadata | do not split into child tables in v1 |
| deleted or unpublished events | defer to later sync work |

## Target Runtime Storage Contract

Primary table name:

- `npm_metadata`

Required row contract for v1:

| Column | Type | Notes |
| --- | --- | --- |
| `name` | `text` | registry package key; unique lookup key |
| `raw_packument` | `text` | exact package document payload returned by the source |
| `raw_packument_sha256` | `text` | helps idempotent checks and diagnostics |
| `source_url` | `text` | exact URL used to fetch the package document |
| `source_rev` | `text` | remote revision when available from the payload or sync feed |
| `fetched_at` | `timestamptz` | wall-clock fetch completion time |
| `created_at` | `timestamptz` | row creation time |
| `updated_at` | `timestamptz` | row update time |

Required constraints for v1:

- `UNIQUE (name)`
- no per-version dependency child tables
- no CouchDB or Cloudant dependency
- exact package-name lookup remains the hot-path contract

Non-goals for v1:

- storing one row per `(name, version)`
- materialized dependency-edge tables
- reproducing `_changes` feed daemon behavior in the first preprocess PR
- delete or unpublish handling in the first preprocess PR
- native C++ PostgreSQL integration in the first resolver handoff

## Working Assumptions

- The new `pre-process/npm/` implementation should follow the current preprocess workspace pattern already used elsewhere in this repository:
  - `adapters/`
  - `pipeline/`
  - `loaders/`
- The new entrypoint should be Docker-friendly and align with the existing preprocess workflow style.
- Input units for v1 should be explicit package names, not package versions.
- Scoped packages must use correct registry path escaping.
- The npm registry base URL must be a runtime configuration, not a compile-time-only constant.
- The preprocessing data source and the resolver online data source should eventually point at the same registry base URL.

## Task Breakdown

### Phase 0. Freeze Scope and Contract

- [x] Add a short design note to `pre-process/npm/README.md` after implementation, stating that v1 is batch ingestion of explicit package names.
- [x] Record that v1 stores raw packuments and does not split dependency metadata into child tables.
- [x] Record that v1 does not restore the legacy Scrapy plus CouchDB daemon workflow.
- [x] Record that `_changes` sync is a later phase, not part of the initial preprocess PR.

### Phase 1. Add Shared PostgreSQL Schema

- [x] Add the npm table definition to a dedicated migration file under `pre-process/common/database/initdb/`.
- [x] Use the table name `npm_metadata`.
- [x] Initialize the `npm_metadata` table with the v1 columns listed above.
- [x] Add `UNIQUE (name)`.
- [x] Use loader-managed upsert behavior to refresh `raw_packument`, `raw_packument_sha256`, `source_url`, `source_rev`, `fetched_at`, and `updated_at`.
- [x] Update `pre-process/common/database/README.md` so npm is no longer only "reserved for future table".

### Phase 2. Create the New Preprocess Skeleton

- [x] Add `pre-process/npm/build.py` as the main batch ingestion entrypoint.
- [x] Add `pre-process/npm/adapters/registry_client.py` to fetch raw packuments from the configured npm registry.
- [x] Add `pre-process/npm/pipeline/package_specs.py` to parse and validate package-name inputs.
- [x] Add `pre-process/npm/pipeline/records.py` to define the in-memory row contract for `npm_metadata`.
- [x] Add `pre-process/npm/loaders/postgres_loader.py` with `ensure_schema`, `exists`, and `upsert` support.
- [x] Reuse shared PostgreSQL helpers from `pre-process/common/database/` where practical.

### Phase 3. Implement v1 Ingestion Behavior

- [x] Support explicit single-input ingestion with `--package <name>`.
- [x] Support batch ingestion with `--package-file /path/to/package-list.txt`.
- [x] Support `--dsn`, `--ensure-schema`, `--skip-existing`, `--registry-base-url`, `--concurrency`, and `--pretty`.
- [x] Fetch the package document from the registry path for the requested package and store the payload exactly as returned.
- [x] Implement npm-compatible package-path escaping, including scoped packages.
- [x] Compute `raw_packument_sha256` before each upsert.
- [x] Extract `source_rev` when it is present in the fetched payload.
- [x] Keep the ingest pipeline parse-light:
  - no dependency expansion
  - no version splitting
  - no attempt to mirror resolver graph logic inside preprocess
- [x] Make reruns idempotent for the same package-name input set.

### Phase 4. Containerization and Developer Workflow

- [x] Add `pre-process/npm/Dockerfile`.
- [x] Add `pre-process/npm/docker-compose.yml`.
- [x] Add `pre-process/npm/docker-entrypoint.sh`.
- [x] Add `pre-process/npm/examples/package-list.txt`.
- [x] Use the shared preprocess PostgreSQL container described in `pre-process/common/database/README.md`.
- [x] Keep the user-facing workflow Docker-first, consistent with the rest of `pre-process/`.

### Phase 5. Documentation

- [x] Expand `pre-process/npm/README.md` from the current placeholder into an actual operator guide.
- [x] Document the selected storage model and why npm v1 stores one row per package instead of one row per version.
- [x] Document the expected table name `npm_metadata`.
- [x] Document the recommended Docker command for single-package ingestion.
- [x] Document the recommended Docker command for package-file batch ingestion.
- [x] Document the shared PostgreSQL prerequisites and connection conventions.
- [x] Document the meaning and limitation of `--skip-existing` for package-level rows.

### Phase 6. Tests and Validation

- [x] Add unit tests for package-name parsing and validation.
- [x] Add unit tests for npm registry package-path escaping, especially scoped packages.
- [x] Add unit tests for PostgreSQL upsert behavior.
- [x] Add unit tests for `--skip-existing` behavior.
- [x] Add an integration test using a stub HTTP server plus local PostgreSQL.
- [x] Run a smoke test with a small representative package list and verify that rows can be queried directly by package name.

### Phase 7. Resolver Handoff Follow-up

- [x] Make the npm resolver registry base URL runtime-configurable instead of compile-time-only.
- [x] Add npm indexed-mode configuration on the resolving side.
- [x] Implement a first indexed handoff that serves packuments from PostgreSQL through a local adapter-managed HTTP shim, so the native resolver can keep using its current packument parsing logic.
- [x] Keep the online npm source available as the default path until indexed mode is validated end to end.
- [x] Add fallback behavior so indexed-mode package misses can still be resolved through the online path during rollout.
- [x] Validate that indexed mode reproduces the same input semantics for `dist-tags`, semver range selection, deprecation preference, and dependency extraction.

### Phase 8. Add Database-Backed Sync Checkpointing

- [x] Add a dedicated PostgreSQL migration for a future `npm_sync_state` table.
- [x] Store sync checkpoints in PostgreSQL instead of a mounted local file.
- [x] Use a stable logical key such as `source_key` so multiple registry sources can be tracked independently.
- [x] Store `registry_base_url`, `changes_url`, `last_seq`, `checkpointed_at`, `created_at`, and `updated_at`.
- [x] Store `last_seq` as `text`, not as an integer-only type, so the design remains compatible with non-numeric checkpoint tokens.
- [x] Add loader support to read, initialize, and update sync checkpoints.
- [x] Define transaction semantics so checkpoint advancement only happens after the corresponding packument writes succeed.

### Phase 9. Implement `_changes` Sync-Once Ingestion

- [x] Add a dedicated npm sync entrypoint, for example `pre-process/npm/sync.py`, instead of overloading the batch `build.py` contract.
- [x] Support a single-batch `sync-once` mode that reads from the stored checkpoint, fetches one `_changes` batch, applies it, and exits.
- [x] Support runtime options for `--source-key`, `--changes-url`, `--registry-base-url`, `--since`, `--limit`, and `--pretty`.
- [x] If `--since` is omitted, resume from `npm_sync_state.last_seq`.
- [x] Deduplicate repeated package names within the same `_changes` batch and keep only the last event per package for application.
- [x] For non-delete events, fetch the current raw packument and upsert it into `npm_metadata`.
- [x] Reuse `source_rev` from `_changes` metadata and or the fetched document when available.
- [x] Update `npm_sync_state.last_seq` only after the batch has been persisted successfully.
- [x] Emit structured summary output that reports fetched package count, updated row count, skipped row count, delete-event count, and checkpoint advancement.

### Phase 10. Add Continuous Sync Follow Mode

- [x] Add a long-running `sync-follow` mode that repeatedly executes the `sync-once` batch logic.
- [x] Support runtime options for poll interval, idle backoff, and batch size.
- [x] Add graceful shutdown behavior so interrupts do not leave checkpoint state ahead of committed data.
- [x] Add logging and metrics for processed batches, advanced checkpoints, repeated idle polls, and transient fetch failures.
- [x] Add bounded concurrency for per-batch packument fetches, while keeping checkpoint advancement serialized.
- [x] Add retry behavior for transient registry and database failures without requiring manual checkpoint rollback.
- [x] Document that `sync-follow` is the successor to the legacy always-on crawler flow, but is PostgreSQL-backed and command-oriented.

### Phase 11. Add Delete and Unpublish Semantics

- [x] Add a dedicated PostgreSQL migration for a future `npm_tombstones` table.
- [x] Record package-level delete events separately from the primary `npm_metadata` table.
- [x] Define package-level delete handling so a delete event removes the current `npm_metadata` snapshot row and writes a tombstone record.
- [x] Store tombstone data such as `name`, `source_rev`, `deleted_seq`, `deleted_at`, `created_at`, and `updated_at`.
- [x] Define restore behavior so a later non-delete event for the same package recreates the `npm_metadata` row and clears any active tombstone.
- [x] Treat version-level unpublish as a normal packument replacement, not as a row-level delete in the primary table.
- [x] Add integration tests for package delete, package recreation, and version removal within an otherwise live packument.
- [x] Document the difference between package deletion and version disappearance so future resolver work does not overfit to CouchDB event semantics.

## Acceptance Criteria

- A stored package can later be served by exact package-name lookup without joining dependency tables.
- The stored row contains enough data for the resolver to reconstruct the same packument input it currently receives from the online registry.
- The first implementation is safe to rerun against the same package list and does not require CouchDB.
- The first implementation does not attempt to rebuild npm dependency-tree semantics inside preprocessing.
- The future resolver integration can be added on top of the stored packument contract, without redesigning the table.

## Explicitly Deferred From v1

- `_changes`-based continuous sync in the first preprocess PR
- database-backed sync checkpoint state such as `npm_sync_state`
- delete and unpublish handling
- splitting `versions` or dependency maps into separate relational tables
- native C++ PostgreSQL access in the first indexed resolver handoff
