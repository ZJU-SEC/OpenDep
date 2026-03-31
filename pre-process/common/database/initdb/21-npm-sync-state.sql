CREATE TABLE IF NOT EXISTS public.npm_sync_state (
    id BIGSERIAL PRIMARY KEY,
    source_key TEXT NOT NULL CHECK (btrim(source_key) <> ''),
    registry_base_url TEXT NOT NULL CHECK (btrim(registry_base_url) <> ''),
    changes_url TEXT NOT NULL CHECK (btrim(changes_url) <> ''),
    last_seq TEXT,
    checkpointed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_key)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_npm_sync_state_source_key
    ON public.npm_sync_state (source_key);

CREATE INDEX IF NOT EXISTS idx_npm_sync_state_updated_at
    ON public.npm_sync_state (updated_at DESC);

COMMENT ON TABLE public.npm_sync_state IS
    'Checkpoint state for future npm _changes ingestion against PostgreSQL.';

COMMENT ON COLUMN public.npm_sync_state.last_seq IS
    'Last applied npm _changes sequence token, stored as text for compatibility with non-numeric checkpoints.';
