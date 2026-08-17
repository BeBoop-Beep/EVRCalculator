BEGIN;

CREATE TABLE IF NOT EXISTS public.simulation_pack_outcome_artifacts (
    calculation_run_id UUID PRIMARY KEY
        REFERENCES public.calculation_runs(id) ON DELETE CASCADE,
    format_version INTEGER NOT NULL CHECK (format_version = 1),
    numeric_dtype TEXT NOT NULL CHECK (numeric_dtype = 'float64'),
    byte_order TEXT NOT NULL CHECK (byte_order = 'little'),
    compression_format TEXT NOT NULL CHECK (compression_format = 'zlib'),
    outcome_count INTEGER NOT NULL CHECK (outcome_count > 0),
    raw_size_bytes BIGINT NOT NULL CHECK (raw_size_bytes = outcome_count::BIGINT * 8),
    compressed_size_bytes BIGINT NOT NULL CHECK (compressed_size_bytes > 0),
    raw_sha256 TEXT NOT NULL CHECK (raw_sha256 ~ '^[0-9a-f]{64}$'),
    payload BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (octet_length(payload) = compressed_size_bytes)
);

ALTER TABLE public.simulation_pack_outcome_artifacts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.simulation_pack_outcome_artifacts FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.simulation_pack_outcome_artifacts TO service_role;

COMMIT;
