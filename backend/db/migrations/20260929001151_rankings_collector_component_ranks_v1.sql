create or replace function public.get_pokemon_card_component_rankings_v1(
  p_model_run_id uuid,
  p_lens text,
  p_set_ids uuid[] default null,
  p_search text default null,
  p_rarity text default null,
  p_offset integer default 0,
  p_limit integer default 50
) returns jsonb
language sql
stable
security invoker
set search_path = public
as $function$
  with eligible as (
    select r.*,
      case p_lens
        when 'pokemon' then r.pokemon_appeal
        when 'trainer' then r.trainer_appeal
        when 'artist' then r.artist_appeal
        when 'playability' then r.playability
      end as component_score
    from public.pokemon_card_collector_appeal_rankings r
    where r.model_run_id = p_model_run_id
      and case p_lens
        when 'pokemon' then r.subject_policy = 'pokemon' and r.pokemon_appeal is not null
        when 'trainer' then r.subject_policy = 'trainer' and r.trainer_appeal is not null
        when 'artist' then r.artist_appeal is not null
        when 'playability' then r.playability is not null
        else false
      end
  ), ranked as (
    select eligible.*,
      rank() over (order by component_score desc) as component_rank,
      count(*) over () as component_cohort_size
    from eligible
  ), filtered as (
    select ranked.*, count(*) over () as filtered_total
    from ranked
    where (p_set_ids is null or ranked.set_id = any(p_set_ids))
      and (p_search is null or ranked.card_name ilike '%' || p_search || '%')
      and (p_rarity is null or ranked.rarity = p_rarity)
  ), page as (
    select * from filtered
    order by component_score desc, pokemon_canonical_card_id
    offset greatest(p_offset, 0)
    limit least(greatest(p_limit, 1), 100)
  )
  select jsonb_build_object(
    'rows', coalesce((select jsonb_agg(to_jsonb(page) order by component_score desc, pokemon_canonical_card_id) from page), '[]'::jsonb),
    'total', coalesce((select max(filtered_total) from filtered), 0),
    'componentCohortSize', coalesce((select max(component_cohort_size) from ranked), 0)
  )
$function$;

revoke all on function public.get_pokemon_card_component_rankings_v1(uuid,text,uuid[],text,text,integer,integer) from public, anon, authenticated;
grant execute on function public.get_pokemon_card_component_rankings_v1(uuid,text,uuid[],text,text,integer,integer) to service_role;
