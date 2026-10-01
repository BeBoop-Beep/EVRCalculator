begin;

-- Rarity staging is publication-only and already proven equivalent after the
-- self-join/narrow-row optimizations. When invoked inside the full immutable
-- candidate transaction it still incurs materially more temp/MVCC overhead
-- than in isolation and can exceed its former 300s local guard.
--
-- Align only this stage with the candidate builder's existing 600s cap.
-- Public/read paths and every other writer timeout remain unchanged.
alter function public.stage_pokemon_market_explorer_rarity_candidates_v2(uuid,date)
  set statement_timeout='600s';

commit;
