\set ON_ERROR_STOP on
\timing on

-- Mirrored file equality is checked before psql in CI. Exercise custom READY
-- publication and immutable revision membership.
insert into public.pokemon_market_explorer_query_cache(
 query_fingerprint,query_contract_version,service_version,instrument_methodology_version,asset,normalized_spec,status,
 build_token,build_started_at,build_expires_at)
values(repeat('a',64),'v','v','v','cards','{}','building','aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',now(),now()+interval '5 minutes');
select public.publish_pokemon_market_explorer_query_cache_build(repeat('a',64),'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
 date '2026-09-01',date '2026-09-29','{}',1,1,1,
 '[{"cardVariantId":"00000000-0000-0000-0000-000000000001"}]') as published \gset
\if :published
\else
  \quit 1
\endif
do $$ begin
 if (select count(*) from public.pokemon_market_explorer_query_cache_revisions_v1)<>1 then raise exception 'revision missing'; end if;
 if (select count(*) from public.pokemon_market_explorer_query_cache_revision_members_v1)<>1 then raise exception 'revision member missing'; end if;
end $$;

insert into public.pokemon_market_explorer_surface_generations_v2 values(
 '11111111-1111-4111-8111-111111111111','22222222-2222-4222-8222-222222222222','2026-09-29','v','VALIDATED','{}',now());
insert into public.pokemon_market_explorer_surface_generations_v2 values(
 '99999999-9999-4999-8999-999999999999','22222222-2222-4222-8222-222222222222','2026-09-30','v','VALIDATED','{}',now());
insert into public.pokemon_market_explorer_surface_serving_v2 values(1,'11111111-1111-4111-8111-111111111111',null,now());
insert into public.market_activity_generations_v1(activity_generation_id,as_of,surface_generation_id,roster_ref,
 contract_version,domain_version,policy_version,policy,fixture_manifest_sha256,evidence_cutoff,state,serving_state)
values
 ('30000000-0000-4000-8000-000000000001','2026-09-29','11111111-1111-4111-8111-111111111111','{"kind":"SURFACE_V2_GENERATION"}',
 'market_activity_v1.1','market_activity_domain_v1.1.0','v','{}','e6235d9c73dc7ce6e38b81431bcfe60e4a32ae27f2780632aae45d407705e007',now(),'VALIDATED','RETAINED'),
 ('30000000-0000-4000-8000-000000000002','2026-09-29','11111111-1111-4111-8111-111111111111','{"kind":"SURFACE_V2_GENERATION"}',
 'market_activity_v1.1','market_activity_domain_v1.1.0','v','{}','e6235d9c73dc7ce6e38b81431bcfe60e4a32ae27f2780632aae45d407705e007',now(),'BUILDING','RETAINED'),
 ('30000000-0000-4000-8000-000000000003','2026-09-29','11111111-1111-4111-8111-111111111111','{"kind":"SURFACE_V2_GENERATION"}',
 'market_activity_v1.1','market_activity_domain_v1.1.0','v','{}','e6235d9c73dc7ce6e38b81431bcfe60e4a32ae27f2780632aae45d407705e007',now(),'REJECTED','RETAINED'),
 ('30000000-0000-4000-8000-000000000004','2026-09-29','11111111-1111-4111-8111-111111111111','{"kind":"SURFACE_V2_GENERATION"}',
 'market_activity_v1.1','market_activity_domain_v1.1.0','v','{}','e6235d9c73dc7ce6e38b81431bcfe60e4a32ae27f2780632aae45d407705e007',now(),'VALIDATED','RETAINED'),
 ('30000000-0000-4000-8000-000000000005','2026-09-29','11111111-1111-4111-8111-111111111111','{"kind":"SURFACE_V2_GENERATION"}',
 'market_activity_v1.1','market_activity_domain_v1.1.0','v','{}','e6235d9c73dc7ce6e38b81431bcfe60e4a32ae27f2780632aae45d407705e007',now(),'VALIDATED','RETAINED');
