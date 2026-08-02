# Pokémon Sealed Market snapshots

This first phase publishes unopened-product market-price history, not complete
Product Economics. It does not assign value to ETB promos, contents,
accessories, or opening EV.

Raw data remains in `sealed_products`,
`sealed_product_price_observations`, and the canonical
`sealed_product_market_usd_latest` view. Names are never mutated. The versioned
backend classifier recognizes retail product families and independently keeps
standard ETB, Pokémon Center ETB, and bracketed variants. Overview eligibility
is limited to booster boxes, enhanced booster boxes, standard and Pokémon
Center ETBs, booster bundles, booster packs, and sleeved packs. Cases,
displays, sets, art bundles, blisters, collection products, and unknown
listings remain in the catalog but are excluded.

The builder selects one latest observation per product/day without averaging
sources or interpolation, rejects invalid/non-positive USD prices, and prepares
7D, 30D, 3M, and LT comparisons. LT means all stored history. A missing
on-or-before baseline is explicitly unavailable. Chart history is bounded to
365 points while retaining the first stored point.

`pokemon_set_sealed_market_snapshot_latest` is refreshed solely from sealed
product membership and price ingestion. It has no simulation, RIP, card,
set-value, or opening-profit dependency. Public
`GET /tcgs/pokemon/sets/{set_id}/market/sealed` reads only that snapshot; the
Next proxy and browser client are read-only and fetch once per set. Missing
snapshots return 404, and the Overview module fails independently.

Build commands:

```powershell
python backend/scripts/build_pokemon_set_sealed_market_snapshots.py --set-id paradox-rift --dry-run
python backend/scripts/build_pokemon_set_sealed_market_snapshots.py --set-id paradox-rift --commit
python backend/scripts/build_pokemon_set_sealed_market_snapshots.py --all --dry-run
python backend/scripts/build_pokemon_set_sealed_market_snapshots.py --all --commit
```

Phase 2 can add explicit product-component and promo mappings before presenting
promo value or opening economics.
