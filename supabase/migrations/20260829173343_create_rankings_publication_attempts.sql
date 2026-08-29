create table if not exists public.pokemon_rankings_publication_attempts (
    id uuid primary key default gen_random_uuid(),
    attempted_market_date date,
    attempted_at timestamptz not null default now(),
    completed_at timestamptz,
    publication_family text not null default 'explore_rankings',
    status text not null,
    reason_code text not null,
    reason_detail text,
    expected_supported_cohort_count integer,
    verified_simulation_cohort_count integer,
    sealed_product_finalized_set_count integer,
    sealed_product_finalized_product_row_count integer,
    product_family_readiness jsonb,
    set_rip_ranked_set_count integer,
    source_run_fingerprint text,
    source_run_ids jsonb,
    resulting_publication_id uuid,
    prior_active_publication_id uuid,
    previous_active_market_date date,
    contract_versions jsonb,
    error_type text,
    error_message text,
    diagnostics jsonb not null default '{}'::jsonb,
    constraint pokemon_rankings_publication_attempts_status_check check (
        status in ('evaluating', 'deferred', 'failed', 'published')
    )
);

comment on table public.pokemon_rankings_publication_attempts is
    'Internal, attempt-oriented observability for Explore / Rankings publication. Never exposed to public clients.';

alter table public.pokemon_rankings_publication_attempts enable row level security;

revoke all on table public.pokemon_rankings_publication_attempts from anon, authenticated;

create index if not exists pokemon_rankings_publication_attempts_market_date_attempted_at_idx
    on public.pokemon_rankings_publication_attempts (attempted_market_date desc, attempted_at desc);
