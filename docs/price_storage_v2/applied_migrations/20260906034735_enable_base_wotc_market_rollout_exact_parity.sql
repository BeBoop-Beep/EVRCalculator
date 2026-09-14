INSERT INTO public.pokemon_market_era_rollout(era_id,activated_market_date,enabled,notes)
SELECT e.id,
       (SELECT max(q.market_date)::date FROM public.pokemon_market_date_quality q WHERE q.tcg='pokemon' AND q.status IN ('READY','LEGACY_VERIFIED')),
       true,
       'Price Storage V2 cleanup rollout: Base Set 2 standard scope verified exact parity on set value, top10 aggregate, and 10/10 chase rows before activation.'
FROM public.eras e
WHERE e.name='Base/WOTC'
  AND NOT EXISTS (SELECT 1 FROM public.pokemon_market_era_rollout r WHERE r.era_id=e.id);