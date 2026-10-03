-- Least-privilege follow-up for Treatment Direct Preference V1.
-- Existing-project default privileges can grant service_role capabilities beyond
-- the CRUD operations required by the research collection API.

begin;

revoke all on table public.pokemon_treatment_preference_v1_block_claims from service_role;
revoke all on table public.pokemon_treatment_preference_v1_responses from service_role;

grant select, insert, update, delete
on table public.pokemon_treatment_preference_v1_block_claims
to service_role;

grant select, insert, update, delete
on table public.pokemon_treatment_preference_v1_responses
to service_role;

commit;
