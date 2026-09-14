create table if not exists public.pokemon_market_public_era_rollout_v1 (
    era_id uuid primary key references public.eras(id) on delete cascade,
    activated_market_date date not null,
    enabled boolean not null default true,
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

insert into public.pokemon_market_public_era_rollout_v1(
    era_id, activated_market_date, enabled, notes
)
select e.id, date '2026-09-05', true,
       'Public Market staged historical rollout: Sword & Shield only. Older eras activate explicitly one era at a time.'
from public.eras e
where e.name = 'Sword and Shield'
on conflict (era_id) do update
set activated_market_date = excluded.activated_market_date,
    enabled = excluded.enabled,
    notes = excluded.notes,
    updated_at = now();

create or replace view public.pokemon_market_public_rollout_root_sets_v1 as
select s.id as set_id,
       s.name as set_name,
       s.canonical_key,
       s.era_id,
       e.name as era_name,
       s.release_date,
       s.logo_image_url,
       s.symbol_image_url,
       r.activated_market_date,
       v.expected_card_count,
       v.priced_card_count,
       v.coverage_pct,
       v.quality_status
from public.sets s
join public.eras e on e.id = s.era_id
join public.pokemon_market_public_era_rollout_v1 r
  on r.era_id = s.era_id and r.enabled
join public.pokemon_market_root_set_value_latest_v1 v
  on v.set_id = s.id and v.market_scope = 'standard'
where s.parent_opening_set_id is null
  and coalesce(s.catalog_only, false) = false
  and coalesce(s.ready_for_daily_scrape, false) = true
  and coalesce(v.coverage_pct, 0) >= 95;

create or replace function public.refresh_pokemon_market_public_rollout_daily_snapshots_v1(
    p_market_date date default null
) returns jsonb
language plpgsql
set search_path to ''
as $function$
declare
    v_market_date date;
    v_latest_approved date;
    v_standard_rows integer := 0;
    v_top10_value_rows integer := 0;
    v_top10_deleted integer := 0;
    v_top10_rows integer := 0;
begin
    select max(q.market_date)::date
      into v_latest_approved
    from public.pokemon_market_date_quality q
    where q.tcg = 'pokemon'
      and q.status in ('READY','LEGACY_VERIFIED');

    v_market_date := coalesce(p_market_date, v_latest_approved);
    if v_market_date is null then
        raise exception 'No approved Pokemon market date exists';
    end if;
    if v_market_date is distinct from v_latest_approved then
        raise exception 'Public rollout snapshot refresh is current-date only: requested %, latest approved %',
            v_market_date, v_latest_approved;
    end if;

    with roots as materialized (
        select r.set_id
        from public.pokemon_market_public_rollout_root_sets_v1 r
        where r.activated_market_date <= v_market_date
          and (r.release_date is null or r.release_date <= v_market_date)
    ), canonical as materialized (
        select v.set_id,
               v.set_value,
               v.expected_card_count,
               v.priced_card_count,
               v.coverage_pct
        from public.pokemon_market_root_set_value_latest_v1 v
        join roots r on r.set_id = v.set_id
        where v.market_scope = 'standard'
          and coalesce(v.coverage_pct, 0) >= 95
    )
    insert into public.pokemon_set_value_daily_history(
        set_id, snapshot_date, value_scope, set_value,
        priced_card_count, total_card_count, source,
        canonical_card_count, linked_card_count, included_card_count,
        coverage_pct, created_at, updated_at
    )
    select c.set_id, v_market_date, 'standard', c.set_value,
           c.priced_card_count, c.expected_card_count,
           'canonical_root_set_public_rollout_v1',
           c.expected_card_count, c.expected_card_count, c.priced_card_count,
           c.coverage_pct, now(), now()
    from canonical c
    on conflict (set_id, snapshot_date, value_scope) do update
    set set_value = excluded.set_value,
        priced_card_count = excluded.priced_card_count,
        total_card_count = excluded.total_card_count,
        source = excluded.source,
        canonical_card_count = excluded.canonical_card_count,
        linked_card_count = excluded.linked_card_count,
        included_card_count = excluded.included_card_count,
        coverage_pct = excluded.coverage_pct,
        updated_at = now();
    get diagnostics v_standard_rows = row_count;

    with roots as materialized (
        select r.set_id
        from public.pokemon_market_public_rollout_root_sets_v1 r
        where r.activated_market_date <= v_market_date
          and (r.release_date is null or r.release_date <= v_market_date)
    ), grouped as materialized (
        select t.set_id,
               sum(t.market_price)::numeric as set_value,
               count(*)::integer as card_count
        from public.pokemon_market_root_set_top10_latest_v1 t
        join roots r on r.set_id = t.set_id
        where t.market_scope = 'standard'
          and t.publishable_100pct
          and t.rank between 1 and 10
        group by t.set_id
        having count(*) = 10
    )
    insert into public.pokemon_set_value_daily_history(
        set_id, snapshot_date, value_scope, set_value,
        priced_card_count, total_card_count, source,
        canonical_card_count, linked_card_count, included_card_count,
        coverage_pct, created_at, updated_at
    )
    select g.set_id, v_market_date, 'top10', g.set_value,
           g.card_count, 10, 'canonical_root_top10_public_rollout_v1',
           10, 10, g.card_count, 100.00, now(), now()
    from grouped g
    on conflict (set_id, snapshot_date, value_scope) do update
    set set_value = excluded.set_value,
        priced_card_count = excluded.priced_card_count,
        total_card_count = excluded.total_card_count,
        source = excluded.source,
        canonical_card_count = excluded.canonical_card_count,
        linked_card_count = excluded.linked_card_count,
        included_card_count = excluded.included_card_count,
        coverage_pct = excluded.coverage_pct,
        updated_at = now();
    get diagnostics v_top10_value_rows = row_count;

    delete from public.pokemon_set_top_chase_card_daily_history h
    where h.snapshot_date = v_market_date
      and h.set_id in (
          select r.set_id
          from public.pokemon_market_public_rollout_root_sets_v1 r
          where r.activated_market_date <= v_market_date
            and (r.release_date is null or r.release_date <= v_market_date)
      );
    get diagnostics v_top10_deleted = row_count;

    insert into public.pokemon_set_top_chase_card_daily_history(
        set_id, snapshot_date, card_id, card_variant_id, rank,
        name, rarity, image_url, image_small_url, image_large_url,
        market_price, source, source_date, created_at, updated_at
    )
    select t.set_id,
           v_market_date,
           t.canonical_card_id,
           t.card_variant_id,
           t.rank,
           t.card_name,
           t.rarity,
           coalesce(pcc.image_small_url, pcc.image_large_url),
           pcc.image_small_url,
           pcc.image_large_url,
           t.market_price,
           t.source,
           t.captured_at::date,
           now(), now()
    from public.pokemon_market_root_set_top10_latest_v1 t
    join public.pokemon_market_public_rollout_root_sets_v1 r on r.set_id = t.set_id
    join public.pokemon_canonical_cards pcc on pcc.id = t.canonical_card_id
    where t.market_scope = 'standard'
      and t.publishable_100pct
      and t.rank between 1 and 10
      and r.activated_market_date <= v_market_date
      and (r.release_date is null or r.release_date <= v_market_date)
    on conflict (set_id, snapshot_date, rank) do update
    set card_id = excluded.card_id,
        card_variant_id = excluded.card_variant_id,
        name = excluded.name,
        rarity = excluded.rarity,
        image_url = excluded.image_url,
        image_small_url = excluded.image_small_url,
        image_large_url = excluded.image_large_url,
        market_price = excluded.market_price,
        source = excluded.source,
        source_date = excluded.source_date,
        updated_at = now();
    get diagnostics v_top10_rows = row_count;

    return jsonb_build_object(
        'marketDate', v_market_date,
        'rolloutRootCount', (
            select count(*) from public.pokemon_market_public_rollout_root_sets_v1 r
            where r.activated_market_date <= v_market_date
              and (r.release_date is null or r.release_date <= v_market_date)
        ),
        'standardRowsUpserted', v_standard_rows,
        'top10ValueRowsUpserted', v_top10_value_rows,
        'top10RowsDeleted', v_top10_deleted,
        'top10RowsInserted', v_top10_rows
    );
end;
$function$;

revoke all on table public.pokemon_market_public_era_rollout_v1 from anon, authenticated;
revoke all on table public.pokemon_market_public_rollout_root_sets_v1 from anon, authenticated;
grant select on table public.pokemon_market_public_era_rollout_v1 to service_role;
grant select on table public.pokemon_market_public_rollout_root_sets_v1 to service_role;
grant execute on function public.refresh_pokemon_market_public_rollout_daily_snapshots_v1(date) to service_role;