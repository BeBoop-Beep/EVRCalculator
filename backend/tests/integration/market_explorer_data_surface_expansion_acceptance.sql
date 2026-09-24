\set ON_ERROR_STOP on
\timing on

-- Deterministic fixture identities.
insert into public.eras(id,name) values
 ('10000000-0000-0000-0000-000000000001','Fixture Era');

insert into public.sets(id,name,era_id,catalog_only) values
 ('20000000-0000-0000-0000-000000000001','Fixture Set A','10000000-0000-0000-0000-000000000001',false),
 ('20000000-0000-0000-0000-000000000002','Fixture Set B','10000000-0000-0000-0000-000000000001',false),
 ('20000000-0000-0000-0000-000000000003','Fixture Set C','10000000-0000-0000-0000-000000000001',false);

insert into public.pokemon_market_set_scope_contract_v1(
 set_id,base_set_name,profile,market_scope,market_key,display_label
)
select id,name,'standard','standard','set:'||id::text,name from public.sets;

insert into public.pokemon_market_date_quality(tcg,market_date,status) values
 ('pokemon','2026-09-17','READY'),('pokemon','2026-09-24','READY');

create temp table fixture_cards as
select
  g,
  gen_random_uuid() canonical_card_id,
  gen_random_uuid() card_variant_id,
  case (g-1)%3
    when 0 then '20000000-0000-0000-0000-000000000001'::uuid
    when 1 then '20000000-0000-0000-0000-000000000002'::uuid
    else '20000000-0000-0000-0000-000000000003'::uuid
  end set_id
from generate_series(1,25) g;

insert into public.pokemon_canonical_cards(
 id,set_id,name,number,printed_number,rarity,set_value_eligible,image_small_url,image_large_url
)
select canonical_card_id,set_id,'GX Fixture Card '||g,g::text,g::text,'Rare Holo GX',true,
       'https://img.example/canonical-'||g||'-small.jpg',
       'https://img.example/canonical-'||g||'-large.jpg'
from fixture_cards;

insert into public.card_variants(id,image_small_url,image_large_url)
select card_variant_id,
       'https://img.example/variant-'||g||'-small.jpg',
       'https://img.example/variant-'||g||'-large.jpg'
from fixture_cards;

insert into public.pokemon_market_explorer_card_current_metadata(
 card_variant_id,canonical_card_id,legacy_card_id,set_id,card_name,card_number,
 rarity,edition,printing_type,special_type,image_url,identity_basis
)
select card_variant_id,canonical_card_id,gen_random_uuid(),set_id,
       'GX Fixture Card '||g,g::text,'Rare Holo GX','unlimited','holo',null,
       'https://img.example/meta-'||g||'.jpg','fixture'
from fixture_cards;

insert into public.pokemon_market_explorer_card_daily_states_v2_shadow(
 market_date,card_variant_id,set_id,market_price
)
select d::date,c.card_variant_id,c.set_id,
       case when d::date='2026-09-17' then 9.00 else 10.00 end
from fixture_cards c
cross join (values ('2026-09-17'::date),('2026-09-24'::date)) v(d);

-- Legacy prepared baseline to prove seed-copy and compact-image enrichment.
insert into public.pokemon_market_explorer_prepared_directory_v1(
 market_key,market_type,label,asset,set_id,era_id,parent_era_id,prepared_series_key,
 comparison_as_of,source_as_of,current_value,comparison_value,comparison_index_value,
 history_available,history_start_date,history_end_date,history_point_count,
 return_7d_pct,screen_group,screen_eligible,source_kind,source_status,metadata,
 generation_id,generated_at
)
values(
 'set:20000000-0000-0000-0000-000000000001','set','Fixture Set A','cards',
 '20000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000001',
 '10000000-0000-0000-0000-000000000001','fixture-set-series',
 '2026-09-24','2026-09-24',84,84,111.111111,true,
 '2026-09-17','2026-09-24',2,11.111111,'card',false,
 'public_set_snapshot','READY',
 '{"marketScope":"standard","baseSetName":"Fixture Set A"}'::jsonb,
 '30000000-0000-0000-0000-000000000001',now()
);

insert into public.pokemon_market_explorer_prepared_history_v1(
 market_key,market_date,index_value,tracked_value,chain_segment_id,generation_id
) values
 ('set:20000000-0000-0000-0000-000000000001','2026-09-17',100,75,0,'30000000-0000-0000-0000-000000000001'),
 ('set:20000000-0000-0000-0000-000000000001','2026-09-24',111.111111,84,0,'30000000-0000-0000-0000-000000000001');

insert into public.pokemon_market_explorer_prepared_constituent_totals_v1(
 generation_id,market_key,asset,source_kind,definition_version,source_as_of,total_count,availability
)
values(
 '30000000-0000-0000-0000-000000000001',
 'set:20000000-0000-0000-0000-000000000001',
 'cards','public_set_snapshot','fixture','2026-09-24',1,'available'
);

