begin;
set local lock_timeout = '5s';

CREATE OR REPLACE FUNCTION public.get_pokemon_cards_daily_constituents_v2_guarded(p_set_ids uuid[], p_start_date date, p_end_date date, p_card_ids uuid[] DEFAULT NULL::uuid[])
 RETURNS TABLE(canonical_card_id uuid, set_id uuid, market_date date, market_price numeric, card_variant_id uuid, source text, captured_at date)
 LANGUAGE plpgsql
 STABLE
 SET search_path TO ''
 SET "TimeZone" TO 'America/Phoenix'
AS $function$
DECLARE
  v_reader_verified boolean;
BEGIN
  IF p_set_ids IS NULL OR cardinality(p_set_ids)=0 THEN
    RAISE EXCEPTION 'get_pokemon_cards_daily_constituents requires a non-empty p_set_ids';
  END IF;
  IF p_start_date IS NULL OR p_end_date IS NULL OR p_start_date>p_end_date THEN
    RAISE EXCEPTION 'get_pokemon_cards_daily_constituents requires a valid bounded date range';
  END IF;

  -- NULL means unrestricted. An explicitly empty filter means no cards,
  -- matching the original public constituent contract.
  IF p_card_ids IS NOT NULL AND cardinality(p_card_ids)=0 THEN
    RETURN;
  END IF;

  -- Acceptance is tied to the actual tested implementation, not its name.
  -- A subsequent reader change falls back to raw until independently accepted.
  v_reader_verified := md5(pg_get_functiondef(
    'public.get_pokemon_cards_daily_constituents_v2_shadow(uuid[],date,date,uuid[])'::regprocedure
  )) = '756f4d28ea3710f59bb23f254ecd3580';

  RETURN QUERY
  WITH requested AS MATERIALIZED (
    SELECT DISTINCT u.requested_set_id
    FROM unnest(p_set_ids) AS u(requested_set_id)
    WHERE u.requested_set_id IS NOT NULL
  ), approved AS MATERIALIZED (
    SELECT r.requested_set_id, a.start_date, a.end_date
    FROM requested r
    JOIN public.pokemon_set_market_constituent_v2_acceptance a
      ON a.set_id=r.requested_set_id
    WHERE v_reader_verified
      AND a.status='complete'
      AND a.missing_side=0
      AND a.mismatches=0
      AND a.old_rows=a.v2_rows
      AND a.start_date IS NOT NULL
      AND a.end_date IS NOT NULL
      AND a.start_date<=a.end_date
      AND NOT EXISTS (
        SELECT 1
        FROM public.pokemon_set_market_constituent_legacy_exceptions_v2 e
        WHERE e.set_id=r.requested_set_id
      )
  ), v2_segments AS MATERIALIZED (
    SELECT a.requested_set_id,
           greatest(p_start_date,a.start_date) AS from_date,
           least(p_end_date,a.end_date) AS through_date
    FROM approved a
    WHERE a.start_date<=p_end_date AND a.end_date>=p_start_date
  ), legacy_segments AS MATERIALIZED (
    -- Unaccepted sets retain their existing reader in full.
    SELECT r.requested_set_id, p_start_date AS from_date, p_end_date AS through_date
    FROM requested r
    WHERE NOT EXISTS(SELECT 1 FROM approved a WHERE a.requested_set_id=r.requested_set_id)
    UNION ALL
    -- Before and after the tested range, use legacy, with no overlap.
    SELECT a.requested_set_id,p_start_date,least(p_end_date,a.start_date-1)
    FROM approved a WHERE p_start_date<a.start_date
    UNION ALL
    SELECT a.requested_set_id,greatest(p_start_date,a.end_date+1),p_end_date
    FROM approved a WHERE p_end_date>a.end_date
  ), result_rows AS (
    -- Bounded per-set calls avoid the pathological all-set expansion observed
    -- when feeding the V2 SQL function a large multi-set array.
    SELECT v.*
    FROM v2_segments seg
    CROSS JOIN LATERAL public.get_pokemon_cards_daily_constituents_v2_shadow(
      ARRAY[seg.requested_set_id],seg.from_date,seg.through_date,p_card_ids
    ) v
    UNION ALL
    SELECT l.*
    FROM legacy_segments seg
    CROSS JOIN LATERAL public.get_pokemon_cards_daily_constituents_legacy_shadow(
      ARRAY[seg.requested_set_id],seg.from_date,seg.through_date,p_card_ids
    ) l
  )
  SELECT r.canonical_card_id,r.set_id,r.market_date,r.market_price,
         r.card_variant_id,r.source,r.captured_at
  FROM result_rows r
  ORDER BY r.market_date,r.canonical_card_id,r.set_id;
END;
$function$;

CREATE OR REPLACE FUNCTION public.refresh_card_market_top_hits_latest()
 RETURNS void
 LANGUAGE plpgsql
