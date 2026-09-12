CREATE TABLE IF NOT EXISTS public.pokemon_set_market_constituent_v2_acceptance (
    set_id uuid PRIMARY KEY REFERENCES public.sets(id) ON DELETE CASCADE,
    start_date date NOT NULL,
    end_date date NOT NULL,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','processing','complete','failed')),
    attempts integer NOT NULL DEFAULT 0,
    old_rows bigint,
    v2_rows bigint,
    missing_side bigint,
    mismatches bigint,
    mismatch_cards bigint,
    mismatch_dates bigint,
    first_mismatch date,
    last_mismatch date,
    last_error text,
    started_at timestamptz,
    completed_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.pokemon_set_market_constituent_v2_acceptance ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.pokemon_set_market_constituent_v2_acceptance FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON TABLE public.pokemon_set_market_constituent_v2_acceptance TO service_role;
GRANT ALL ON TABLE public.pokemon_set_market_constituent_v2_acceptance TO postgres;

CREATE OR REPLACE FUNCTION public.compare_pokemon_set_market_constituents_v2_full_history(
    p_set_id uuid,
    p_start_date date,
    p_end_date date
)
RETURNS TABLE(
    old_rows bigint,
    v2_rows bigint,
    missing_side bigint,
    mismatches bigint,
    mismatch_cards bigint,
    mismatch_dates bigint,
    first_mismatch date,
    last_mismatch date
)
LANGUAGE sql
STABLE
SET search_path TO ''
SET "TimeZone" TO 'America/Phoenix'
SET work_mem TO '64MB'
SET statement_timeout TO '60s'
AS $function$
WITH old_rows_data AS MATERIALIZED (
    SELECT *
    FROM public.get_pokemon_cards_daily_constituents_legacy_shadow(
      ARRAY[p_set_id],p_start_date,p_end_date,NULL::uuid[]
    )
), v2_rows_data AS MATERIALIZED (
    SELECT *
    FROM public.get_pokemon_cards_daily_constituents_v2_shadow(
      ARRAY[p_set_id],p_start_date,p_end_date,NULL::uuid[]
    )
), cmp AS MATERIALIZED (
    SELECT coalesce(o.canonical_card_id,v.canonical_card_id) canonical_card_id,
           coalesce(o.market_date,v.market_date) market_date,
           (o.canonical_card_id IS NULL OR v.canonical_card_id IS NULL) missing,
           (o.card_variant_id IS DISTINCT FROM v.card_variant_id
            OR o.market_price IS DISTINCT FROM v.market_price
            OR o.captured_at IS DISTINCT FROM v.captured_at
            OR o.source IS DISTINCT FROM v.source) mismatch
    FROM old_rows_data o
    FULL JOIN v2_rows_data v
      USING(canonical_card_id,set_id,market_date)
)
SELECT (SELECT count(*) FROM old_rows_data)::bigint,
       (SELECT count(*) FROM v2_rows_data)::bigint,
       count(*) FILTER (WHERE missing)::bigint,
       count(*) FILTER (WHERE mismatch)::bigint,
       count(DISTINCT canonical_card_id) FILTER (WHERE mismatch)::bigint,
       count(DISTINCT market_date) FILTER (WHERE mismatch)::bigint,
       min(market_date) FILTER (WHERE mismatch),
       max(market_date) FILTER (WHERE mismatch)
FROM cmp;
$function$;
REVOKE ALL ON FUNCTION public.compare_pokemon_set_market_constituents_v2_full_history(uuid,date,date) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.compare_pokemon_set_market_constituents_v2_full_history(uuid,date,date) TO postgres,service_role;

CREATE OR REPLACE FUNCTION public.process_pokemon_set_market_constituent_v2_acceptance(p_limit integer DEFAULT 3)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO ''
AS $function$
DECLARE
    v_job record;
    v_cmp record;
    v_processed integer:=0;
    v_completed integer:=0;
    v_failed integer:=0;
BEGIN
    IF p_limit IS NULL OR p_limit<1 OR p_limit>5 THEN
        RAISE EXCEPTION 'p_limit must be between 1 and 5';
    END IF;
    FOR v_job IN
      SELECT q.set_id,q.start_date,q.end_date
      FROM public.pokemon_set_market_constituent_v2_acceptance q
      WHERE q.status IN ('pending','failed') AND q.attempts<3
      ORDER BY q.set_id
      FOR UPDATE SKIP LOCKED
      LIMIT p_limit
    LOOP
      v_processed:=v_processed+1;
      UPDATE public.pokemon_set_market_constituent_v2_acceptance
      SET status='processing',attempts=attempts+1,started_at=now(),completed_at=NULL,last_error=NULL,updated_at=now()
      WHERE set_id=v_job.set_id;
      BEGIN
        SELECT * INTO v_cmp
        FROM public.compare_pokemon_set_market_constituents_v2_full_history(v_job.set_id,v_job.start_date,v_job.end_date);
        UPDATE public.pokemon_set_market_constituent_v2_acceptance
        SET status='complete',old_rows=v_cmp.old_rows,v2_rows=v_cmp.v2_rows,
            missing_side=v_cmp.missing_side,mismatches=v_cmp.mismatches,
            mismatch_cards=v_cmp.mismatch_cards,mismatch_dates=v_cmp.mismatch_dates,
            first_mismatch=v_cmp.first_mismatch,last_mismatch=v_cmp.last_mismatch,
            completed_at=now(),last_error=NULL,updated_at=now()
        WHERE set_id=v_job.set_id;
        v_completed:=v_completed+1;
      EXCEPTION WHEN OTHERS THEN
        UPDATE public.pokemon_set_market_constituent_v2_acceptance
        SET status='failed',last_error=left(SQLERRM,2000),completed_at=now(),updated_at=now()
        WHERE set_id=v_job.set_id;
        v_failed:=v_failed+1;
      END;
    END LOOP;
    RETURN jsonb_build_object('processed',v_processed,'completed',v_completed,'failed',v_failed);
END;
$function$;
REVOKE ALL ON FUNCTION public.process_pokemon_set_market_constituent_v2_acceptance(integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.process_pokemon_set_market_constituent_v2_acceptance(integer) TO postgres,service_role;

INSERT INTO public.pokemon_set_market_constituent_v2_acceptance(
  set_id,start_date,end_date,status,attempts,old_rows,v2_rows,missing_side,mismatches,
  mismatch_cards,mismatch_dates,first_mismatch,last_mismatch,last_error,started_at,completed_at,updated_at
)
SELECT DISTINCT v.set_id,date '2026-04-07',date '2026-09-05','pending',0,
       NULL::bigint,NULL::bigint,NULL::bigint,NULL::bigint,NULL::bigint,NULL::bigint,
       NULL::date,NULL::date,NULL::text,NULL::timestamptz,NULL::timestamptz,now()
FROM public.pokemon_set_value_daily_history_v2_shadow v
WHERE NOT EXISTS (
  SELECT 1 FROM public.pokemon_edition_split_root_sets_v2 e WHERE e.set_id=v.set_id
)
ON CONFLICT (set_id) DO UPDATE SET
  start_date=EXCLUDED.start_date,end_date=EXCLUDED.end_date,status='pending',attempts=0,
  old_rows=NULL,v2_rows=NULL,missing_side=NULL,mismatches=NULL,mismatch_cards=NULL,mismatch_dates=NULL,
  first_mismatch=NULL,last_mismatch=NULL,last_error=NULL,started_at=NULL,completed_at=NULL,updated_at=now();