insert into public.pokemon_market_explorer_prepared_constituents_v1(
 generation_id,market_key,rank,instrument_id,asset,market_price,price_as_of,item
)
select
 '30000000-0000-0000-0000-000000000001',
 'set:20000000-0000-0000-0000-000000000001',
 1,card_variant_id::text,'cards',10,'2026-09-24',
 jsonb_build_object('setId',set_id,'cardVariantId',card_variant_id,'name','GX Fixture Card '||g)
from fixture_cards order by g limit 1;

-- Raw index stays Set-level mathematically; the new 25-card roster is only the
-- reconciled display composition.
insert into public.pokemon_market_index_daily_history(
 tcg,index_key,market_date,contract_version,methodology_version,basket_value,
 normalized_index_value,set_count,card_count,cohort_fingerprint,
 source_generation_fingerprint,constituents_json
) values
 ('pokemon','raw','2026-09-17','fixture','raw-fixture-v1',225,100,3,25,'fixture','fixture',
  '[{"setId":"20000000-0000-0000-0000-000000000001"},{"setId":"20000000-0000-0000-0000-000000000002"},{"setId":"20000000-0000-0000-0000-000000000003"}]'::jsonb),
 ('pokemon','raw','2026-09-24','fixture','raw-fixture-v1',250,111.111111,3,25,'fixture','fixture',
  '[{"setId":"20000000-0000-0000-0000-000000000001"},{"setId":"20000000-0000-0000-0000-000000000002"},{"setId":"20000000-0000-0000-0000-000000000003"}]'::jsonb);

-- Representative complete sealed taxonomy, including a bulk Case that must
-- never enter Total Sealed.
create temp table fixture_sealed(
 id uuid primary key,set_id uuid,name text,p17 numeric,p24 numeric
);
insert into fixture_sealed values
 ('40000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000001','Fixture Booster Box',100,110),
 ('40000000-0000-0000-0000-000000000002','20000000-0000-0000-0000-000000000002','Fixture Booster Box 2',120,125),
 ('40000000-0000-0000-0000-000000000003','20000000-0000-0000-0000-000000000001','Fixture Elite Trainer Box',40,45),
 ('40000000-0000-0000-0000-000000000004','20000000-0000-0000-0000-000000000003','Fixture Half Booster Box',55,60),
 ('40000000-0000-0000-0000-000000000005','20000000-0000-0000-0000-000000000003','Fixture Enhanced Booster Box',135,140),
 ('40000000-0000-0000-0000-000000000006','20000000-0000-0000-0000-000000000001','Fixture Loose Booster Pack',5,6),
 ('40000000-0000-0000-0000-000000000007','20000000-0000-0000-0000-000000000002','Fixture Sleeved Booster Pack',6,7),
 ('40000000-0000-0000-0000-000000000008','20000000-0000-0000-0000-000000000002','Fixture Build & Battle Box',25,27),
 ('40000000-0000-0000-0000-000000000009','20000000-0000-0000-0000-000000000003','Fixture Build & Battle Stadium',45,48),
 ('40000000-0000-0000-0000-000000000010','20000000-0000-0000-0000-000000000001','Fixture Three-Pack Blister',15,16),
 ('40000000-0000-0000-0000-000000000011','20000000-0000-0000-0000-000000000002','Fixture Single-Pack Blister',7,8),
 ('40000000-0000-0000-0000-000000000012','20000000-0000-0000-0000-000000000003','Fixture Collection Box Set',30,32),
 ('40000000-0000-0000-0000-000000000013','20000000-0000-0000-0000-000000000001','Fixture Case of Booster Boxes',600,620),
 ('40000000-0000-0000-0000-000000000014','20000000-0000-0000-0000-000000000002','Fixture Booster Display',90,95),
 ('40000000-0000-0000-0000-000000000015','20000000-0000-0000-0000-000000000003','Fixture Set of Two Tins',45,46),
 ('40000000-0000-0000-0000-000000000016','20000000-0000-0000-0000-000000000001','Fixture Fun Pack',3,4),
 ('40000000-0000-0000-0000-000000000017','20000000-0000-0000-0000-000000000002','Fixture Booster Bundle',25,28),
 ('40000000-0000-0000-0000-000000000018','20000000-0000-0000-0000-000000000003','Fixture Pokemon Center Elite Trainer Box',55,60);

insert into public.sealed_products(id,set_id,name,image_small_url,image_large_url)
select id,set_id,name,null,null from fixture_sealed;

insert into public.sealed_product_price_observations(
 sealed_product_id,market_price,source,currency,captured_at
)
select id,p17,'fixture','USD',timestamptz '2026-09-17 12:00:00+00' from fixture_sealed
union all
select id,p24,'fixture','USD',timestamptz '2026-09-24 12:00:00+00' from fixture_sealed;

