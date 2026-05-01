create table if not exists public.simulation_value_threshold_bins (
    id uuid primary key default gen_random_uuid(),
    calculation_run_id uuid not null
        references public.calculation_runs(id)
        on delete cascade,
    threshold_floor numeric not null,
    threshold_ceiling numeric null,
    occurrence_count integer not null,
    probability numeric not null,
    cumulative_probability numeric null,
    survival_probability numeric null,
    bucket_label text not null,
    bucket_order integer not null,
    created_at timestamptz not null default now(),
    constraint uq_simulation_value_threshold_bins_run_floor_ceiling
        unique (calculation_run_id, threshold_floor, threshold_ceiling)
);

create index if not exists idx_simulation_value_threshold_bins_run_id
    on public.simulation_value_threshold_bins(calculation_run_id);

create index if not exists idx_simulation_value_threshold_bins_run_bucket_order
    on public.simulation_value_threshold_bins(calculation_run_id, bucket_order);
