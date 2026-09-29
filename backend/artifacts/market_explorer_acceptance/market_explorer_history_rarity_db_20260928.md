# Market Explorer Historical / Rarity DB Acceptance — 2026-09-28

## Repository baseline

- Starting `develop`: `51cf0c265e3d8adccef78a17e52c924922c62457`
- Work branch: `fix/market-explorer-history-rarity-db-20260928-v2`
- No merge performed.
- Production project: `zwxzxuuawalvwioadhmf` (TheIndex)

## Production migrations in this closure

Existing production migrations carried onto the current-develop branch:
- `20260928202430_market_explorer_standard_history_raw_repair_v1.sql`
- `20260928202526_market_explorer_rarity_selection_semantics_v1.sql`
- `20260928202954_market_explorer_standard_history_invariant_guard_v1.sql`
- `20260928204424_market_explorer_root_standard_frozen_roster_v2.sql`
- `20260928204547_market_explorer_root_standard_current_refresh_v2.sql`
- `20260928204928_market_explorer_surface_v2_edition_stable_readiness.sql`

New production migration applied during final closure:
- `20260928213731_market_explorer_surface_v2_stable_raw_validation.sql`

The new migration changes candidate validation so Raw reconciliation is checked directly against
`pokemon_market_raw_edition_stable_daily_history_v1` and the staged `raw` directory/total/leaves.
It no longer requires the legacy generic-vintage `pokemon_market_explorer_raw_composition_runs_v1`
sidecar to pass the V2 Raw gate.

All seven migration files are mirrored under both `supabase/migrations` and `backend/db/migrations`.

## Standard historical repair

Canonical source used:
- `card_variant_price_events_v2` interval authority
- `card_variant_price_observation_ranges_v2`
- canonical card / legacy identity bindings
- `pokemon_market_root_set_value_daily_history_v2_shadow`

The V2 root history no longer shows temporary >=10% constituent-collapse / next-date-restoration events
for non-vintage Standard roots across the accepted Apr-23+ history: **0 detected**.

Known anomaly proof:

| Set | 2026-09-11 | 2026-09-25 |
| --- | --- | --- |
| Hidden Fates | 163/163, $3,727.38 | 163/163, $3,739.84 |
| Generations | 115/115, $1,863.75 | 115/115, $1,836.50 |
| Southern Islands | 18/18, $2,081.27 | 18/18, $2,150.75 |
| Legendary Treasures | 140/140, $2,208.29 | 140/140, $2,261.08 |
| Arceus | 111/111, $2,133.13 | 111/111, $2,211.95 |
| Supreme Victors | 153/153, $3,319.38 | 153/153, $3,468.92 |
| Platinum | 133/133, $1,800.33 | 133/133, $1,860.67 |
| Expedition Base Set | n/a in sampled Sep-11 row | 162/165, $9,210.87 |

The root V2 authority is now the Standard source used by edition-stable Raw (with the documented
subset-invariant fallback only where required).

Residual legacy-table note:
- `pokemon_set_value_daily_history` still has 9,790 historical Standard rows that differ from root V2
  across 145 roots after excluding subset-invariant-protected rows.
- A 20-root reconciliation attempt exceeded the operational runtime budget and rolled back.
- This residual table is **not** the primary Standard authority for edition-stable Raw, so the public Raw
  repair is not dependent on forcing this large rewrite.
- Leave this as bounded legacy cleanup rather than running a long all-history transaction on production.

## Vintage edition history

Edition identities remain separate. Generic vintage Standard markets are excluded from Raw.

Current scope summary (history starts 2026-04-07 where rows exist):

| Root / scope | Current reconstructed / expected | Certified dates | Publication note |
| --- | ---: | ---: | --- |
| Base First Edition | 92 / 102 | 0 | incomplete |
| Base Shadowless | 100 / 102 | 0 | incomplete |
| Base Unlimited | 102 / 102 | 2 | limited certified history |
| Fossil First Edition | 62 / 62 | 162 | certified |
| Fossil Unlimited | 62 / 62 | 148 | certified |
| Jungle First Edition | 64 / 64 | 162 | certified |
| Jungle Unlimited | 64 / 64 | 148 | certified |
| Gym Heroes First Edition | 132 / 132 | 162 | certified |
| Gym Heroes Unlimited | 132 / 132 | 148 | certified |
| Gym Challenge First Edition | 132 / 132 | 162 | certified |
| Gym Challenge Unlimited | 132 / 132 | 148 | certified |
| Neo Destiny First Edition | 112 / 113 | 0 | incomplete |
| Neo Destiny Unlimited | 113 / 113 | 152 | certified |
| Neo Discovery First Edition | 75 / 75 | 162 | withheld source review |
| Neo Discovery Unlimited | 75 / 75 | 148 | publishable/reviewed |
| Neo Genesis First Edition | 111 / 111 | 162 | withheld source review |
| Neo Genesis Unlimited | 111 / 111 | 148 | publishable |
| Neo Revelation First Edition | 65 / 66 | 0 | incomplete |
| Neo Revelation Unlimited | 65 / 66 | 0 | incomplete |
| Team Rocket First Edition | 83 / 83 | 162 | withheld source review |
| Team Rocket Unlimited | 83 / 83 | 148 | publishable |

