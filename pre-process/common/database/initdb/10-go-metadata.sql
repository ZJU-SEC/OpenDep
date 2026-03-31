CREATE TABLE IF NOT EXISTS public.go_metadata (
    id BIGSERIAL PRIMARY KEY,
    module_path TEXT NOT NULL CHECK (btrim(module_path) <> ''),
    version TEXT NOT NULL CHECK (btrim(version) <> ''),
    raw_mod TEXT NOT NULL,
    raw_mod_sha256 TEXT NOT NULL,
    source_url TEXT NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (module_path, version)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_pip_metadata_name_version
    ON public.go_metadata (module_path, version);

CREATE INDEX IF NOT EXISTS idx_go_metadata_updated_at
    ON public.go_metadata (updated_at DESC);

COMMENT ON TABLE public.go_metadata IS
    'Raw go.mod payloads indexed for future Go resolver PostgreSQL lookup mode.';
