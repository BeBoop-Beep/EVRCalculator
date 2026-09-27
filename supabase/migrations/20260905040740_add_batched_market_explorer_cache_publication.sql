create or replace function public.sync_pokemon_market_explorer_query_cache_constituents()
returns trigger
language plpgsql
set search_path to ''
as $$
begin
  if current_setting('market_explorer.skip_constituent_sync', true) = 'on' then
    return new;
  end if;

  delete from public.pokemon_market_explorer_query_cache_constituents
  where query_fingerprint = new.query_fingerprint;

  insert into public.pokemon_market_explorer_query_cache_constituents(
    query_fingerprint, rank, card_variant_id, item
  )
  select
    new.query_fingerprint,
    ordinality::integer,
    nullif(value->>'cardVariantId','')::uuid,
    value
  from jsonb_array_elements(coalesce(new.current_constituents,'[]'::jsonb))
       with ordinality;

  return new;
end
$$;

create or replace function public.stage_pokemon_market_explorer_query_cache_build(
  p_query_fingerprint text,
  p_build_token uuid,
  p_computed_from date,
  p_computed_through date,
  p_series_payload jsonb,
  p_current_value numeric,
  p_constituent_count bigint,
  p_eligible_universe_count bigint,
  p_current_constituents jsonb
)
returns boolean
language plpgsql
set search_path to 'public','pg_temp'
as $$
declare
  staged_fingerprint text;
begin
  if p_query_fingerprint is null
     or length(p_query_fingerprint) <> 64
     or p_build_token is null
     or p_constituent_count is null
     or p_constituent_count < 0
     or jsonb_typeof(coalesce(p_current_constituents,'[]'::jsonb)) <> 'array' then
    return false;
  end if;

  perform set_config('market_explorer.skip_constituent_sync','on', true);

  update public.pokemon_market_explorer_query_cache
  set computed_from = p_computed_from,
      computed_through = p_computed_through,
      series_payload = p_series_payload,
      current_value = p_current_value,
      constituent_count = p_constituent_count,
      eligible_universe_count = p_eligible_universe_count,
      current_constituents = coalesce(p_current_constituents,'[]'::jsonb),
      updated_at = clock_timestamp()
  where query_fingerprint = p_query_fingerprint
    and status = 'building'
    and build_token = p_build_token
    and build_expires_at > clock_timestamp()
  returning query_fingerprint into staged_fingerprint;

  return staged_fingerprint is not null;
end
$$;

create or replace function public.upsert_pokemon_market_explorer_query_cache_constituent_batch(
  p_query_fingerprint text,
  p_build_token uuid,
  p_items jsonb
)
returns integer
language plpgsql
set search_path to 'public','pg_temp'
as $$
declare
  affected integer := 0;
  item_count integer := 0;
begin
  if p_query_fingerprint is null
     or length(p_query_fingerprint) <> 64
     or p_build_token is null
     or jsonb_typeof(coalesce(p_items,'[]'::jsonb)) <> 'array' then
    return -1;
  end if;

  item_count := jsonb_array_length(coalesce(p_items,'[]'::jsonb));
  if item_count < 1 or item_count > 1000 then
    return -1;
  end if;

  if not exists (
    select 1
    from public.pokemon_market_explorer_query_cache c
    where c.query_fingerprint = p_query_fingerprint
      and c.status = 'building'
      and c.build_token = p_build_token
      and c.build_expires_at > clock_timestamp()
  ) then
    return -1;
  end if;

  if exists (
    select 1
    from (
      select (value->>'rank')::integer as rank
      from jsonb_array_elements(p_items)
    ) x
    where x.rank is null or x.rank <= 0
  ) then
    return -1;
  end if;

  if exists (
    select 1
    from (
      select (value->>'rank')::integer as rank, count(*) as n
      from jsonb_array_elements(p_items)
      group by 1
      having count(*) > 1
    ) d
  ) then
    return -1;
  end if;

  insert into public.pokemon_market_explorer_query_cache_constituents(
    query_fingerprint, rank, card_variant_id, item
  )
  select
    p_query_fingerprint,
    (value->>'rank')::integer,
    nullif(value->>'cardVariantId','')::uuid,
    value
  from jsonb_array_elements(p_items)
  on conflict (query_fingerprint, rank) do update
  set card_variant_id = excluded.card_variant_id,
      item = excluded.item;

  get diagnostics affected = row_count;
  return affected;
