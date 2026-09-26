create index idx_pokemon_market_explorer_card_filter_rarity_v1
  on public.pokemon_market_explorer_card_current_metadata
  using btree (
    public.market_explorer_filter_rarity_key(rarity),
    set_id,
    card_variant_id
  )
  include (canonical_card_id);

analyze public.pokemon_market_explorer_card_current_metadata;
