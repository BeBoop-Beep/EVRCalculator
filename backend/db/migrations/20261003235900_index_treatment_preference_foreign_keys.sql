-- Cover Treatment Direct Preference V1 response foreign keys.
-- Research-only indexes; no data mutation.

begin;

create index if not exists idx_pokemon_treatment_preference_v1_set
on public.pokemon_treatment_preference_v1_responses (set_id);

create index if not exists idx_pokemon_treatment_preference_v1_left_card
on public.pokemon_treatment_preference_v1_responses (left_card_id);

create index if not exists idx_pokemon_treatment_preference_v1_right_card
on public.pokemon_treatment_preference_v1_responses (right_card_id);

commit;
