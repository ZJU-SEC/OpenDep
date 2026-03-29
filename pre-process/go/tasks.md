# Go Pre-process Refactor Tasks

## Selected Direction

- Scheme A is the default implementation target for the Go preprocess refactor.
- PostgreSQL is the only persistent store for the new path.
- The authoritative payload is the raw `go.mod` content fetched from the Go proxy.
- Future indexed resolving must keep the current lookup shape:
  - exact query by requested `(module_path, version)`
  - return `raw_mod`
  - continue parsing through `resolving/containerization/images/go/internal/parser/modfile.go`
- v1 does not create split dependency tables for `require`, `replace`, `exclude`, or `retract`.
- v1 does not recreate the legacy MongoDB crawler behavior.

## Constraints Already Confirmed

- The archived code in `pre-process/go/.legacy/go-dependency-crawler/` is incomplete.
- `main.go` references `crawler.StartCrawling(...)`, but that implementation is not present in the archived workspace.
- `internal/crawler/parser.go` is only a storage skeleton and does not preserve the old parsing logic.
- The active runtime in `resolving/containerization/images/go/` already has a stable source contract:
  - `ModSource.FetchGoMod(ctx, module.Version) (*model.ModuleMeta, error)`
- The active online implementation fetches `/<escaped module>/@v/<escaped version>.mod` and then calls `ParseGoMod`.
- Because of that, the database contract should optimize for point lookup and parser reuse, not for pre-expanded dependency edges.

## Legacy-to-v1 Data Mapping

| Legacy field | v1 treatment |
| --- | --- |
| `Path` | keep as `module_path` |
| `Version` | keep as `version` |
| `ModFile` | keep as `raw_mod` |
| `CacheTime` | normalize to `fetched_at` |
| `mod.ModulePath` | not first-class in v1 hot path; can be derived later from `raw_mod` |
| `mod.GoVersion` | not first-class in v1 hot path; can be derived later from `raw_mod` |
| `mod.DirRequire` | do not persist as split rows in v1 |
| `mod.IndirRequire` | do not persist as split rows in v1 |
| `mod.Exclude` | do not persist as split rows in v1 |
| `mod.Replace` | do not persist as split rows in v1 |
| `mod.Retract` | do not persist as split rows in v1 |
| `HasValidMod` | do not store in the primary table in v1 |
| `IsOnPkg` | drop in v1; not needed for resolver contract |

## Target Runtime Storage Contract

Primary table name:

- `go_metadata`

Required row contract for v1:

| Column | Type | Notes |
| --- | --- | --- |
| `module_path` | `text` | requested module path; part of primary key |
| `version` | `text` | requested module version; part of primary key |
| `raw_mod` | `text` | exact `.mod` payload returned by the source |
| `raw_mod_sha256` | `text` | helps idempotent checks and diagnostics |
| `source_url` | `text` | exact URL used to fetch the `.mod` file |
| `fetched_at` | `timestamptz` | wall-clock fetch completion time |
| `created_at` | `timestamptz` | row creation time |
| `updated_at` | `timestamptz` | row update time |

Required constraints for v1:

- `PRIMARY KEY (module_path, version)`
- no dependency-edge child tables
- no dependency on MongoDB
- requested coordinates stay as the lookup key even if the `module` directive inside `raw_mod` differs

Non-goals for v1:

- whole-ecosystem crawling from proxy index timestamps
- persistence of failure rows in PostgreSQL
- materialized dependency edges
- resolver-side PostgreSQL reads in the same first preprocess PR

## Working Assumptions

- The new `pre-process/go/` implementation should follow the current preprocess workspace pattern already used elsewhere in this repository:
  - `adapters/`
  - `pipeline/`
  - `loaders/`
- The new entrypoint should be Docker-friendly and align with the existing preprocess workflow style.
- Input units should be explicit module versions, not open-ended crawling state.

## Task Breakdown

### Phase 0. Freeze Scope and Contract

- [x] Add a short design note to `pre-process/go/README.md` after implementation, stating that v1 is batch ingestion of explicit `module@version` inputs.
- [x] Record that v1 does not attempt to restore `lastModCacheTime`-style crawling from the legacy code.
- [x] Record that the indexed store is designed around resolver hot-path lookup, not analytics-first normalization.
- [x] Record that successful fetches are stored in PostgreSQL and failures are emitted to logs or JSONL instead of a failure table.

### Phase 1. Add Shared PostgreSQL Schema

