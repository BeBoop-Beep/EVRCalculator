begin;

-- The immutable V2 candidate builder performs all staging in one transaction.
-- Production-sized stage timings after the rarity query-plan fixes total about
-- 165 seconds when run independently, but the atomic combined build incurs
-- substantial temp/WAL/MVCC overhead and can exceed the legacy 300s function
-- timeout before rarity completes. This is a publication-only path protected
-- by the existing advisory lock; public/read request bounds are unchanged.
--
-- Give the atomic candidate up to 10 minutes, then measure the real end-to-end
-- runtime. Do not alter any child-stage math or public query timeout.
alter function public.build_pokemon_market_explorer_surface_candidate_v2(uuid,date,text)
  set statement_timeout='600s';

commit;
