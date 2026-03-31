CREATE TABLE IF NOT EXISTS public.npm_tombstones (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL CHECK (btrim(name) <> ''),
    source_rev TEXT,
    deleted_seq TEXT,
    deleted_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (name)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_npm_tombstones_name
    ON public.npm_tombstones (name);

CREATE INDEX IF NOT EXISTS idx_npm_tombstones_deleted_at
    ON public.npm_tombstones (deleted_at DESC);

COMMENT ON TABLE public.npm_tombstones IS
    'Active package-level delete markers observed from the npm _changes feed.';

COMMENT ON COLUMN public.npm_tombstones.deleted_seq IS
    'The _changes sequence token that produced the active delete marker.';