insert into public.market_activity_rosters_v1 values(
 '30000000-0000-4000-8000-000000000001','quick:test','PREPARED_GENERATION','{}','2026-09-29',1),
 ('30000000-0000-4000-8000-000000000004','quick:other','PREPARED_GENERATION','{}','2026-09-29',1),
 ('30000000-0000-4000-8000-000000000005','quick:test','PREPARED_GENERATION','{}','2026-09-29',1);
insert into public.market_activity_roster_members_v1 values(
 '30000000-0000-4000-8000-000000000001','quick:test',1,'card:00000000-0000-0000-0000-000000000001:raw','00000000-0000-0000-0000-000000000001'),
 ('30000000-0000-4000-8000-000000000004','quick:other',1,'card:00000000-0000-0000-0000-000000000001:raw','00000000-0000-0000-0000-000000000001'),
 ('30000000-0000-4000-8000-000000000005','quick:test',1,'card:00000000-0000-0000-0000-000000000001:raw','00000000-0000-0000-0000-000000000001');
insert into public.market_activity_instrument_payloads_v1 values
 ('30000000-0000-4000-8000-000000000001','card:00000000-0000-0000-0000-000000000001:raw','{"ok":true}'),
 ('30000000-0000-4000-8000-000000000002','card:00000000-0000-0000-0000-000000000001:raw','{"leak":true}'),
 ('30000000-0000-4000-8000-000000000003','card:00000000-0000-0000-0000-000000000001:raw','{"leak":true}'),
 ('30000000-0000-4000-8000-000000000004','card:00000000-0000-0000-0000-000000000001:raw','{"market":"other"}'),
 ('30000000-0000-4000-8000-000000000005','card:00000000-0000-0000-0000-000000000001:raw','{"market":"test-v2"}');
insert into public.market_activity_group_payloads_v1 values(
 '30000000-0000-4000-8000-000000000001','quick:test',30,'{"ok":true}'),
 ('30000000-0000-4000-8000-000000000004','quick:other',30,'{"market":"other"}'),
 ('30000000-0000-4000-8000-000000000005','quick:test',30,'{"market":"test-v2"}');

do $$ begin
 if public.get_market_activity_instrument_v1('30000000-0000-4000-8000-000000000001','card:00000000-0000-0000-0000-000000000001:raw') is null then raise exception 'validated instrument hidden'; end if;
 if public.get_market_activity_group_v1('30000000-0000-4000-8000-000000000001','quick:test',30::smallint) is null then raise exception 'validated group hidden'; end if;
 if public.get_market_activity_instrument_v1('30000000-0000-4000-8000-000000000002','card:00000000-0000-0000-0000-000000000001:raw') is not null then raise exception 'building leak'; end if;
 if public.get_market_activity_instrument_v1('30000000-0000-4000-8000-000000000003','card:00000000-0000-0000-0000-000000000001:raw') is not null then raise exception 'rejected leak'; end if;
 if not public.promote_market_activity_generation_v1('30000000-0000-4000-8000-000000000001') then raise exception 'promotion failed'; end if;
 if not public.promote_market_activity_generation_v1('30000000-0000-4000-8000-000000000004') then raise exception 'second-market promotion failed'; end if;
 if (select count(*) from public.market_activity_market_serving_v1 where activity_generation_id is not null) <> 2 then raise exception 'per-market serving rows missing'; end if;
 if not public.promote_market_activity_generation_v1('30000000-0000-4000-8000-000000000005') then raise exception 'market-local replacement failed'; end if;
 if (select activity_generation_id from public.market_activity_market_serving_v1 where market_key='quick:other') <> '30000000-0000-4000-8000-000000000004' then raise exception 'publishing A changed B'; end if;
 if (select previous_activity_generation_id from public.market_activity_market_serving_v1 where market_key='quick:test') <> '30000000-0000-4000-8000-000000000001' then raise exception 'market-local rollback pointer missing'; end if;
 if (select serving_state from public.market_activity_generations_v1 where activity_generation_id='30000000-0000-4000-8000-000000000001') <> 'RETAINED' then raise exception 'prior A not retained'; end if;