- [x] Add the Go table definition to the dedicated initdb schema file `pre-process/common/database/initdb/10-go-metadata.sql`.
- [x] Initialize the `go_metadata` table with the v1 columns listed above.
- [x] Add `PRIMARY KEY (module_path, version)`.
- [x] Use loader-managed upsert behavior to refresh `raw_mod`, `raw_mod_sha256`, `source_url`, `fetched_at`, and `updated_at`.
- [x] Update `pre-process/common/database/README.md` so Go is no longer only "reserved for future table" and the split initdb contract is documented.

### Phase 2. Create the New Preprocess Skeleton

- [x] Add `pre-process/go/build.py` as the main batch ingestion entrypoint.
- [x] Add `pre-process/go/adapters/proxy_client.py` to fetch raw `.mod` files from the configured Go proxy.
- [x] Add `pre-process/go/pipeline/module_specs.py` to parse and validate `module@version` inputs.
- [x] Add `pre-process/go/pipeline/records.py` to define the in-memory row contract for `go_metadata`.
- [x] Add `pre-process/go/loaders/postgres_loader.py` with `ensure_schema`, `exists`, and `upsert` support.
- [x] Reuse shared PostgreSQL helpers from `pre-process/common/database/` where practical.

### Phase 3. Implement v1 Ingestion Behavior

- [x] Support explicit single-input ingestion with `--module module@version`.
- [x] Support batch ingestion with `--module-file /path/to/module-list.txt`.
- [x] Support `--dsn`, `--ensure-schema`, `--skip-existing`, `--proxy-base-url`, and `--pretty`.
- [ ] Add `--concurrency` support.
- [x] Implement Go proxy path/version escaping compatible with the current resolver behavior.
- [x] Fetch `/<escaped module>/@v/<escaped version>.mod` and store the payload exactly as returned.
- [x] Compute `raw_mod_sha256` before each upsert.
- [x] Keep the ingest pipeline parse-light:
  - no dependency expansion
  - no split table writes
  - no attempt to mirror resolver graph logic
- [x] Make reruns idempotent for the same `(module_path, version)` input set.

### Phase 4. Containerization and Developer Workflow

- [x] Add `pre-process/go/Dockerfile`.
- [x] Add `pre-process/go/docker-compose.yml`.
- [x] Add `pre-process/go/examples/module-list.txt`.
- [x] Use the shared preprocess PostgreSQL container described in `pre-process/common/database/README.md`.
- [x] Keep the user-facing workflow Docker-first, consistent with the rest of `pre-process/`.

### Phase 5. Documentation

- [x] Expand `pre-process/go/README.md` from the current placeholder into an actual operator guide.
- [x] Document the selected Scheme A storage model and why the table is single-row-per-module-version.
- [x] Document the expected table name `go_metadata`.
- [x] Document the recommended Docker command for single-module ingest.
- [x] Document the recommended Docker command for module-file batch ingest.
- [x] Document the shared PostgreSQL prerequisites and connection conventions.

### Phase 6. Tests and Validation

- [ ] Add unit tests for `module@version` parsing and validation.
- [ ] Add unit tests for Go proxy escaping compatibility.
- [ ] Add unit tests for PostgreSQL upsert behavior.
- [ ] Add unit tests for `--skip-existing` behavior.
- [ ] Add an integration test using a stub HTTP server plus local PostgreSQL.
- [ ] Run a smoke test with a small representative module list and verify that rows can be queried directly by `(module_path, version)`.

### Phase 7. Resolver Handoff Follow-up

- [ ] Add a new PostgreSQL-backed source implementation under `resolving/containerization/images/go/internal/source/`.
- [ ] Keep the source contract aligned with `FetchGoMod(ctx, module.Version)`.
- [ ] In indexed mode, query `go_metadata` by `(module_path, version)`, read `raw_mod`, and continue using the existing parser.
- [ ] Keep `ProxySource` available as the default or fallback until indexed mode is validated end to end.
- [ ] Add resolver configuration for switching between `online` and `indexed` metadata modes.

## Acceptance Criteria

- A stored module version can be served later by exact `(module_path, version)` lookup without joining any dependency tables.
- The stored row contains enough data for the resolver to reconstruct the same `raw_mod` input it currently receives from the online proxy.
- The first implementation is safe to rerun against the same module list and does not require MongoDB.
- The first implementation does not attempt to rebuild full graph semantics inside preprocessing.
- The future resolver integration can be added as a new source implementation, without redesigning the table.

## Explicitly Deferred

- deriving and storing `require` or `replace` edges as separate relational rows
- recreating the legacy concurrent crawler shape
- backfilling the whole Go ecosystem from proxy timestamps
- replacing the existing online Go resolver mode before the indexed path is proven