AS $function$
begin
  truncate table public.card_market_top_hits_latest;

  insert into public.card_market_top_hits_latest (
    set_id,
    card_id,
    card_variant_id,
    condition_id,
    rank,
    card_name,
    card_number,
    rarity,
    market_price,
    currency,
    source,
    captured_at
  )
  with near_mint_condition as (
    select id
    from public.conditions
    where lower(name) in ('near mint', 'nm')
    limit 1
  ),
  latest_observations as (
    select
      o.card_variant_id,
      o.condition_id,
      o.market_price,
      o.currency,
      o.source,
      o.captured_at,
      o.created_at,
      row_number() over (
        partition by o.card_variant_id, o.source
        order by o.captured_at desc nulls last, o.created_at desc
      ) as rn
    from public.card_variant_price_observations o
    join near_mint_condition nmc
      on nmc.id = o.condition_id
    where o.market_price is not null
      and o.currency = 'USD'
      and o.source = 'TCGPlayer'
  ),
  latest_nm_per_variant as (
    select
      lo.card_variant_id,
      lo.condition_id,
      lo.market_price,
      lo.currency,
      lo.source,
      lo.captured_at
    from latest_observations lo
    where lo.rn = 1
  ),
  best_nm_latest_per_card as (
    select
      c.set_id,
      c.id as card_id,
      cv.id as card_variant_id,
      lnv.condition_id,
      c.name as card_name,
      c.card_number,
      c.rarity,
      lnv.market_price,
      lnv.currency,
      lnv.source,
      lnv.captured_at,
      row_number() over (
        partition by c.id
        order by lnv.market_price desc nulls last,
                 lnv.captured_at desc nulls last,
                 cv.created_at desc,
                 cv.id
      ) as card_choice_rank
    from latest_nm_per_variant lnv
    join public.card_variants cv
      on cv.id = lnv.card_variant_id
    join public.cards c
      on c.id = cv.card_id
  ),
  ranked_set_hits as (
    select
      bnlpc.set_id,
      bnlpc.card_id,
      bnlpc.card_variant_id,
      bnlpc.condition_id,
      bnlpc.card_name,
      bnlpc.card_number,
      bnlpc.rarity,
      bnlpc.market_price,
      bnlpc.currency,
      bnlpc.source,
      bnlpc.captured_at,
      row_number() over (
        partition by bnlpc.set_id
        order by bnlpc.market_price desc nulls last,
                 bnlpc.card_name asc,
                 bnlpc.card_id
      ) as set_rank
    from best_nm_latest_per_card bnlpc
    where bnlpc.card_choice_rank = 1
  )
  select
    rsh.set_id,
    rsh.card_id,
    rsh.card_variant_id,
    rsh.condition_id,
    rsh.set_rank as rank,
    rsh.card_name,
    rsh.card_number,
    rsh.rarity,
    rsh.market_price,
    rsh.currency,
    rsh.source,
    rsh.captured_at
  from ranked_set_hits rsh
  where rsh.set_rank <= 10;
end;
$function$;

CREATE OR REPLACE FUNCTION public.refresh_card_market_top_hits_by_edition_latest()
 RETURNS jsonb
 LANGUAGE plpgsql
AS $function$
declare
  v_rows integer := 0;
begin
  truncate table public.card_market_top_hits_by_edition_latest;

  insert into public.card_market_top_hits_by_edition_latest (
    set_id,
    edition,
    card_id,
    card_variant_id,
    condition_id,
    rank,
    card_name,
    card_number,
    rarity,
    market_price,
    currency,
    source,
    captured_at
  )
  with latest_observations as (
    select
      o.card_variant_id,
      o.condition_id,
      o.market_price,
      o.currency,
      o.source,
      o.captured_at,
      o.created_at,
      row_number() over (
        partition by o.card_variant_id, o.condition_id
        order by o.captured_at desc nulls last, o.created_at desc
      ) as rn
    from public.card_variant_price_observations o
    where o.market_price is not null
      and o.currency = 'USD'
      and o.source = 'TCGPlayer'
  ),
  latest_per_variant_condition as (
    select
      lo.card_variant_id,
      lo.condition_id,
      lo.market_price,
      lo.currency,
      lo.source,
      lo.captured_at
    from latest_observations lo
    where lo.rn = 1
  ),
  joined as (
    select
      c.set_id,
      coalesce(cv.edition, '') as edition,
      c.id as card_id,
      cv.id as card_variant_id,
      lpvc.condition_id,
      c.name as card_name,
      c.card_number,
      c.rarity,
      lpvc.market_price,
      lpvc.currency,
      lpvc.source,
      lpvc.captured_at
    from latest_per_variant_condition lpvc
    join public.card_variants cv
      on cv.id = lpvc.card_variant_id
    join public.cards c
      on c.id = cv.card_id
  ),
  best_available_per_card_identity as (
    select
      j.*,
      row_number() over (
        partition by
          j.set_id,
          j.edition,
          j.card_name,
          j.card_number,
          j.rarity
        order by
          j.market_price desc nulls last,
          j.captured_at desc nulls last,
          j.card_variant_id
      ) as identity_rank
    from joined j
  ),
  ranked as (
    select
      b.set_id,
      b.edition,
      b.card_id,
      b.card_variant_id,
      b.condition_id,
      b.card_name,
      b.card_number,
      b.rarity,
      b.market_price,
      b.currency,
      b.source,
      b.captured_at,
      row_number() over (
        partition by b.set_id, b.edition
        order by
          b.market_price desc nulls last,
          b.card_name asc,
          b.card_number asc
      ) as set_edition_rank
    from best_available_per_card_identity b
    where b.identity_rank = 1
  )
  select
    r.set_id,
    r.edition,
    r.card_id,
    r.card_variant_id,
    r.condition_id,
    r.set_edition_rank as rank,
    r.card_name,
    r.card_number,
    r.rarity,
    r.market_price,
    r.currency,
    r.source,
    r.captured_at
  from ranked r
  where r.set_edition_rank <= 10;

  get diagnostics v_rows = row_count;

  return jsonb_build_object(
    'refreshed_rows', v_rows,
    'table_name', 'card_market_top_hits_by_edition_latest'
  );
end;
$function$;

commit;
