insert into public.pokemon_collector_entity_reference (
    entity_type, canonical_key, display_name, normalized_name, pokemon_reference_id, identity_metadata_json
)
select
    'pokemon',
    'pokemon:' || p.pokedex_number::text,
    coalesce(nullif(btrim(p.display_name), ''), nullif(btrim(p.canonical_name), ''), 'Pokemon #' || p.pokedex_number::text),
    lower(regexp_replace(coalesce(nullif(btrim(p.canonical_name), ''), nullif(btrim(p.display_name), ''), 'pokemon-' || p.pokedex_number::text), '\s+', ' ', 'g')),
    p.id,
    jsonb_build_object('bootstrap_source', 'pokemon_reference', 'pokedex_number', p.pokedex_number)
from public.pokemon_reference p
on conflict (entity_type, canonical_key) do nothing;

with artists as (
    select
        lower(regexp_replace(btrim(c.artist), '\s+', ' ', 'g')) as normalized_name,
        min(btrim(c.artist)) as display_name
    from public.pokemon_canonical_cards c
    where c.artist is not null and btrim(c.artist) <> ''
    group by lower(regexp_replace(btrim(c.artist), '\s+', ' ', 'g'))
)
insert into public.pokemon_collector_entity_reference (
    entity_type, canonical_key, display_name, normalized_name, identity_metadata_json
)
select
    'artist',
    'artist:' || a.normalized_name,
    a.display_name,
    a.normalized_name,
    jsonb_build_object('bootstrap_source', 'pokemon_canonical_cards.artist')
from artists a
on conflict (entity_type, canonical_key) do nothing;

insert into public.pokemon_card_collector_entity_links (
    pokemon_canonical_card_id,
    collector_entity_id,
    link_role,
    link_position,
    link_count,
    contribution_weight,
    match_method,
    match_confidence,
    notes
)
select
    d.pokemon_canonical_card_id,
    e.id,
    'subject',
    d.link_position,
    d.link_count,
    d.contribution_weight,
    'existing_pokemon_desirability_link:' || d.match_method,
    d.match_confidence,
    concat_ws(' | ', 'bootstrapped from pokemon_card_desirability_links', nullif(d.source, ''), nullif(d.notes, ''))
from public.pokemon_card_desirability_links d
join public.pokemon_collector_entity_reference e
  on e.entity_type = 'pokemon'
 and e.pokemon_reference_id = d.pokemon_reference_id
on conflict (pokemon_canonical_card_id, collector_entity_id, link_role) do nothing;

insert into public.pokemon_card_collector_entity_links (
    pokemon_canonical_card_id,
    collector_entity_id,
    link_role,
    link_position,
    link_count,
    contribution_weight,
    match_method,
    match_confidence,
    notes
)
select
    c.id,
    e.id,
    'artist',
    1,
    1,
    1,
    'canonical_card_artist_exact',
    1,
    'Bootstrapped from pokemon_canonical_cards.artist'
from public.pokemon_canonical_cards c
join public.pokemon_collector_entity_reference e
  on e.entity_type = 'artist'
 and e.normalized_name = lower(regexp_replace(btrim(c.artist), '\s+', ' ', 'g'))
where c.artist is not null and btrim(c.artist) <> ''
on conflict (pokemon_canonical_card_id, collector_entity_id, link_role) do nothing;