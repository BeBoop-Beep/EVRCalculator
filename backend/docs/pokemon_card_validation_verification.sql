-- Verify Pokemon card desirability validation snapshots after rebuild.
--
-- Rebuild commands:
-- python backend/scripts/build_pokemon_set_cards_snapshots.py --all --commit
-- python backend/scripts/build_pokemon_set_page_snapshots.py --all --commit
-- python backend/scripts/build_pokemon_market_dashboard_snapshots.py --all --commit --days 365 --window 365d

select
  s.name,
  s.canonical_key,
  jsonb_array_length(coalesce(c.payload_json->'cardDesirabilityValidation'->'cards', '[]'::jsonb)) as validation_cards,
  c.updated_at
from public.pokemon_set_cards_snapshot_latest c
join public.sets s on s.id = c.set_id
where s.canonical_key in ('ascendedHeroes', 'scarletViolet151', 'whiteFlare');

select
  card->>'name' as card_name,
  card->>'rarity' as rarity,
  card->>'marketPrice' as market_price,
  card->>'pokemonDesirabilityScore' as pokemon_desirability,
  card->>'adjustedCardAppealScore' as adjusted_appeal,
  card->>'isHitEligible' as hit_eligible
from public.pokemon_set_cards_snapshot_latest c
join public.sets s on s.id = c.set_id
cross join lateral jsonb_array_elements(c.payload_json->'cardDesirabilityValidation'->'cards') card
where s.canonical_key = 'ascendedHeroes'
limit 20;
