UPDATE public.pokemon_canonical_cards
SET catalog_role = 'duplicate_alias',
    set_value_eligible = false,
    opening_eligible = false,
    eligibility_reason = 'duplicate_alias: invalid Gym Challenge checklist row; number 113 is Cinnabar City Gym'
WHERE id = '5b336ad8-1397-42ea-a88b-53c0d67f6d82'::uuid
  AND name = '______''s Chansey (DUPLICATE)';
