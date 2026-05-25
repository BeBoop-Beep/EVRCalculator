# Evolving Skies Slot-Schema Pilot Audit (Project 6.0)

## Scope
Audit-first pilot for Evolving Skies (`swsh7`) under slot-schema scaffolding.

Guardrails preserved:
- `SIMULATION_ENGINE = slot_schema`
- `SLOT_SCHEMA_RUNTIME_ENABLED = False`
- no `RARE_SLOT_PROBABILITY`
- no changes to SV/Mega routing behavior
- no changes to Chilling Reign blocked status

## Pack Shape Confirmation (standard SWSH pre-SV)
- commons: 5
- uncommons: 3
- reverse slot: 1
- rare-or-better slot: 1
- modeled total: 10 cards

## Supabase Card/Variant Audit (swsh7)
Resolved set row id: `93212749-ce0e-498e-975e-7d947a3448ce`

Tables audited:
- `cards`
- `card_variants`
- `card_variant_price_observations`
- `card_market_usd_latest_by_condition`
- `simulation_input_cards`
- `simulation_input_cards_with_near_mint_price`

Row counts:
- cards: 237
- variants: 369
- latest market rows for set variants: 1403
- price observation rows sampled for set variants: 2000

Card-level rarity counts:
- Common: 42
- Uncommon: 51
- Rare: 19
- Holo Rare: 20
- Ultra Rare: 71
- Secret Rare: 34

Variant-level counts:
- printing_type: reverse-holo=132, holo=125, non-holo=112
- special_type: NULL=369
- edition: NULL=369

Other field findings:
- `card_number` present on all 237 cards
- `supertype` and `subtypes` not present in set card rows
- `set_name` not present in set card rows
- reverse representation is explicit via `printing_type = reverse-holo`

## Outcome-to-Pool Mapping Audit (swsh7)
Policy: exclude reverse-holo variants from rare-slot pools.

Coverage checks:
- eligible non-reverse rare-family variants: 144
- mapped by outcomes: 144
- unmapped: 0
- overlaps: 0

Outcome pool counts (card_count / variant_count):
- rare: 19 / 19
- holo rare: 20 / 20
- regular v: 18 / 18
- regular vmax: 15 / 15
- full art v: 22 / 22
- full art trainer: 5 / 5
- alternate art v: 11 / 11
- alternate art vmax: 6 / 6
- rainbow trainer: 5 / 5
- rainbow vmax: 11 / 11
- gold secret rare: 12 / 12

## Pull-Rate Source Audit Status
Source families reviewed:
- CharmanderHelps/X style rows: referenced as image-only datasets in Reddit links (not machine-readable rows in this audit)
- Reddit: image-linked posts found (`5000 packs`, `TCGPlayer 8000 packs`), no transcribed non-overlapping table extracted
- Cardzard: site endpoints returned store-unavailable / 404 during audit window
- DripShop: no stable machine-readable Evolving Skies row table discovered

Classification result:
- direct non-overlapping candidate rows: none extracted
- parent/sanity-only rows: none extracted
- named-card-only rows: none extracted
- unusable/overlapping rows: image-only references without transcribed structured rows

## Runtime Readiness Decision
Blocked for probability completeness:
- missing source-backed non-overlapping rare outcome mass
- missing source-backed non-overlapping holo rare outcome mass
- missing source-backed non-overlapping regular V outcome mass
- missing source-backed non-overlapping regular VMAX outcome mass

Decision:
- keep runtime disabled
- keep mapping inert for contract validation only
- do not add `RARE_SLOT_PROBABILITY`
