alter table public.simulation_derived_metrics
  add column if not exists hhi_ev_concentration numeric null,
  add column if not exists effective_chase_count numeric null;
