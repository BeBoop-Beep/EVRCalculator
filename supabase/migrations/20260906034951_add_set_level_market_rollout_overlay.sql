CREATE TABLE IF NOT EXISTS public.pokemon_market_set_rollout_v1 (
    set_id uuid PRIMARY KEY REFERENCES public.sets(id) ON DELETE CASCADE,
    activated_market_date date NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.pokemon_market_set_rollout_v1 ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.pokemon_market_set_rollout_v1 FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.pokemon_market_set_rollout_v1 TO service_role;

CREATE OR REPLACE VIEW public.pokemon_market_rollout_root_sets_v1 AS
SELECT s.id AS set_id,
       s.name AS set_name,
       s.canonical_key,
       s.era_id,
       e.name AS era_name,
       s.release_date,
       s.logo_image_url,
       s.symbol_image_url,
       CASE
         WHEN coalesce(r.enabled,false) AND coalesce(sr.enabled,false)
           THEN least(r.activated_market_date, sr.activated_market_date)
         WHEN coalesce(r.enabled,false) THEN r.activated_market_date
         ELSE sr.activated_market_date
       END AS activated_market_date,
       v.expected_card_count,
       v.priced_card_count,
       v.coverage_pct,
       v.quality_status
FROM public.sets s
JOIN public.eras e ON e.id=s.era_id
LEFT JOIN public.pokemon_market_era_rollout r ON r.era_id=s.era_id AND r.enabled
LEFT JOIN public.pokemon_market_set_rollout_v1 sr ON sr.set_id=s.id AND sr.enabled
JOIN public.pokemon_market_root_set_value_latest_v1 v ON v.set_id=s.id AND v.market_scope='standard'
WHERE (coalesce(r.enabled,false) OR coalesce(sr.enabled,false))
  AND s.parent_opening_set_id IS NULL
  AND coalesce(s.catalog_only,false)=false
  AND coalesce(s.ready_for_daily_scrape,false)=true
  AND coalesce(v.coverage_pct,0)>=95;

COMMENT ON TABLE public.pokemon_market_set_rollout_v1 IS
'Backend-only per-root opt-in overlay for the canonical market rollout. Allows exact-parity roots to migrate without enabling a mixed-quality era.';
COMMENT ON VIEW public.pokemon_market_rollout_root_sets_v1 IS
'Effective canonical market rollout roots from enabled era rollout OR explicit set-level rollout, restricted to ready root sets with >=95% standard-scope coverage.';