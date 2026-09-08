begin;

create or replace function public.advance_pokemon_market_explorer_daily_v2_shadow_for_set(
    p_set_id uuid,
    p_through_date date,
    p_retention_days integer default 100
)
returns jsonb
language plpgsql
set search_path to ''
as $function$
declare
    v_coverage public.pokemon_market_explorer_card_daily_coverage_v2_shadow%rowtype;
    v_from date;
    v_append_from date;
    v_rows bigint;
begin
    if p_set_id is null or p_through_date is null then
        raise exception 'set_id and through_date are required';
    end if;
    if p_retention_days is null or p_retention_days < 1 or p_retention_days > 400 then
        raise exception 'p_retention_days must be between 1 and 400';
    end if;

    select * into v_coverage
    from public.pokemon_market_explorer_card_daily_coverage_v2_shadow
    where set_id = p_set_id
    for update;

    if not found then
        return public.rebuild_pokemon_market_explorer_daily_v2_shadow_for_set(
            p_set_id, p_through_date, p_retention_days
        );
    end if;
    if p_through_date < v_coverage.computed_through then
        raise exception 'cannot move V2 daily coverage backward from % to %',
            v_coverage.computed_through, p_through_date;
    end if;

    v_from := p_through_date - (p_retention_days - 1);
    v_append_from := greatest(v_coverage.computed_through + 1, v_from);

    delete from public.pokemon_market_explorer_card_daily_states_v2_shadow
    where set_id = p_set_id and market_date < v_from;

    with approved_dates as materialized (
        select distinct quality.market_date
        from public.pokemon_market_date_quality quality
        where quality.tcg = 'pokemon'
          and quality.market_date between v_append_from and p_through_date
          and quality.status in ('READY', 'LEGACY_VERIFIED')
    )
    insert into public.pokemon_market_explorer_card_daily_states_v2_shadow(
        market_date, card_variant_id, set_id, market_price
    )
    select d.market_date, i.card_variant_id, i.set_id, i.market_price
    from approved_dates d
    join public.pokemon_market_price_intervals_v2_shadow i
      on i.set_id = p_set_id
     and i.valid_from <= d.market_date
     and (i.valid_to is null or d.market_date < i.valid_to)
    on conflict (market_date, card_variant_id) do update
    set set_id = excluded.set_id, market_price = excluded.market_price;

    select count(*) into v_rows
    from public.pokemon_market_explorer_card_daily_states_v2_shadow
    where set_id = p_set_id;

    update public.pokemon_market_explorer_card_daily_coverage_v2_shadow
    set retained_from = v_from,
        computed_through = p_through_date,
        row_count = v_rows,
        retention_days = p_retention_days,
        refreshed_at = clock_timestamp()
    where set_id = p_set_id;

    return jsonb_build_object(
        'set_id', p_set_id,
        'retained_from', v_from,
        'computed_through', p_through_date,
        'retention_days', p_retention_days,
        'row_count', v_rows
    );
end;
$function$;

create or replace function public.renew_pokemon_market_explorer_query_cache_build(
    p_query_fingerprint text,
    p_build_token uuid,
    p_lease_seconds integer default 30
)
returns boolean
language plpgsql
set search_path to ''
as $function$
declare
    v_fingerprint text;
begin
    if p_query_fingerprint is null or length(p_query_fingerprint) <> 64
       or p_build_token is null
       or p_lease_seconds is null or p_lease_seconds < 1 or p_lease_seconds > 300 then
        return false;
    end if;

    update public.pokemon_market_explorer_query_cache
    set build_expires_at = clock_timestamp() + make_interval(secs => p_lease_seconds),
        updated_at = clock_timestamp()
    where query_fingerprint = p_query_fingerprint
      and status = 'building'
      and build_token = p_build_token
      and build_expires_at > clock_timestamp()
    returning query_fingerprint into v_fingerprint;

    return v_fingerprint is not null;
end;
$function$;

revoke all on function public.advance_pokemon_market_explorer_daily_v2_shadow_for_set(uuid,date,integer) from public, anon, authenticated;
grant execute on function public.advance_pokemon_market_explorer_daily_v2_shadow_for_set(uuid,date,integer) to service_role;
revoke all on function public.renew_pokemon_market_explorer_query_cache_build(text,uuid,integer) from public, anon, authenticated;
grant execute on function public.renew_pokemon_market_explorer_query_cache_build(text,uuid,integer) to service_role;

commit;
