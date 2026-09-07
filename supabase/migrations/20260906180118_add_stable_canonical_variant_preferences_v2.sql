CREATE TABLE IF NOT EXISTS public.pokemon_canonical_card_variant_preferences_v2 (
    canonical_card_id uuid PRIMARY KEY REFERENCES public.pokemon_canonical_cards(id) ON DELETE CASCADE,
    preferred_card_variant_id uuid NOT NULL REFERENCES public.card_variants(id) ON DELETE RESTRICT,
    reason text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.pokemon_canonical_card_variant_preferences_v2 ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.pokemon_canonical_card_variant_preferences_v2 FROM PUBLIC, anon, authenticated;
GRANT SELECT ON TABLE public.pokemon_canonical_card_variant_preferences_v2 TO service_role;
GRANT ALL ON TABLE public.pokemon_canonical_card_variant_preferences_v2 TO postgres;

INSERT INTO public.pokemon_canonical_card_variant_preferences_v2 (
    canonical_card_id, preferred_card_variant_id, reason, updated_at
)
SELECT pcc.id,
       latest.card_variant_id,
       'same_day_same_print_stable_tiebreak_preserve_current_authority',
       now()
FROM public.pokemon_canonical_cards pcc
JOIN public.pokemon_canonical_card_market_prices_latest latest
  ON latest.canonical_card_id = pcc.id
 AND latest.set_id = pcc.set_id
WHERE pcc.pokemon_tcg_api_card_id IN (
    'gym2-118','gym1-103','base2-13','neo4-91','neo1-65','neo1-80','neo3-25'
)
  AND latest.card_variant_id IS NOT NULL
ON CONFLICT (canonical_card_id) DO UPDATE
SET preferred_card_variant_id = EXCLUDED.preferred_card_variant_id,
    reason = EXCLUDED.reason,
    updated_at = now();

CREATE OR REPLACE FUNCTION public.get_pokemon_canonical_card_market_prices_latest_for_set_v2_shad(target_set_id uuid)
RETURNS TABLE(canonical_card_id uuid, set_id uuid, pokemon_tcg_api_card_id text, legacy_card_id uuid, card_variant_id uuid, condition_id uuid, printing_type text, market_price numeric, captured_at date, source text, price_selection_reason text)
LANGUAGE sql
STABLE
SET search_path TO ''
AS $function$
WITH near_mint_condition AS (
    SELECT id
    FROM public.conditions
    WHERE name = 'Near Mint'
      AND abbreviation = 'NM'
    ORDER BY id
    LIMIT 1
), manual_identity AS (
    SELECT pcc.*, link.legacy_card_id, -1 AS identity_rank
    FROM public.pokemon_canonical_cards pcc
    JOIN public.pokemon_canonical_card_legacy_identity_links link
      ON link.canonical_card_id = pcc.id
    WHERE pcc.set_id = target_set_id
), parent_api_identity AS (
    SELECT pcc.*, c.id AS legacy_card_id, 0 AS identity_rank
    FROM public.pokemon_canonical_cards pcc
    JOIN public.cards c
      ON c.set_id = pcc.set_id
     AND c.pokemon_tcg_api_id = pcc.pokemon_tcg_api_card_id
    WHERE pcc.set_id = target_set_id
), variant_api_identity AS (
    SELECT pcc.*, c.id AS legacy_card_id, 1 AS identity_rank
    FROM public.pokemon_canonical_cards pcc
    JOIN public.card_variants matched_variant
      ON matched_variant.pokemon_tcg_api_id = pcc.pokemon_tcg_api_card_id
    JOIN public.cards c
      ON c.id = matched_variant.card_id
     AND c.set_id = pcc.set_id
    WHERE pcc.set_id = target_set_id
      AND NOT EXISTS (SELECT 1 FROM parent_api_identity parent_match WHERE parent_match.id = pcc.id)
), name_number_identity AS (
    SELECT pcc.*, c.id AS legacy_card_id, 2 AS identity_rank
    FROM public.pokemon_canonical_cards pcc
    JOIN public.cards c
      ON c.set_id = pcc.set_id
     AND lower(regexp_replace(trim(c.name), '\\s+', ' ', 'g')) = lower(regexp_replace(trim(pcc.name), '\\s+', ' ', 'g'))
     AND regexp_replace(split_part(lower(coalesce(c.card_number, '')), '/', 1), '^0+', '') IN (
         regexp_replace(split_part(lower(coalesce(pcc.number, '')), '/', 1), '^0+', ''),
         regexp_replace(split_part(lower(coalesce(pcc.printed_number, '')), '/', 1), '^0+', '')
     )
    WHERE pcc.set_id = target_set_id
      AND NOT EXISTS (SELECT 1 FROM parent_api_identity parent_match WHERE parent_match.id = pcc.id)
      AND NOT EXISTS (SELECT 1 FROM variant_api_identity variant_match WHERE variant_match.id = pcc.id)
), resolved_cards AS (
    SELECT * FROM manual_identity
    UNION ALL SELECT * FROM parent_api_identity
    UNION ALL SELECT * FROM variant_api_identity
    UNION ALL SELECT * FROM name_number_identity
), identity_candidates AS (
    SELECT resolved.id AS canonical_card_id, resolved.set_id, resolved.pokemon_tcg_api_card_id,
           resolved.rarity, resolved.legacy_card_id, cv.id AS card_variant_id,
           cv.printing_type, cv.special_type, resolved.identity_rank
    FROM resolved_cards resolved
    JOIN public.card_variants cv ON cv.card_id = resolved.legacy_card_id
), candidates AS (
    SELECT ic.canonical_card_id, ic.set_id, ic.pokemon_tcg_api_card_id, ic.legacy_card_id,
           ic.card_variant_id, latest.condition_id, ic.printing_type, latest.market_price,
           latest.captured_at, latest.source,
           CASE
             WHEN ic.rarity IN ('Common','Uncommon') AND ic.printing_type='non-holo' AND ic.special_type IS NULL THEN 'latest_nm_common_uncommon_non_holo_base_print'
             WHEN ic.rarity IN ('Common','Uncommon') AND ic.printing_type='holo' AND ic.special_type IS NULL THEN 'latest_nm_common_uncommon_holo_fallback'
             WHEN ic.rarity IN ('Common','Uncommon') AND ic.printing_type='reverse-holo' AND ic.special_type IS NULL THEN 'latest_nm_common_uncommon_regular_reverse_fallback'
             WHEN ic.printing_type='holo' AND ic.special_type IS NULL THEN 'latest_nm_rare_or_hit_holo_base_print'
             WHEN ic.printing_type='non-holo' AND ic.special_type IS NULL THEN 'latest_nm_rare_or_hit_non_holo_fallback'
             WHEN ic.printing_type='reverse-holo' AND ic.special_type IS NULL THEN 'latest_nm_rare_or_hit_regular_reverse_fallback'
             ELSE 'latest_nm_special_or_other_fallback'
           END AS price_selection_reason,
           row_number() OVER (
             PARTITION BY ic.canonical_card_id
             ORDER BY ic.identity_rank,
                      latest.captured_at DESC NULLS LAST,
                      CASE WHEN ic.special_type IS NULL THEN 0 ELSE 1 END,
                      CASE
                        WHEN ic.rarity IN ('Common','Uncommon') AND ic.printing_type='non-holo' THEN 0
                        WHEN ic.rarity IN ('Common','Uncommon') AND ic.printing_type='holo' THEN 1
                        WHEN ic.rarity IN ('Common','Uncommon') AND ic.printing_type='reverse-holo' AND ic.special_type IS NULL THEN 2
                        WHEN ic.printing_type='holo' THEN 0
                        WHEN ic.printing_type='non-holo' THEN 1
                        WHEN ic.printing_type='reverse-holo' AND ic.special_type IS NULL THEN 2
                        ELSE 9
                      END,
                      CASE WHEN pref.preferred_card_variant_id = ic.card_variant_id THEN 0 ELSE 1 END,
                      latest.created_at DESC NULLS LAST,
                      ic.card_variant_id
           ) AS selection_rank
    FROM identity_candidates ic
    LEFT JOIN public.pokemon_canonical_card_variant_preferences_v2 pref
      ON pref.canonical_card_id = ic.canonical_card_id
    CROSS JOIN near_mint_condition nmc
    JOIN LATERAL (
      SELECT current_row.condition_id,
             current_row.market_price,
             current_row.last_observed_date AS captured_at,
             current_row.source,
             current_row.last_observation_created_at AS created_at,
             current_row.last_observation_id AS id
      FROM public.card_variant_price_current_v2 current_row
      WHERE current_row.card_variant_id = ic.card_variant_id
        AND current_row.condition_id = nmc.id
        AND current_row.market_price > 0
        AND current_row.currency = 'USD'
      ORDER BY current_row.last_observed_date DESC NULLS LAST,
               current_row.last_observation_created_at DESC NULLS LAST,
               current_row.last_observation_id DESC NULLS LAST
      LIMIT 1
    ) latest ON true
)
SELECT candidates.canonical_card_id, candidates.set_id, candidates.pokemon_tcg_api_card_id,
       candidates.legacy_card_id, candidates.card_variant_id, candidates.condition_id,
       candidates.printing_type, candidates.market_price, candidates.captured_at,
       candidates.source, candidates.price_selection_reason
FROM candidates
WHERE candidates.selection_rank = 1;
$function$;

CREATE OR REPLACE FUNCTION public.get_pokemon_set_value_canonical_prices_as_of_v2_shadow(target_set_id uuid, target_date date)
RETURNS TABLE(canonical_card_id uuid, set_id uuid, card_variant_id uuid, printing_type text, market_price numeric, captured_at date, source text, price_selection_reason text)
LANGUAGE sql
STABLE
SET search_path TO ''
AS $function$
with near_mint_condition as (
    select id
    from public.conditions
    where name='Near Mint' and abbreviation='NM'
    order by id
    limit 1
), base_cards as (
    select pcc.*
    from public.pokemon_canonical_cards pcc
    where pcc.set_id=target_set_id
      and pcc.set_value_eligible=true
), manual_identity as (
    select pcc.id as canonical_card_id,pcc.set_id,pcc.rarity,link.legacy_card_id,-1 as identity_rank
    from base_cards pcc
    join public.pokemon_canonical_card_legacy_identity_links link on link.canonical_card_id=pcc.id
), parent_api_identity as (
    select pcc.id as canonical_card_id,pcc.set_id,pcc.rarity,c.id as legacy_card_id,0 as identity_rank
    from base_cards pcc
    join public.cards c on c.set_id=pcc.set_id and c.pokemon_tcg_api_id=pcc.pokemon_tcg_api_card_id
), variant_api_identity as (
    select pcc.id as canonical_card_id,pcc.set_id,pcc.rarity,c.id as legacy_card_id,1 as identity_rank
    from base_cards pcc
    join public.card_variants matched_variant on matched_variant.pokemon_tcg_api_id=pcc.pokemon_tcg_api_card_id
    join public.cards c on c.id=matched_variant.card_id and c.set_id=pcc.set_id
    where not exists(select 1 from parent_api_identity p where p.canonical_card_id=pcc.id)
), name_number_identity as (
    select pcc.id as canonical_card_id,pcc.set_id,pcc.rarity,c.id as legacy_card_id,2 as identity_rank
    from base_cards pcc
    join public.cards c
      on c.set_id=pcc.set_id
     and lower(regexp_replace(trim(c.name),'\\s+',' ','g'))=lower(regexp_replace(trim(pcc.name),'\\s+',' ','g'))
     and regexp_replace(split_part(lower(coalesce(c.card_number,'')),'/',1),'^0+','') in (
         regexp_replace(split_part(lower(coalesce(pcc.number,'')),'/',1),'^0+',''),
         regexp_replace(split_part(lower(coalesce(pcc.printed_number,'')),'/',1),'^0+','')
     )
    where not exists(select 1 from parent_api_identity p where p.canonical_card_id=pcc.id)
      and not exists(select 1 from variant_api_identity v where v.canonical_card_id=pcc.id)
), resolved_cards as (
    select * from manual_identity
    union all select * from parent_api_identity
    union all select * from variant_api_identity
    union all select * from name_number_identity
), identity_candidates as (
    select resolved.canonical_card_id,resolved.set_id,resolved.rarity,resolved.identity_rank,
           cv.id as card_variant_id,cv.printing_type,cv.special_type
    from resolved_cards resolved
    join public.card_variants cv on cv.card_id=resolved.legacy_card_id
), candidates as (
    select ic.canonical_card_id,ic.set_id,ic.card_variant_id,ic.printing_type,
           state.market_price,state.latest_observed_date as captured_at,state.source,
           case
             when ic.rarity in ('Common','Uncommon') and ic.printing_type='non-holo' and ic.special_type is null then 'latest_nm_common_uncommon_non_holo_base_print'
             when ic.rarity in ('Common','Uncommon') and ic.printing_type='holo' and ic.special_type is null then 'latest_nm_common_uncommon_holo_fallback'
             when ic.rarity in ('Common','Uncommon') and ic.printing_type='reverse-holo' and ic.special_type is null then 'latest_nm_common_uncommon_regular_reverse_fallback'
             when ic.printing_type='holo' and ic.special_type is null then 'latest_nm_rare_or_hit_holo_base_print'
             when ic.printing_type='non-holo' and ic.special_type is null then 'latest_nm_rare_or_hit_non_holo_fallback'
             when ic.printing_type='reverse-holo' and ic.special_type is null then 'latest_nm_rare_or_hit_regular_reverse_fallback'
             else 'latest_nm_special_or_other_fallback'
           end as price_selection_reason,
           row_number() over(
             partition by ic.canonical_card_id
             order by ic.identity_rank,
                      state.latest_observed_date desc nulls last,
                      case when ic.special_type is null then 0 else 1 end,
                      case
                        when ic.rarity in ('Common','Uncommon') and ic.printing_type='non-holo' then 0
                        when ic.rarity in ('Common','Uncommon') and ic.printing_type='holo' then 1
                        when ic.rarity in ('Common','Uncommon') and ic.printing_type='reverse-holo' and ic.special_type is null then 2
                        when ic.printing_type='holo' then 0
                        when ic.printing_type='non-holo' then 1
                        when ic.printing_type='reverse-holo' and ic.special_type is null then 2
                        else 9
                      end,
                      case when pref.preferred_card_variant_id=ic.card_variant_id then 0 else 1 end,
                      ic.card_variant_id
           ) as selection_rank
    from identity_candidates ic
    left join public.pokemon_canonical_card_variant_preferences_v2 pref
      on pref.canonical_card_id=ic.canonical_card_id
    cross join near_mint_condition nmc
    join lateral (
      select priced_source.market_price,priced_source.latest_observed_date,priced_source.source
      from (
        select rr.source,rr.latest_observed_date,ev.market_price
        from (
          select r.source,max(least(r.observed_through,target_date)) as latest_observed_date
          from public.card_variant_price_observation_ranges_v2 r
          where r.card_variant_id=ic.card_variant_id
            and r.condition_id=nmc.id
            and r.currency='USD'
            and r.observed_from<=target_date
          group by r.source
        ) rr
        join lateral (
          select e.market_price
          from public.card_variant_price_events_v2 e
          where e.card_variant_id=ic.card_variant_id
            and e.condition_id=nmc.id
            and e.currency='USD'
            and e.source=rr.source
            and e.effective_date<=target_date
            and e.market_price>0
          order by e.effective_date desc,e.id desc
          limit 1
        ) ev on true
      ) priced_source
      order by priced_source.latest_observed_date desc,priced_source.source desc
      limit 1
    ) state on true
)
select canonical_card_id,set_id,card_variant_id,printing_type,market_price,captured_at,source,price_selection_reason
from candidates
where selection_rank=1;
$function$;