-- Build, validate and promote only inside this disposable fixture DB.
create temp table fixture_generation(generation_id uuid primary key);
do $$
declare
  j jsonb;
  g uuid;
begin
  j:=public.build_pokemon_market_explorer_surface_candidate_v2(
    '30000000-0000-0000-0000-000000000001',
    '2026-09-24',
    'raw-fixture-v1'
  );
  g:=(j->>'generationId')::uuid;
  insert into fixture_generation values(g);

  j:=public.validate_pokemon_market_explorer_surface_candidate_v2(g);
  if j->>'state'<>'VALIDATED' then
    raise exception 'fixture candidate rejected: %',j;
  end if;

  perform public.promote_pokemon_market_explorer_surface_v2(g);
end $$;

-- Acceptance assertions.
do $$
declare
  g uuid;
  j jsonb;
  n integer;
begin
  select generation_id into g from fixture_generation;

  if not exists (
    select 1 from public.pokemon_market_explorer_surface_directory_v2
    where generation_id=g and market_key='raw' and availability='available'
  ) then raise exception 'raw surface missing'; end if;

  if not exists (
    select 1 from public.pokemon_market_explorer_surface_directory_v2
    where generation_id=g and market_key='rarity:rareHoloGx'
  ) then raise exception 'Rare Holo GX candidate missing'; end if;

  if not exists (
    select 1 from public.pokemon_market_explorer_surface_directory_v2
    where generation_id=g and market_key='sealedMarket'
  ) then raise exception 'Total Sealed missing'; end if;

  if not exists (
    select 1 from public.pokemon_market_explorer_surface_directory_v2
    where generation_id=g and market_key='sealed-type:case'
  ) then raise exception 'Case type market missing'; end if;

  if exists (
    select 1 from public.pokemon_market_explorer_surface_constituents_v2
    where generation_id=g and market_key='sealedMarket'
      and (item->>'isBulkContainer')::boolean
  ) then raise exception 'bulk container leaked into Total Sealed'; end if;

  select public.get_pokemon_market_explorer_surface_constituents_v2('raw',g,0,100) into j;
  if (j->>'totalCount')::integer<>25 or jsonb_array_length(j->'rows')<>25 then
    raise exception 'Raw page mismatch: %',j;
  end if;

  select count(*) into n
  from public.search_pokemon_market_explorer_catalog_v1('cards','Rare Holo GX',20)
  where result_kind='rarity' and market_key='rarity:rareHoloGx';
  if n<1 then raise exception 'Rare Holo GX search missing'; end if;

  select count(*) into n
  from public.search_pokemon_market_explorer_catalog_v1('sealed','case',20)
  where result_kind in ('sealed_type','instrument');
  if n<1 then raise exception 'sealed Case search missing'; end if;

  select count(*) into n
  from public.search_pokemon_market_explorer_catalog_v1('graded','anything',20)
  where availability='INSUFFICIENT_AUTHORITY';
  if n<>1 then raise exception 'graded fail-closed state missing'; end if;

  if exists (
    select 1 from public.pokemon_market_explorer_sealed_quick_registry_v1
    where status='APPROVED'
  ) then raise exception 'unapproved sealed quick market was published'; end if;

  if (select status from public.pokemon_market_explorer_focus_readiness_v1 where feature_key='demandPressure')
       <>'DEMAND_PRESSURE_NOT_READY'
  then raise exception 'Demand Pressure readiness wrong'; end if;

  if (select status from public.pokemon_market_explorer_focus_readiness_v1 where feature_key='indexFairValue')
       <>'INDEX_FAIR_VALUE_NOT_READY_FOR_PRODUCTION'
  then raise exception 'Fair Value readiness wrong'; end if;

  begin
    perform public.get_pokemon_market_explorer_surface_constituents_v2(
      'raw','00000000-0000-0000-0000-000000000001',0,100
    );
    raise exception 'generation mismatch did not fail closed';
  exception when others then
    if sqlerrm='generation mismatch did not fail closed' then raise; end if;
  end;

  begin
    perform public.get_pokemon_market_explorer_surface_constituents_v2('raw',g,0,101);
    raise exception 'page limit did not fail closed';
  exception when others then
    if sqlerrm='page limit did not fail closed' then raise; end if;
  end;
end $$;

-- Surface/read performance smoke on representative fixture data.
select count(*) as directory_rows
from public.get_pokemon_market_explorer_surface_directory_v2();

select count(*) as rarity_search_rows
from public.search_pokemon_market_explorer_catalog_v1('cards','Rare Holo GX',20);

select count(*) as sealed_search_rows
from public.search_pokemon_market_explorer_catalog_v1('sealed','Booster Box',20);

select jsonb_array_length(
  public.get_pokemon_market_explorer_surface_constituents_v2(
    'raw',(select generation_id from fixture_generation),0,100
  )->'rows'
) as raw_first_page_rows;
