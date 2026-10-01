begin;

-- The rarity stage is invoked inside build_pokemon_market_explorer_surface_candidate_v2,
-- whose publication statement is already bounded to 300s. PostgreSQL's
-- statement_timeout measures from the start of the outer command, so a nested
-- 180s function setting can expire after earlier candidate stages have already
-- consumed part of that same command budget. The isolated optimized rarity
-- stage completes in ~84s on the production-sized cohort; align its nested
-- guard with the existing candidate builder budget rather than shortening the
-- outer statement mid-flight.
alter function public.stage_pokemon_market_explorer_rarity_candidates_v2(uuid,date)
  set statement_timeout='300s';

commit;