end $$;

update public.pokemon_market_explorer_surface_serving_v2
set generation_id='99999999-9999-4999-8999-999999999999' where singleton=1;
do $$ begin
 if public.promote_market_activity_generation_v1('30000000-0000-4000-8000-000000000001') then raise exception 'surface mismatch promotion succeeded'; end if;
end $$;
update public.pokemon_market_explorer_surface_serving_v2
set generation_id='11111111-1111-4111-8111-111111111111' where singleton=1;
select * from public.get_market_activity_constituent_page_v1('30000000-0000-4000-8000-000000000001','quick:test',0,50);

-- Direct table access: Supabase service role bypasses RLS; client roles do not.
set role service_role;
select count(*) from public.market_activity_generations_v1;
select count(*) from public.market_activity_market_serving_v1;
reset role;
set role anon;
\set ON_ERROR_STOP off
select * from public.market_activity_generations_v1;
\if :ERROR
\else
  \echo 'anon unexpectedly read activity table'
  \quit 1
\endif
select * from public.market_activity_market_serving_v1;
\if :ERROR
\else
  \echo 'anon unexpectedly read market serving table'
  \quit 1
\endif
insert into public.market_activity_generations_v1 default values;
\if :ERROR
\else
  \echo 'anon unexpectedly wrote activity table'
  \quit 1
\endif
reset role;
set role authenticated;
select * from public.market_activity_generations_v1;
\if :ERROR
\else
  \echo 'authenticated unexpectedly read activity table'
  \quit 1
\endif
reset role;
\set ON_ERROR_STOP on

-- Constant-call capability primitives: one bounded serving query for 1/3/10
-- keys and one generation batch, never one query per market.
\echo 'EXPLAIN capability serving batch 1'
explain (analyze,buffers) select market_key,activity_generation_id
from public.market_activity_market_serving_v1 where market_key = any(array['quick:test']);
\echo 'EXPLAIN capability serving batch 3'
explain (analyze,buffers) select market_key,activity_generation_id
from public.market_activity_market_serving_v1 where market_key = any(array['quick:test','quick:other','missing:1']);
\echo 'EXPLAIN capability serving batch 10'
explain (analyze,buffers) select market_key,activity_generation_id
from public.market_activity_market_serving_v1 where market_key = any(array[
 'quick:test','quick:other','missing:1','missing:2','missing:3','missing:4','missing:5','missing:6','missing:7','missing:8']);

\echo 'EXPLAIN instrument'
explain (analyze,buffers) select public.get_market_activity_instrument_v1(
 '30000000-0000-4000-8000-000000000001','card:00000000-0000-0000-0000-000000000001:raw');
\echo 'EXPLAIN group'
explain (analyze,buffers) select public.get_market_activity_group_v1(
 '30000000-0000-4000-8000-000000000001','quick:test',30::smallint);
\echo 'EXPLAIN page'
explain (analyze,buffers) select * from public.get_market_activity_constituent_page_v1(
 '30000000-0000-4000-8000-000000000001','quick:test',0,50);

-- Parse and dependency-check the documented destructive rollback without
-- retaining it. Disable is independently non-destructive (null serving ptr).
begin;
update public.market_activity_market_serving_v1 set activity_generation_id=null;
drop function public.get_market_activity_constituent_page_v1(uuid,text,integer,integer);
drop function public.get_market_activity_instrument_v1(uuid,text);
drop function public.get_market_activity_group_v1(uuid,text,smallint);
drop function public.promote_market_activity_generation_v1(uuid);
drop table public.market_activity_market_serving_v1;
rollback;
select 'FMA2_PER_MARKET_POSTGRES_VALIDATION_OK' as receipt;