end
$$;

create or replace function public.trim_pokemon_market_explorer_query_cache_constituent_batch(
  p_query_fingerprint text,
  p_build_token uuid,
  p_keep_through_rank integer,
  p_limit integer default 1000
)
returns integer
language plpgsql
set search_path to 'public','pg_temp'
as $$
declare
  affected integer := 0;
begin
  if p_query_fingerprint is null
     or length(p_query_fingerprint) <> 64
     or p_build_token is null
     or p_keep_through_rank < 0
     or p_limit < 1
     or p_limit > 5000 then
    return -1;
  end if;

  if not exists (
    select 1
    from public.pokemon_market_explorer_query_cache c
    where c.query_fingerprint = p_query_fingerprint
      and c.status = 'building'
      and c.build_token = p_build_token
      and c.build_expires_at > clock_timestamp()
  ) then
    return -1;
  end if;

  with doomed as (
    select ctid
    from public.pokemon_market_explorer_query_cache_constituents
    where query_fingerprint = p_query_fingerprint
      and rank > p_keep_through_rank
    order by rank
    limit p_limit
  )
  delete from public.pokemon_market_explorer_query_cache_constituents d
  using doomed
  where d.ctid = doomed.ctid;

  get diagnostics affected = row_count;
  return affected;
end
$$;

create or replace function public.finalize_pokemon_market_explorer_query_cache_build(
  p_query_fingerprint text,
  p_build_token uuid
)
returns boolean
language plpgsql
set search_path to 'public','pg_temp'
as $$
declare
  expected_count bigint;
  detail_count bigint;
  nonnull_variant_count bigint;
  unique_variant_count bigint;
  min_rank integer;
  max_rank integer;
  published_fingerprint text;
begin
  select c.constituent_count
  into expected_count
  from public.pokemon_market_explorer_query_cache c
  where c.query_fingerprint = p_query_fingerprint
    and c.status = 'building'
    and c.build_token = p_build_token
    and c.build_expires_at > clock_timestamp()
  for update;

  if expected_count is null or expected_count < 0 then
    return false;
  end if;

  select count(*)::bigint,
         count(card_variant_id)::bigint,
         count(distinct card_variant_id)::bigint,
         min(rank),
         max(rank)
  into detail_count, nonnull_variant_count, unique_variant_count, min_rank, max_rank
  from public.pokemon_market_explorer_query_cache_constituents
  where query_fingerprint = p_query_fingerprint;

  if expected_count = 0 then
    if detail_count <> 0 then
      return false;
    end if;
  else
    if detail_count <> expected_count
       or nonnull_variant_count <> expected_count
       or unique_variant_count <> expected_count
       or min_rank <> 1
       or max_rank <> expected_count then
      return false;
    end if;
  end if;

  update public.pokemon_market_explorer_query_cache
  set status = 'ready',
      last_built_at = clock_timestamp(),
      updated_at = clock_timestamp(),
      build_token = null,
      build_started_at = null,
      build_expires_at = null
  where query_fingerprint = p_query_fingerprint
    and status = 'building'
    and build_token = p_build_token
    and build_expires_at > clock_timestamp()
  returning query_fingerprint into published_fingerprint;

  return published_fingerprint is not null;
end
$$;

revoke all on function public.stage_pokemon_market_explorer_query_cache_build(text,uuid,date,date,jsonb,numeric,bigint,bigint,jsonb) from public, anon, authenticated;
revoke all on function public.upsert_pokemon_market_explorer_query_cache_constituent_batch(text,uuid,jsonb) from public, anon, authenticated;
revoke all on function public.trim_pokemon_market_explorer_query_cache_constituent_batch(text,uuid,integer,integer) from public, anon, authenticated;
revoke all on function public.finalize_pokemon_market_explorer_query_cache_build(text,uuid) from public, anon, authenticated;

grant execute on function public.stage_pokemon_market_explorer_query_cache_build(text,uuid,date,date,jsonb,numeric,bigint,bigint,jsonb) to service_role;
grant execute on function public.upsert_pokemon_market_explorer_query_cache_constituent_batch(text,uuid,jsonb) to service_role;
grant execute on function public.trim_pokemon_market_explorer_query_cache_constituent_batch(text,uuid,integer,integer) to service_role;
grant execute on function public.finalize_pokemon_market_explorer_query_cache_build(text,uuid) to service_role;
