CREATE TABLE IF NOT EXISTS public.pokemon_set_value_daily_history_v2_shadow (
    set_id uuid NOT NULL REFERENCES public.sets(id) ON DELETE CASCADE,
    snapshot_date date NOT NULL,
    value_scope text NOT NULL,
    set_value numeric,
    priced_card_count integer NOT NULL DEFAULT 0,
    total_card_count integer NOT NULL DEFAULT 0,
    canonical_card_count integer,
    linked_card_count integer,
    included_card_count integer,
    coverage_pct numeric,
    source text NOT NULL,
    built_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (set_id,snapshot_date,value_scope)
);
CREATE INDEX IF NOT EXISTS idx_pokemon_set_value_daily_history_v2_shadow_date_set
  ON public.pokemon_set_value_daily_history_v2_shadow(snapshot_date,set_id);
ALTER TABLE public.pokemon_set_value_daily_history_v2_shadow ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.pokemon_set_value_daily_history_v2_shadow FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON TABLE public.pokemon_set_value_daily_history_v2_shadow TO service_role;
GRANT ALL ON TABLE public.pokemon_set_value_daily_history_v2_shadow TO postgres;

CREATE TABLE IF NOT EXISTS public.pokemon_set_value_daily_history_v2_backfill_sets (
    set_id uuid PRIMARY KEY REFERENCES public.sets(id) ON DELETE CASCADE,
    through_date date NOT NULL,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','processing','complete','failed')),
    attempts integer NOT NULL DEFAULT 0,
    last_error text,
    started_at timestamptz,
    completed_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.pokemon_set_value_daily_history_v2_backfill_sets ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.pokemon_set_value_daily_history_v2_backfill_sets FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON TABLE public.pokemon_set_value_daily_history_v2_backfill_sets TO service_role;
GRANT ALL ON TABLE public.pokemon_set_value_daily_history_v2_backfill_sets TO postgres;

CREATE OR REPLACE FUNCTION public.rebuild_pokemon_set_value_daily_history_v2_shadow_for_set(
    p_set_id uuid,
    p_through_date date
)
RETURNS integer
LANGUAGE plpgsql
SET search_path TO ''
AS $function$
DECLARE
    v_rows integer:=0;
BEGIN
    DELETE FROM public.pokemon_set_value_daily_history_v2_shadow WHERE set_id=p_set_id;
    INSERT INTO public.pokemon_set_value_daily_history_v2_shadow(
      set_id,snapshot_date,value_scope,set_value,priced_card_count,total_card_count,
      canonical_card_count,linked_card_count,included_card_count,coverage_pct,source,built_at
    )
    SELECT r.set_id,r.snapshot_date,r.value_scope,r.set_value,r.priced_card_count,r.total_card_count,
           r.canonical_card_count,r.linked_card_count,r.included_card_count,r.coverage_pct,r.source,now()
    FROM public.get_pokemon_set_value_daily_rows_v2_hybrid_shadow(p_set_id,NULL,p_through_date) r;
    GET DIAGNOSTICS v_rows=ROW_COUNT;
    RETURN v_rows;
END;
$function$;
REVOKE ALL ON FUNCTION public.rebuild_pokemon_set_value_daily_history_v2_shadow_for_set(uuid,date) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.rebuild_pokemon_set_value_daily_history_v2_shadow_for_set(uuid,date) TO postgres,service_role;

CREATE OR REPLACE FUNCTION public.process_pokemon_set_value_daily_history_v2_backfill(p_limit integer DEFAULT 5)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO ''
AS $function$
DECLARE
    v_job record;
    v_processed integer:=0;
    v_completed integer:=0;
    v_failed integer:=0;
    v_rows integer:=0;
BEGIN
    IF p_limit IS NULL OR p_limit<1 OR p_limit>10 THEN
        RAISE EXCEPTION 'p_limit must be between 1 and 10';
    END IF;
    FOR v_job IN
      SELECT q.set_id,q.through_date
      FROM public.pokemon_set_value_daily_history_v2_backfill_sets q
      WHERE q.status IN ('pending','failed') AND q.attempts<5
      ORDER BY q.set_id
      FOR UPDATE SKIP LOCKED
      LIMIT p_limit
    LOOP
      v_processed:=v_processed+1;
      UPDATE public.pokemon_set_value_daily_history_v2_backfill_sets
      SET status='processing',attempts=attempts+1,started_at=now(),completed_at=NULL,last_error=NULL,updated_at=now()
      WHERE set_id=v_job.set_id;
      BEGIN
        v_rows:=public.rebuild_pokemon_set_value_daily_history_v2_shadow_for_set(v_job.set_id,v_job.through_date);
        UPDATE public.pokemon_set_value_daily_history_v2_backfill_sets
        SET status='complete',completed_at=now(),last_error=NULL,updated_at=now()
        WHERE set_id=v_job.set_id;
        v_completed:=v_completed+1;
      EXCEPTION WHEN OTHERS THEN
        UPDATE public.pokemon_set_value_daily_history_v2_backfill_sets
        SET status='failed',completed_at=now(),last_error=left(SQLERRM,2000),updated_at=now()
        WHERE set_id=v_job.set_id;
        v_failed:=v_failed+1;
      END;
    END LOOP;
    RETURN jsonb_build_object('processed',v_processed,'completed',v_completed,'failed',v_failed);
END;
$function$;
REVOKE ALL ON FUNCTION public.process_pokemon_set_value_daily_history_v2_backfill(integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.process_pokemon_set_value_daily_history_v2_backfill(integer) TO postgres,service_role;

INSERT INTO public.pokemon_set_value_daily_history_v2_backfill_sets(set_id,through_date,status,attempts,last_error,started_at,completed_at,updated_at)
SELECT DISTINCT h.set_id,date '2026-09-05','pending'::text,0,NULL::text,NULL::timestamptz,NULL::timestamptz,now()
FROM public.pokemon_set_value_daily_history h
ON CONFLICT (set_id) DO UPDATE
SET through_date=EXCLUDED.through_date,status='pending',attempts=0,last_error=NULL,started_at=NULL,completed_at=NULL,updated_at=now();