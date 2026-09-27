create or replace function public.guard_canonical_rollout_root_set_value_history_v1()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    if new.value_scope not in ('standard','top10') then
        return new;
    end if;

    -- Canonical root publication/backfill owns these rows.
    if coalesce(new.source,'') in (
        'canonical_root_set_public_rollout_v1',
        'canonical_root_top10_public_rollout_v1',
        'canonical_root_standard_backfill_v1',
        'canonical_root_top10_backfill_v1'
    ) then
        return new;
    end if;

    -- Once a public Market root is active, a per-physical-set refresh must not
    -- replace its parent+subset standard/top10 row with a parent-only row.
    if exists (
        select 1
        from public.pokemon_market_public_rollout_root_sets_v1 r
        where r.set_id = new.set_id
          and r.activated_market_date <= new.snapshot_date
          and (r.release_date is null or r.release_date <= new.snapshot_date)
          and exists (
              select 1
              from public.sets child
              where child.parent_opening_set_id = new.set_id
                and child.counts_toward_parent_set_value = true
          )
    ) then
        return null;
    end if;

    return new;
end;
$$;

drop trigger if exists trg_guard_canonical_rollout_root_set_value_history_v1
on public.pokemon_set_value_daily_history;

create trigger trg_guard_canonical_rollout_root_set_value_history_v1
before insert or update
on public.pokemon_set_value_daily_history
for each row
execute function public.guard_canonical_rollout_root_set_value_history_v1();
