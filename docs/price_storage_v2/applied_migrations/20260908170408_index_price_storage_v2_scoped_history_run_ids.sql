BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='20s';

CREATE INDEX pokemon_member_set_value_daily_history_v2_run_id_idx
ON public.pokemon_member_set_value_daily_history_v2(run_id);

CREATE INDEX pokemon_root_set_value_daily_history_v2_run_id_idx
ON public.pokemon_root_set_value_daily_history_v2(run_id);

COMMIT;