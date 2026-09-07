create or replace function public.get_pokemon_set_value_canonical_prices_as_of_raw_oracle(
    target_set_id uuid,
    target_date date
)
returns table(
    canonical_card_id uuid,
    set_id uuid,
    card_variant_id uuid,
    printing_type text,
    market_price numeric,
    captured_at date,
    source text,
    price_selection_reason text
)
language sql
stable
set search_path to ''
as $$
with near_mint_condition as (
    select id from public.conditions where name='Near Mint' and abbreviation='NM' order by id limit 1
), base_cards as (
    select pcc.* from public.pokemon_canonical_cards pcc where pcc.set_id=target_set_id and pcc.set_value_eligible=true
), manual_identity as (
    select pcc.id canonical_card_id,pcc.set_id,pcc.rarity,link.legacy_card_id,-1 identity_rank
    from base_cards pcc join public.pokemon_canonical_card_legacy_identity_links link on link.canonical_card_id=pcc.id
), parent_api_identity as (
    select pcc.id canonical_card_id,pcc.set_id,pcc.rarity,c.id legacy_card_id,0 identity_rank
    from base_cards pcc join public.cards c on c.set_id=pcc.set_id and c.pokemon_tcg_api_id=pcc.pokemon_tcg_api_card_id
), variant_api_identity as (
    select pcc.id canonical_card_id,pcc.set_id,pcc.rarity,c.id legacy_card_id,1 identity_rank
    from base_cards pcc join public.card_variants matched_variant on matched_variant.pokemon_tcg_api_id=pcc.pokemon_tcg_api_card_id
    join public.cards c on c.id=matched_variant.card_id and c.set_id=pcc.set_id
    where not exists(select 1 from parent_api_identity p where p.canonical_card_id=pcc.id)
), name_number_identity as (
    select pcc.id canonical_card_id,pcc.set_id,pcc.rarity,c.id legacy_card_id,2 identity_rank
    from base_cards pcc
    join public.cards c on c.set_id=pcc.set_id
      and lower(regexp_replace(trim(c.name),'\\s+',' ','g'))=lower(regexp_replace(trim(pcc.name),'\\s+',' ','g'))
      and regexp_replace(split_part(lower(coalesce(c.card_number,'')),'/',1),'^0+','') in (
        regexp_replace(split_part(lower(coalesce(pcc.number,'')),'/',1),'^0+',''),
        regexp_replace(split_part(lower(coalesce(pcc.printed_number,'')),'/',1),'^0+','')
      )
    where not exists(select 1 from parent_api_identity p where p.canonical_card_id=pcc.id)
      and not exists(select 1 from variant_api_identity v where v.canonical_card_id=pcc.id)
), resolved_cards as (
    select * from manual_identity union all select * from parent_api_identity union all select * from variant_api_identity union all select * from name_number_identity
), identity_candidates as (
    select r.canonical_card_id,r.set_id,r.rarity,r.identity_rank,cv.id card_variant_id,cv.printing_type,cv.special_type
    from resolved_cards r join public.card_variants cv on cv.card_id=r.legacy_card_id
), candidates as (
    select ic.canonical_card_id,ic.set_id,ic.card_variant_id,ic.printing_type,latest.market_price,latest.captured_at,latest.source,
      case
        when ic.rarity in ('Common','Uncommon') and ic.printing_type='non-holo' and ic.special_type is null then 'latest_nm_common_uncommon_non_holo_base_print'
        when ic.rarity in ('Common','Uncommon') and ic.printing_type='holo' and ic.special_type is null then 'latest_nm_common_uncommon_holo_fallback'
        when ic.rarity in ('Common','Uncommon') and ic.printing_type='reverse-holo' and ic.special_type is null then 'latest_nm_common_uncommon_regular_reverse_fallback'
        when ic.printing_type='holo' and ic.special_type is null then 'latest_nm_rare_or_hit_holo_base_print'
        when ic.printing_type='non-holo' and ic.special_type is null then 'latest_nm_rare_or_hit_non_holo_fallback'
        when ic.printing_type='reverse-holo' and ic.special_type is null then 'latest_nm_rare_or_hit_regular_reverse_fallback'
        else 'latest_nm_special_or_other_fallback'
      end price_selection_reason,
      row_number() over(partition by ic.canonical_card_id order by
        ic.identity_rank,
        latest.captured_at desc nulls last,
        case when ic.special_type is null then 0 else 1 end,
        case
          when ic.rarity in ('Common','Uncommon') and ic.printing_type='non-holo' then 0
          when ic.rarity in ('Common','Uncommon') and ic.printing_type='holo' then 1
          when ic.rarity in ('Common','Uncommon') and ic.printing_type='reverse-holo' and ic.special_type is null then 2
          when ic.printing_type='holo' then 0
          when ic.printing_type='non-holo' then 1
          when ic.printing_type='reverse-holo' and ic.special_type is null then 2
          else 9 end,
        latest.created_at desc nulls last,
        ic.card_variant_id
      ) selection_rank
    from identity_candidates ic cross join near_mint_condition nmc
    join lateral (
      select po.market_price,po.captured_at,po.source,po.created_at,po.id
      from public.card_variant_price_observations po
      where po.card_variant_id=ic.card_variant_id and po.condition_id=nmc.id and po.market_price>0
        and trim(both '"' from upper(coalesce(po.currency,'')))='USD'
        and po.captured_at<=target_date
      order by po.captured_at desc nulls last,po.created_at desc nulls last,po.id desc
      limit 1
    ) latest on true
)
select canonical_card_id,set_id,card_variant_id,printing_type,market_price,captured_at,source,price_selection_reason
from candidates where selection_rank=1;
$$;
revoke all on function public.get_pokemon_set_value_canonical_prices_as_of_raw_oracle(uuid,date) from public,anon,authenticated;
grant execute on function public.get_pokemon_set_value_canonical_prices_as_of_raw_oracle(uuid,date) to postgres,service_role;