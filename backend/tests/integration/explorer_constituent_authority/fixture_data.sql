insert into public.eras values ('e0000000-0000-0000-0000-0000000000e1','EX'),('e0000000-0000-0000-0000-0000000000e2','Scarlet and Violet');
insert into public.sets values
 ('50000000-0000-0000-0000-000000000001','Team Rocket','e0000000-0000-0000-0000-0000000000e1'),
 ('50000000-0000-0000-0000-000000000002','Modern Root','e0000000-0000-0000-0000-0000000000e2'),
 ('50000000-0000-0000-0000-000000000003','Big Set','e0000000-0000-0000-0000-0000000000e2'),
 ('50000000-0000-0000-0000-0000000000c2','Modern Subset','e0000000-0000-0000-0000-0000000000e2'),
 ('50000000-0000-0000-0000-0000000000c3','Modern Non-Counting Subset','e0000000-0000-0000-0000-0000000000e2');
create temp table cc as select gen_random_uuid() id, g n from generate_series(1,270) g;
insert into public.pokemon_canonical_cards select id,'Card '||n,n::text,'Rare' from cc;
create temp table vt as
  select gen_random_uuid() id, id cid, n, 'holo' kind from cc
  union all select gen_random_uuid(), id, n, 'reverse-holo' from cc where n<=10;
insert into public.card_variants select id, case when n%2=0 then '1st Edition' else 'Unlimited' end, kind, null from vt;
insert into public.fx_roster select '50000000-0000-0000-0000-000000000001','50000000-0000-0000-0000-000000000001',cid,id,200-n-(case when kind='holo' then 0 else 1 end),date '2026-09-22',true from vt where n<=6 or (n<=3);
insert into public.fx_roster select '50000000-0000-0000-0000-000000000002','50000000-0000-0000-0000-000000000002',cid,id,90-n,date '2026-09-22',true from vt where n between 11 and 13 and kind='holo';
insert into public.fx_roster select '50000000-0000-0000-0000-000000000002','50000000-0000-0000-0000-0000000000c2',cid,id,80-n,date '2026-09-22',true from vt where n between 14 and 15 and kind='holo';
insert into public.fx_roster select '50000000-0000-0000-0000-000000000002','50000000-0000-0000-0000-0000000000c3',cid,id,70-n,date '2026-09-22',false from vt where n between 16 and 17 and kind='holo';
insert into public.fx_roster select '50000000-0000-0000-0000-000000000003','50000000-0000-0000-0000-000000000003',cid,id,1000-n,date '2026-09-22',true from vt where n between 21 and 270 and kind='holo';

insert into public.pokemon_market_explorer_query_cache values
 ('fp_era_ex','maintained','ready','cards',date '2026-09-22',timestamptz '2026-09-22 01:00+00',120,'{"kind":"era","id":"ex"}','{"asOf":"2026-09-22"}'),
 ('fp_rare','maintained','ready','cards',date '2026-09-22',timestamptz '2026-09-22 01:00+00',3,'{"kind":"rarity","id":"rareUltra"}','{"asOf":"2026-09-22"}'),
 ('fp_obt','maintained','ready','cards',date '2026-09-22',timestamptz '2026-09-22 01:00+00',5,'{"kind":"curated","id":"obtainable"}','{"asOf":"2026-09-22"}');
insert into public.pokemon_market_explorer_query_cache_constituents
 select 'fp_era_ex', row_number() over (order by n), jsonb_build_object('rank',row_number() over (order by n),'cardVariantId',id,'cardName','Card '||n,'marketPrice',500-n,'asOf','2026-09-22') from vt where kind='holo' and n between 100 and 219;
insert into public.pokemon_market_explorer_query_cache_constituents
 select 'fp_rare', row_number() over (order by n), jsonb_build_object('rank',row_number() over (order by n),'cardVariantId',id,'cardName','Card '||n,'marketPrice',50-n) from vt where kind='holo' and n between 30 and 32;
insert into public.pokemon_market_explorer_query_cache_constituents
 select 'fp_obt', row_number() over (order by n), jsonb_build_object('rank',row_number() over (order by n),'cardVariantId',id,'cardName','Card '||n,'marketPrice',5) from vt where kind='holo' and n between 40 and 44;

create function pg_temp.seg(n int, fam text[]) returns jsonb language sql as $$
  select jsonb_build_object('isComplete',true,'totalCount',n,'asOf','2026-09-22','idField','sealedProductId','limit',n,
    'topConstituents',(select coalesce(jsonb_agg(jsonb_build_object('rank',i,'sealedProductId',gen_random_uuid(),'productName','Product '||i,
       'productFamily',fam[1+(i%array_length(fam,1))],'marketPrice',3000-i,'setName','S'||i) order by i),'[]'::jsonb) from generate_series(1,n) i))
$$;
insert into public.pokemon_explore_set_value_snapshot_latest values ('pokemon','market',date '2026-09-22',timestamptz '2026-09-22 02:00+00',5,
 jsonb_build_object('sets','[]'::jsonb,'filler',(select string_agg(md5(i::text||'a')||md5(i::text||'b'),'') from generate_series(1,23000) i),'marketOverview',jsonb_build_object('sealedSegments',jsonb_build_object('segments',jsonb_build_object(
   'boosterBox',jsonb_build_object('currentConstituents',pg_temp.seg(30,array['booster_box'])),
   'eliteTrainerBox',jsonb_build_object('currentConstituents',pg_temp.seg(20,array['elite_trainer_box'])),
   'pokemonCenterEliteTrainerBox',jsonb_build_object('currentConstituents',pg_temp.seg(5,array['pokemon_center_elite_trainer_box'])),
   'boosterBundle',jsonb_build_object('currentConstituents',pg_temp.seg(10,array['booster_bundle'])),
   'packs',jsonb_build_object('currentConstituents',pg_temp.seg(178,array['loose_booster_pack','sleeved_booster_pack'])))))));
