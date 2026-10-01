# Treatment Panel Recovery V2 — PkmnPrices Historical NM

Status: `PILOT_FROZEN_PRECOLLECTION`

## Why this exists

Treatment Hierarchy V1 stopped at Phase 1 because Round 24 had only 5 panel-ready matched-treatment ladders out of 15,989. The missing requirement was exact condition-aligned shared historical dates.

The ongoing PkmnPrices sold-comps backfill does not repair that Round-24 authority: it writes sold evidence, while Round 24 required exact Near-Mint historical market-price panels. PkmnPrices exposes a separate `/v1/cards/:id/prices/history` endpoint with TCGPlayer daily aggregates by exact condition and variant. This recovery study uses that endpoint as a research-only panel source.

## Frozen pilot

The pilot is deliberately small: 16 matched identities / 36 canonical cards across 7 Sets, all inside the 22-Set simulation-supported cohort.

Families:

- Double Rare vs Special Illustration Rare vs Ultra Rare:
  - Surging Sparks
  - Scarlet and Violet 151
- Common vs Illustration Rare:
  - Shrouded Fable
  - White Flare
- Illustration Rare vs Uncommon:
  - Black Bolt
  - Paldea Evolved
- Double Rare vs Ultra Rare:
  - Paradox Rift
  - Surging Sparks

Each Set/family contributes exactly two frozen matched identities. This is enough to exercise the preregistered two-identities-per-Set and two-Sets-per-era hierarchy gates without mapping thousands of unrelated cards.

## Price-history contract

- source: PkmnPrices TCGPlayer USD history
- condition: exact `Near Mint`
- horizon: 180 days
- variant: exact provider printing variant
- aggregation used: daily `avg`
- no interpolation
- no nearest-date substitution
- no forward fill
- no canonical price writes
- no Supabase writes of any kind

The maximum history-row cost is 6,480 rows. The run has a hard research cap of 7,500 provider credits to leave room for identity and card-variant verification.

## Variant policy

For low rarity cards (Common / Uncommon / Rare), use the ordinary `Normal` printing when it exists. Reverse Holofoil is not substituted into a rarity-designation comparison.

For premium rarity cards, use the ordinary `Holofoil` printing when it exists.

Any special treatment, edition, or provider-variant ambiguity blocks that card instead of guessing.

## Runtime isolation

The collector is read-only against Supabase. Missing PkmnPrices identities are resolved in memory and written only to the local research artifact.

The workflow shares `/tmp/pkmnprices-api.lock` with the active PkmnPrices pipeline and also checks for a live B5 database run. If either indicates the provider budget is owned elsewhere, collection is deferred with zero provider calls.

## Decision

The first run does not fit a Treatment model.

It only asks whether the frozen pilot now has enough exact shared NM dates to reopen Treatment Hierarchy V1 Phase 2.

Round-24 thresholds remain unchanged:

- Tier 1 strong: >=90 exact shared dates
- Tier 1 moderate: >=30
- Tier 2/3 moderate: >=90
- at least 2 ready identities per Set/family
- at least 2 passing Sets in the same era/family before era hierarchy work resumes

No gate may be relaxed after collection.
