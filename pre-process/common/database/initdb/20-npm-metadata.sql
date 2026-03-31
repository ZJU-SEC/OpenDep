CREATE TABLE IF NOT EXISTS public.npm_metadata (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL CHECK (btrim(name) <> ''),
    raw_packument TEXT NOT NULL,
    raw_packument_sha256 TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_rev TEXT,
    fetched_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (name)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_npm_metadata_name
    ON public.npm_metadata (name);

CREATE INDEX IF NOT EXISTS idx_npm_metadata_updated_at
    ON public.npm_metadata (updated_at DESC);

COMMENT ON TABLE public.npm_metadata IS
    'Raw npm packuments indexed for future npm resolver PostgreSQL lookup mode.';

COMMENT ON COLUMN public.npm_metadata.raw_packument IS
    'Exact package document payload fetched from the npm registry.';
