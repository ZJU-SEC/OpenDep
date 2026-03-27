CREATE TABLE IF NOT EXISTS public.pip_projects_metadata (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    dependency TEXT,
    yanked BOOLEAN DEFAULT FALSE,
    metadata TEXT,
    parsed_type_for_dep TEXT,
    version_struct TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_pip_projects_metadata_name_version
    ON public.pip_projects_metadata (name, version);

CREATE INDEX IF NOT EXISTS idx_pip_projects_metadata_name
    ON public.pip_projects_metadata (name);

CREATE INDEX IF NOT EXISTS idx_pip_projects_metadata_name_version_struct
    ON public.pip_projects_metadata (name, version_struct);

COMMENT ON TABLE public.pip_projects_metadata IS
    'Indexed pip dependency metadata consumed by the pip resolver indexed mode.';

COMMENT ON COLUMN public.pip_projects_metadata.dependency IS
    'JSON-serialized requires_dist list written by the preprocessing pipeline.';

COMMENT ON COLUMN public.pip_projects_metadata.metadata IS
    'JSON-serialized auxiliary metadata such as requires_python, artifact info, warnings, and extraction detail.';