Exact current unresolved identities at 2026-09-28:
- Base First Edition: Alakazam #1, Nidoking #11, Venusaur #15, Blastoise #2, Charizard #4,
  Clefairy #5, Gyarados #6, Hitmonchan #7, Super Energy Removal #79, Magneton #9 — bindings
  exist but current canonical interval price is absent.
- Base Shadowless: Raichu #14 and Chansey #3 — bindings exist but current canonical interval price is absent.
- Neo Destiny First Edition: Shining Noctowl #110 — no bound card variant.
- Neo Revelation First Edition: Shining Gyarados #65 — no bound card variant.
- Neo Revelation Unlimited: Shining Gyarados #65 — bound variant exists but canonical interval price is absent.

No cross-edition substitution or forward-fill was used.

## Edition-stable Raw before / after

| Date | Handoff defect | Repaired return | Current markets | Current cards | Membership explanation |
| --- | ---: | ---: | ---: | ---: | --- |
| 2026-09-11 | about -4.73% | +0.0843% | 106 | 14,171 | 106 common; no add/remove |
| 2026-09-12 | about +5.09% | +0.0133% | 118 | 15,333 | 106 common; 12 newly available stable markets |
| 2026-09-25 | about -2.98% | -0.0334% | 158 | 20,210 | stable common cohort; no temporary constituent collapse |

The known Hidden Fates / Generations / Southern Islands / Legendary Treasures collapses are absent in
the repaired source. Daily movement now comes from price movement within stable market identities,
plus explicit market additions when certified history legitimately begins.

Raw diagnostics:
- `editionStable=true`
- `vintageScopesSeparate=true`
- `legacyGenericVintageExcluded=true`
- Standard authority: `root_v2_with_subset_invariant_legacy_fallback`

## Rarity markets

Current registry:
- total canonical rarities: **39**
- executable: **39**
- blocked: **0**
- PREPARED: **9**
- CUSTOM_BUILD_AVAILABLE: **30**

The old 25-card / 3-set threshold no longer blocks selection. Small canonical rarities route through
the proven single-axis custom-build path; the threshold may still be used for analytical/prewarm
eligibility without turning the rarity into an unavailable option.

Rarity coverage certification is current through **2026-09-28**.

## Sep-28 publication closure

Final freshness:
- canonical accepted date: 2026-09-28
- edition-stable Raw: 2026-09-28
- Cards daily: 2026-09-28
- Sealed daily: 2026-09-28
- Sealed metadata: 2026-09-28
- rarity certification: 2026-09-28
- prepared V1: 2026-09-28
- V2 serving surface: 2026-09-28
- surface lag: **0 days**
- maintained caches: **37 / 37 current**
- freshness status: **CURRENT**

Serving generation:
- generation: `6bf499a0-75f4-4297-be9c-a78650c76bac`
- previous: `96740b15-88d7-455d-bf64-c9da57cf26ab`
- state: `VALIDATED`
- validation issues: **0**
- coherence: **COHERENT**
- Raw stable markets: **159**
- Raw roots: **155**
- Raw leaves: **20,313**
- sealed quick markets: **6**

The first Sep-28 candidate validation correctly failed because the validator was still requiring the
legacy generic-vintage Raw sidecar. Migration 20260928213731 changed the validator to the actual
edition-stable V2 authority; re-validation then returned zero issues and the candidate was promoted.

## Performance / safety

- Historical/current writes were performed sequentially.
- Frozen Standard roster convergence was already 146 / 146 ready before V2 staging.
- The monolithic V2 publisher was not repeatedly forced after it exceeded the connector/runtime window.
- Sep-28 was staged in bounded committed phases:
  - prepared seed: 30,903 history rows, 199 directory rows, 101,508 constituent rows
  - scoped overlays: 16 markets, 1,838 history rows, 1,533 constituents
  - Raw: 159 markets, 155 roots, 20,313 leaves
  - sealed lattice: 186 markets, 28,127 history rows, 5,954 constituents
  - sealed quicks: 6 markets, 1,046 history rows, 2,036 constituents
  - metrics: 379 markets updated
- No competing heavy writer was intentionally started while an advisory-locked repair/publication was active.

## Validation performed

Live production assertions:
- known Standard anomaly sets/counts/value checks: pass
- non-vintage root V2 collapse/restore scan: 0 findings
- vintage edition separation: pass
- no generic vintage Standard leakage in edition-stable Raw diagnostics: pass
- rarity executable options: 39 / 39
- frozen Sep-28 Standard Raw roots: 146 / 146 ready
- V2 candidate validation: VALIDATED, 0 issues
- V2 coherence assertion: COHERENT
- freshness: CURRENT, lag 0
- maintained caches: 37 / 37 current

Supabase security/performance advisors were run after the change. They continue to report broad
pre-existing project advisories (for example RLS-with-no-policy info findings and unindexed-FK info
findings); this validator-only migration adds no table, index, privilege, or SECURITY DEFINER change.

## Backend consumption contract

Backend/public readers should consume the serving V2 generation pointer and edition-stable Raw surface.
Do not require `pokemon_market_explorer_raw_composition_runs_v1` as proof that V2 Raw is valid; that
sidecar represents the legacy generic-vintage Raw model. Candidate validation now proves the V2 Raw
directory, totals, leaf count, leaf uniqueness, leaf value, and `editionStable` metadata directly
against `pokemon_market_raw_edition_stable_daily_history_v1`.

Rarity callers should treat both `PREPARED` and `CUSTOM_BUILD_AVAILABLE` as executable states.
