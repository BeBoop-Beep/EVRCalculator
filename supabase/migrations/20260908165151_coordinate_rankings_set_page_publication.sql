create or replace function public.publish_pokemon_public_rip_leaderboard_with_set_pages(
  p_snapshot jsonb,
  p_rows jsonb,
  p_latest jsonb,
  p_generation_id uuid
) returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_publication_id uuid;
  v_generation_id uuid;
begin
  -- Both existing functions retain their complete validation contracts. Calling
  -- them inside this wrapper places both public-pointer changes in one database
  -- transaction, so no reader can observe mixed Top Chase lineage.
  v_publication_id := public.publish_pokemon_public_rip_leaderboard(
    p_snapshot, p_rows, p_latest
  );
  v_generation_id := public.activate_pokemon_set_page_snapshot_generation(
    p_generation_id
  );
  if v_generation_id is distinct from p_generation_id then
    raise exception 'set-page activation returned unexpected generation %', v_generation_id;
  end if;
  return v_publication_id;
end
$$;

revoke all on function public.publish_pokemon_public_rip_leaderboard_with_set_pages(jsonb,jsonb,jsonb,uuid)
  from public, anon, authenticated;
grant execute on function public.publish_pokemon_public_rip_leaderboard_with_set_pages(jsonb,jsonb,jsonb,uuid)
  to service_role;
alter function public.publish_pokemon_public_rip_leaderboard_with_set_pages(jsonb,jsonb,jsonb,uuid)
  set statement_timeout = '240s';
