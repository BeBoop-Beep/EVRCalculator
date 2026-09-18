-- Disk IO remediation: align the Top Chase freshness lookup with its actual
-- production predicate/order:
--
--   WHERE set_id = ?
--   ORDER BY updated_at DESC
--   LIMIT 1
--
-- This file intentionally contains no BEGIN/COMMIT wrapper because
-- CREATE INDEX CONCURRENTLY is not legal inside a transaction block.
-- Production execution still requires explicit operator approval.
create index concurrently if not exists idx_pokemon_top_chase_history_set_updated_at
on public.pokemon_set_top_chase_card_daily_history (set_id, updated_at desc);
