begin;
set local lock_timeout = '5s';

CREATE OR REPLACE FUNCTION public.get_pokemon_market_root_set_card_prices_latest_v1_v2_shadow(p_root_set_id uuid DEFAULT NULL::uuid)
 RETURNS TABLE(root_set_id uuid, root_set_name text, member_set_id uuid, member_set_name text, member_type text, market_scope text, canonical_card_id uuid, card_name text, card_number text, rarity text, canonical_review_status text, card_variant_id uuid, edition text, printing_type text, special_type text, identity_basis text, market_price numeric, captured_at date, source text, price_selection_reason text)
 LANGUAGE sql
 STABLE
 SET search_path TO ''
 SET "TimeZone" TO 'America/Phoenix'
AS $function$
WITH near_mint AS (
    SELECT c.id
    FROM public.conditions c
    WHERE lower(c.name) = 'near mint'
    ORDER BY c.id
    LIMIT 1
),
roots AS (
    SELECT s.id AS root_set_id,
           s.name AS root_set_name
    FROM public.sets s
    WHERE s.parent_opening_set_id IS NULL
      AND s.catalog_only = false
      AND (p_root_set_id IS NULL OR s.id = p_root_set_id)
),
members AS (
    SELECT r.root_set_id,
           r.root_set_name,
           r.root_set_id AS member_set_id,
           r.root_set_name AS member_set_name,
           'main'::text AS member_type
    FROM roots r
    UNION ALL
    SELECT r.root_set_id,
           r.root_set_name,
           child.id,
           child.name,
           coalesce(child.subset_type, 'subset')::text
    FROM roots r
    JOIN public.sets child
      ON child.parent_opening_set_id = r.root_set_id
     AND child.counts_toward_parent_set_value = true
),
eligible_cards AS (
    SELECT m.root_set_id,
           m.root_set_name,
           m.member_set_id,
           m.member_set_name,
           m.member_type,
           pcc.id AS canonical_card_id,
           pcc.name AS card_name,
           coalesce(pcc.number, pcc.printed_number) AS card_number,
           pcc.rarity,
           pcc.canonical_review_status
    FROM members m
    JOIN public.pokemon_canonical_cards pcc
      ON pcc.set_id = m.member_set_id
     AND pcc.set_value_eligible = true
),
edition_evidence AS (
    SELECT ec.root_set_id,
           count(DISTINCT ec.canonical_card_id)::integer AS eligible_card_count,
           count(DISTINCT ec.canonical_card_id) FILTER (WHERE meta.edition = '1st-edition')::integer AS first_edition_card_count,
           count(DISTINCT ec.canonical_card_id) FILTER (WHERE meta.edition = 'unlimited')::integer AS unlimited_card_count
    FROM eligible_cards ec
    LEFT JOIN public.pokemon_market_explorer_card_current_metadata meta
      ON meta.canonical_card_id = ec.canonical_card_id
     AND meta.set_id = ec.member_set_id
    GROUP BY ec.root_set_id
),
root_profiles AS (
    SELECT r.root_set_id,
           r.root_set_name,
           coalesce(ev.eligible_card_count, 0) AS eligible_card_count,
           coalesce(ev.first_edition_card_count, 0) AS first_edition_card_count,
           coalesce(ev.unlimited_card_count, 0) AS unlimited_card_count,
           CASE
             WHEN lower(r.root_set_name) = 'base' THEN 'base_three_printings'
             WHEN coalesce(ev.eligible_card_count, 0) > 0
              AND coalesce(ev.first_edition_card_count, 0) >= greatest(10, ceil(ev.eligible_card_count * 0.50)::integer)
              AND coalesce(ev.unlimited_card_count, 0) >= greatest(10, ceil(ev.eligible_card_count * 0.50)::integer)
               THEN 'edition_split'
             ELSE 'standard'
           END AS profile
    FROM roots r
    LEFT JOIN edition_evidence ev ON ev.root_set_id = r.root_set_id
),
root_scopes AS (
    SELECT rp.root_set_id, rp.root_set_name, 'standard'::text AS market_scope
    FROM root_profiles rp
    WHERE rp.profile = 'standard'
    UNION ALL
    SELECT rp.root_set_id, rp.root_set_name, scope.market_scope
    FROM root_profiles rp
    CROSS JOIN LATERAL (VALUES ('first_edition'::text), ('unlimited'::text)) AS scope(market_scope)
    WHERE rp.profile = 'edition_split'
    UNION ALL
    SELECT rp.root_set_id, rp.root_set_name, scope.market_scope
    FROM root_profiles rp
    CROSS JOIN LATERAL (VALUES ('first_edition'::text), ('shadowless'::text), ('unlimited'::text)) AS scope(market_scope)
    WHERE rp.profile = 'base_three_printings'
),
standard_rows AS (
    SELECT ec.root_set_id,
           ec.root_set_name,
           ec.member_set_id,
           ec.member_set_name,
           ec.member_type,
           'standard'::text AS market_scope,
           ec.canonical_card_id,
           ec.card_name,
           ec.card_number,
           ec.rarity,
           ec.canonical_review_status,
           price.card_variant_id,
           cv.edition,
           cv.printing_type,
           cv.special_type,
           meta.identity_basis,
           price.market_price,
           price.captured_at,
           price.source,
           price.price_selection_reason
    FROM eligible_cards ec
    JOIN root_scopes rs
      ON rs.root_set_id = ec.root_set_id
     AND rs.market_scope = 'standard'
    LEFT JOIN public.pokemon_canonical_card_market_prices_latest price
      ON price.canonical_card_id = ec.canonical_card_id
     AND price.set_id = ec.member_set_id
    LEFT JOIN public.card_variants cv ON cv.id = price.card_variant_id
    LEFT JOIN public.pokemon_market_explorer_card_current_metadata meta
      ON meta.card_variant_id = price.card_variant_id
     AND meta.canonical_card_id = ec.canonical_card_id
),
edition_variant_latest AS (
    SELECT ec.root_set_id,
           ec.root_set_name,
           ec.member_set_id,
           ec.member_set_name,
           ec.member_type,
           rs.market_scope,
           ec.canonical_card_id,
           ec.card_name,
           ec.card_number,
           ec.rarity,
           ec.canonical_review_status,
           meta.card_variant_id,
           meta.edition,
           meta.printing_type,
           meta.special_type,
           meta.identity_basis,
           latest.market_price,
           latest.captured_at,
           latest.source,
           row_number() OVER (
             PARTITION BY ec.root_set_id, rs.market_scope, ec.canonical_card_id
             ORDER BY
               CASE meta.identity_basis
                 WHEN 'explicit_legacy_identity_link' THEN 0
                 WHEN 'parent_pokemon_tcg_api_id' THEN 1
                 WHEN 'normalized_name_number_fallback' THEN 2
                 ELSE 9
               END,
               CASE WHEN meta.special_type IS NULL OR meta.special_type = '' THEN 0 ELSE 1 END,
               CASE
                 WHEN ec.rarity IN ('Common','Uncommon') AND meta.printing_type = 'non-holo' THEN 0
                 WHEN ec.rarity IN ('Common','Uncommon') AND meta.printing_type = 'holo' THEN 1
                 WHEN ec.rarity IN ('Common','Uncommon') AND meta.printing_type = 'reverse-holo' THEN 2
                 WHEN meta.printing_type = 'holo' THEN 0
                 WHEN meta.printing_type = 'non-holo' THEN 1
                 WHEN meta.printing_type = 'reverse-holo' THEN 2
                 ELSE 9
               END,
               latest.captured_at DESC NULLS LAST,
               meta.card_variant_id
           ) AS selection_rank
    FROM eligible_cards ec
    JOIN root_scopes rs
      ON rs.root_set_id = ec.root_set_id
     AND rs.market_scope IN ('first_edition','shadowless','unlimited')
    JOIN public.pokemon_market_explorer_card_current_metadata meta
      ON meta.canonical_card_id = ec.canonical_card_id
     AND meta.set_id = ec.member_set_id
     AND (
       (rs.market_scope = 'first_edition' AND meta.edition = '1st-edition')
       OR (rs.market_scope = 'unlimited' AND meta.edition = 'unlimited')
       OR (rs.market_scope = 'shadowless' AND meta.edition = 'shadowless')
     )
    CROSS JOIN near_mint nm
    LEFT JOIN LATERAL (
      SELECT o.market_price, o.last_observed_date AS captured_at, o.source
      FROM public.card_variant_price_current_v2 o
      WHERE o.card_variant_id = meta.card_variant_id
        AND o.condition_id = nm.id
        AND o.market_price IS NOT NULL
        AND o.market_price > 0
        AND trim(both '"' from upper(coalesce(o.currency,''))) = 'USD'
        AND o.source = 'TCGPlayer'
      ORDER BY o.last_observed_date DESC NULLS LAST, o.last_observation_created_at DESC NULLS LAST, o.last_observation_id DESC
      LIMIT 1
    ) latest ON true
),
edition_selected AS (
    SELECT *
    FROM edition_variant_latest
    WHERE selection_rank = 1
),
edition_rows AS (
    SELECT ec.root_set_id,
           ec.root_set_name,
           ec.member_set_id,
           ec.member_set_name,
           ec.member_type,
           rs.market_scope,
           ec.canonical_card_id,
           ec.card_name,
           ec.card_number,
           ec.rarity,
           ec.canonical_review_status,
           sel.card_variant_id,
           sel.edition,
           sel.printing_type,
           sel.special_type,
           sel.identity_basis,
           sel.market_price,
           sel.captured_at,
           sel.source,
           CASE
             WHEN sel.card_variant_id IS NULL THEN 'missing_required_edition_variant'
             WHEN sel.market_price IS NULL THEN 'required_edition_variant_missing_nm_price'
             ELSE 'edition_exact_latest_nm_preferred_printing'
           END AS price_selection_reason
    FROM eligible_cards ec
    JOIN root_scopes rs
      ON rs.root_set_id = ec.root_set_id
     AND rs.market_scope IN ('first_edition','shadowless','unlimited')
    LEFT JOIN edition_selected sel
      ON sel.root_set_id = ec.root_set_id
     AND sel.market_scope = rs.market_scope
     AND sel.canonical_card_id = ec.canonical_card_id
)
SELECT * FROM standard_rows
UNION ALL
SELECT root_set_id, root_set_name, member_set_id, member_set_name, member_type,
       market_scope, canonical_card_id, card_name, card_number, rarity,
       canonical_review_status, card_variant_id, edition, printing_type,
       special_type, identity_basis, market_price, captured_at, source,
       price_selection_reason
FROM edition_rows;
$function$;


-- Preserve existing function shape and selection rules; lock only the source.

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
            and r.source='TCGPlayer'
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


-- Preserve existing function shape and selection rules; lock only the source.

commit;
