# Market Explorer Data Surface Expansion — DB Handoff — 2026-09-24

## Status

**SHADOW IMPLEMENTATION COMPLETE; PRODUCTION CUTOVER DEFERRED.**

Branch: `feat/market-explorer-data-surface-expansion-20260924`

Production was not mutated by this pass. Draft PR #357 (explicit vintage edition scopes) is still open and not merged into `develop`, so the new Explorer surface must not be promoted until the edition-scope prerequisite is landed and the production database is on that contract.

The connected Supabase project reports PostgreSQL 17.6 and ACTIVE_HEALTHY. Direct SQL through the Supabase connector timed out even for a trivial read during this session, so no claim below is presented as a fresh production SQL re-audit. PostgreSQL execution validation was therefore completed against the disposable PostgreSQL 17 CI database.

## A. Starting develop / branch state

- `develop`: `5ba004d05d8923ba8de474ade4d92bd3ca9015a5`
- Feature branch was created from that baseline and remains separate.
- No merge was performed.
- No frontend code was changed.

## B. Vintage prerequisite

PR #357, **Split vintage Set markets by physical edition scope**, remains open and unmerged.

The feature branch includes the already-developed explicit-scope DB migration as a prerequisite dependency. The scoped contract remains:
- Standard: `set:<set_id>`
- Explicit vintage: `set:<set_id>:<market_scope>`
- Supported non-standard scopes: `first_edition`, `unlimited`, and Base-only `shadowless`

The earlier DB authority audit recorded 167 expected Set-market rows after scope activation and 204 total prepared Explorer rows when combined with the then-current 37 non-Set rows.

## C–E. Raw Card parent

### Root cause
The Raw parent did not expose constituents because the Raw mathematical index is Set-level: `pokemon_market_index_daily_history` chains Set Value constituents. It is not mathematically built by directly chaining every physical card variant.

### Contract
New authorities:
- `pokemon_market_explorer_raw_composition_runs_v1`
- `pokemon_market_explorer_raw_composition_v1`
- `stage_pokemon_market_explorer_raw_composition_v1(...)`

The implementation preserves the existing Raw index. It separately builds a display **composition** roster of physical card leaves and marks the run READY only when:
1. the card-leaf basket sum reconciles exactly to the persisted Raw basket value (cent-rounded), and
2. leaf count reconciles to the persisted Raw card count.

The leaf identity is `card_variant_id` plus canonical/set/scope metadata. Explicit vintage scope metadata is carried so the repaired vintage contract cannot silently double-count physical editions.

**Semantic distinction:** Raw index constituents remain the Set-level chaining units; Raw composition constituents are the physical card leaves represented by the current parent basket.

## F–H. Prepared card image repair

Root cause: the compact prepared Set path stored item JSON without the image fields that were already available in normalized card metadata/variant/canonical authorities.

Canonical precedence implemented:
1. exact variant small
2. canonical small
3. exact variant large
4. canonical large
5. current metadata image
6. null

Function:
- `enrich_pokemon_market_explorer_prepared_constituent_images_v1(generation_id)`

The v2 candidate surface also writes the same image policy directly into card constituent item JSON.

Fresh live before/after percentages were not measured in this session because production SQL connectivity timed out and production was intentionally not changed.

## I–L. Full rarity taxonomy

Authority:
- `pokemon_market_explorer_rarity_registry_v1`
- `refresh_pokemon_market_explorer_rarity_registry_v1(market_date)`

Every taxonomy row is retained and gets a truthful state:
- `PREPARED`
- `CUSTOM_BUILD_AVAILABLE`
- `INSUFFICIENT_COHORT`
- `INSUFFICIENT_HISTORY`
- `UNAVAILABLE`

Current eligibility rule:
- existing maintained prepared market => PREPARED
- otherwise at least 25 currently priced cards
- at least 3 represented Sets
- at least 2 accepted historical dates
- history must reach audited Market Date
- positive current pricing

Candidate publication is generic; there is no Rare Holo GX special-case.

### Rare Holo GX
The original failure was architectural: it could be present in the full filter taxonomy while absent from the smaller maintained prepared rarity list. The new registry separates selectability from maintained/prepared eligibility and the v2 builder creates a rarity candidate for every eligible registry row.

PostgreSQL 17 acceptance specifically proves `rarity:rareHoloGx` is generated and searchable.

### Newly prepared rarity markets
No production rarity was newly promoted in this pass. The candidate builder stages every `CUSTOM_BUILD_AVAILABLE` rarity as `rarity:<rarity_key>`; exact live candidate names must be refreshed after #357 lands and live SQL connectivity is available.

## M–P. Normalized sealed authority

New normalized authorities:
- `pokemon_market_explorer_sealed_daily_v1`
- `pokemon_market_explorer_sealed_current_metadata_v1`
- `pokemon_market_explorer_sealed_type_registry_v1`

Classification version:
- `sealed-product-classification-v3-loose-pack-family`

Supported canonical families include:
- booster_box
- half_booster_box
- enhanced_booster_box
- elite_trainer_box
- pokemon_center_elite_trainer_box
- booster_bundle
- loose_booster_pack
- sleeved_booster_pack
- build_and_battle_box
- build_and_battle_stadium
- three_pack_blister
- single_pack_blister
- collection_product
- case
- display
- multi_product_bundle
- fun_pack
- other

Daily normalization chooses one deterministic positive USD observation per product/date (latest observation that day), carries source/provenance identifiers, and is indexed for product/Set/Era/family/date reads.

### Total Sealed membership
The existing retail parent definition is preserved. Bulk/container families are searchable/buildable/type-market eligible but are not silently included in Total Sealed. The acceptance fixture explicitly asserts a Case never enters `sealedMarket`.

## Q–T. Sealed prepared lattice

Candidate keys:
- Total: `sealedMarket`
- Set: `sealed-set:<set_id>`
- Era: `sealed-era:<era_id>`
- Type: `sealed-type:<product_family>`
- Intentional packs composite: `sealed-type:packs`

Set and Era markets are built directly from physical sealed product history, not from averages of Set indexes.

Type eligibility is registry-driven:
- existing legacy prepared => PREPARED
- no current priced inventory => UNAVAILABLE
- insufficient historical dates => INSUFFICIENT_HISTORY
- broad enough cross-Set cohort => PREPARED_CANDIDATE
- otherwise SEARCHABLE_BUILDABLE

The five legacy prepared-format identities are represented through generation-scoped aliases rather than duplicate history storage.

### Sealed Quick Markets
Registry exists, but all current candidate definitions remain `PROPOSED`; none is silently approved. This intentionally blocks arbitrary sealed price-tier definitions until distribution research/product approval exists.

## U–V. Unified contextual search / Graded

RPC:
`search_pokemon_market_explorer_catalog_v1(p_asset, p_query, p_limit)`

Bound:
- default 20
- maximum 50
- statement timeout 1 second

Result columns:
- asset
- result_kind
- label
- subtitle
- market_key
- instrument_id
- set_id
- era_id
- image_url
- availability
- metadata
- relevance

Cards can return:
- prepared market
- Set
- Era
- rarity
- specific card instrument

Sealed can return:
- prepared market
- Set-Sealed
- Era-Sealed
- sealed type
- specific sealed product

Sealed leaf search reads normalized current metadata, not truncated Set snapshot JSON.

Search uses bounded FTS/trigram/prefix-style authorities and never wildcard-scans history tables.

Graded is contract-compatible but fail-closed: one `INSUFFICIENT_AUTHORITY` result is returned rather than publishing fake production markets.

## W–Y. Prepared surface / history / constituents

New generation-pinned shadow surface:
- `pokemon_market_explorer_surface_generations_v2`
- `pokemon_market_explorer_surface_serving_v2`
- `pokemon_market_explorer_surface_directory_v2`
- `pokemon_market_explorer_surface_history_v2`
- `pokemon_market_explorer_surface_constituent_totals_v2`
- `pokemon_market_explorer_surface_constituents_v2`
- `pokemon_market_explorer_surface_aliases_v2`

Existing proven card Set/Era/Quick/Rarity data is copied into a candidate generation. New Raw composition, eligible rarity candidates, and the normalized sealed lattice are staged beside it.

History remains server-computed chain-linked history. No client financial computation is introduced.

Generic constituent paging RPC:
`get_pokemon_market_explorer_surface_constituents_v2(market_key, generation_id, after_rank, limit)`

Rules:
- limit 1..100
- rank-key paging
- generation mismatch fails closed
- no per-page recomputation
- no full JSON document parse

Card item contract includes:
- asset, instrumentId, cardVariantId, canonicalCardId, setId/setName
- name/cardName, cardNumber, rarity, edition, printingType, specialType
- marketPrice, priceAsOf
- imageUrl/imageSmallUrl/imageLargeUrl

Sealed item contract includes:
- asset, instrumentId, sealedProductId, setId/setName
- name/productName, variantLabel
- productFamily/productFamilyLabel
- marketPrice, priceAsOf
- imageUrl/imageSmallUrl/imageLargeUrl
- isBulkContainer

## Z. Query-engine changes

The new sealed build/search substrate uses normalized sealed daily/current authorities instead of the deliberately truncated Overview snapshot universe.

No existing query fingerprint is silently redefined in production by this branch because production was not promoted.

## AA. Indexes / performance

Persistent read indexes cover:
- directory generation + asset + scope
- directory Set and Era lookup
- history generation + market + date with included metrics
- constituent instrument lookup
- constituent generation + market + Set + rank
- sealed normalized Set/date
- sealed normalized Era/date
- sealed normalized family/date
- sealed current family/current-date
- sealed FTS
- sealed trigram

Publication staging uses indexed temporary tables for rarity and sealed chain construction.

Disposable PostgreSQL 17 smoke timings on the accepted fixture:
- directory read (25 rows): ~0.53 ms
- Rare Holo GX contextual search: ~1.94 ms
- sealed contextual search: ~2.60 ms
- Raw first constituent page (25 rows): ~0.65 ms

These are fixture smoke timings, not production SLO measurements. The code also enforces 1s search and 2s constituent-reader statement timeouts.

## AB. Migration files

Mirrored, byte-identical pairs:
- `20260924190000_explicit_vintage_market_scopes.sql`
- `20260924213000_market_explorer_data_surface_authorities_v1.sql`
- `20260924214500_market_explorer_generation_surface_v2.sql`
- `20260924220000_market_explorer_catalog_search_v1.sql`

Validation support:
- `.github/workflows/market-explorer-db-expansion-validation.yml`
- `backend/tests/unit/db/test_market_explorer_data_surface_expansion_migrations.py`
- `backend/tests/integration/fixtures/market_explorer_data_surface_expansion_fixture.sql`
- `backend/tests/integration/market_explorer_data_surface_expansion_acceptance.sql`

## AC–AD. PostgreSQL tests / candidate validation

Current-head CI on PostgreSQL 17:
- static contract tests: 12 passed
- source fixture install: passed
- all expansion migrations compile: passed
- end-to-end candidate acceptance: passed
- Pattern Overlay Guardrails: passed

Acceptance proves:
- reconciled Raw composition
- Rare Holo GX prepared candidate
- Total Sealed
- Case type market
- bulk-container exclusion from Total Sealed
- bounded Raw constituents
- Cards contextual search
- Sealed contextual search
- Graded fail-closed
- no unapproved Sealed Quick market
- Demand Pressure readiness only
- Fair Value readiness only
- generation mismatch fail-closed
- >100 constituent page fail-closed

## AE–AF. Cutover / rollback

Cutover after prerequisite:
1. merge/land explicit vintage edition repair
2. verify production migration state and live function definitions
3. apply additive authorities
4. refresh normalized registries/authorities
5. build candidate generation
6. run parity, coverage, reconciliation, and latency audits
7. validate candidate
8. atomically promote serving pointer

Rollback:
- preserve previous generation id in the serving pointer
- use `rollback_pokemon_market_explorer_surface_v2()`
- do not delete the old immutable generation during initial rollout

## AG–AH. Demand Pressure

Status: `DEMAND_PRESSURE_NOT_READY`.

Exact missing authority: legitimate completed-sale / sold-quantity observations with stable instrument identity, condition, currency, observation/sale timestamps, source, provenance/fingerprint, and enough coverage to support a preregistered validated signal.

Active asks/listings are explicitly not treated as sales.

## AI–AJ. Index Fair Value

Status: `INDEX_FAIR_VALUE_NOT_READY_FOR_PRODUCTION`.

Blockers:
- research must produce a model that passes frozen validation
- estimand/model version must be frozen
- production model-run authority required
- point-in-time card estimates with provenance required
- no-lookahead validation required
- market-level aggregation must use the exact focused market membership
- coverage/unavailable semantics must be defined and validated

No Fair Value production rows are created by this project.

## AK. Commercial comparison limit

No Index+/Premium active-market quota is encoded in the database.

Technical recommendation remains to enforce a product-decided active comparison limit in shared application/access constants and use DB quota state only if persisted Saved Markets/workspaces later require it.

## AL. Application contracts

Claude/application code should consume:
1. v2 surface directory for typed market identities.
2. v2 surface history for comparison series.
3. v2 constituent RPC for every active market that has composition.
4. `search_pokemon_market_explorer_catalog_v1` for asset-contextual search.
5. `get_pokemon_market_explorer_asset_options_v2` for rarity/type availability states and reasons.
6. generation id from the serving surface and pass it back on constituent paging.
7. stable instrument identities from constituent rows; do not reconstruct routes from labels.
8. availability/reason fields; never render an option as silently clickable-to-nothing.

Do not make the frontend know Set-vs-Era-vs-rarity-vs-sealed-type SQL details.

## AM. Branch / head

Branch: `feat/market-explorer-data-surface-expansion-20260924`

The exact final head is the commit containing this handoff document or a subsequent validation-only commit on the same branch.

## AN. Explicit deferrals

- production migration application / serving promotion until vintage prerequisite lands
- fresh production taxonomy/family counts while direct SQL connectivity is unavailable
- Sealed Quick Market product approval
- Demand Pressure production metric
- Fair Value production metric
- Graded production markets
- sealed image backfill where no trustworthy image authority exists
- commercial comparison quotas
- all React/UI work
- merge to develop


---

## 2026-09-25 continuation — live production re-audit and Raw composition correction

This section supersedes any earlier statement above that live SQL connectivity was unavailable.

### Production connectivity / outage result

The production database recovered and direct PostgreSQL validation resumed on PostgreSQL 17.6.

The preceding outage was project-origin wide rather than an Explorer-reader-only failure:
- hosted and production-VM Supavisor session/transaction routes failed,
- PostgREST returned sustained HTTP 522 origin timeouts,
- the last observed successful 2xx before the sustained outage was 2026-09-24 21:42:35 UTC,
- after recovery, the existing prepared readers returned to low-millisecond execution.

Live post-recovery execution:
- prepared serving directory: 193 rows in ~5.7 ms,
- Fossil v3 constituent first page (62 available rows, limit 100): ~7.6 ms,
- Rare Ultra v3 constituent page 2: ~5.0 ms.

The background-load hardening is already deployed to production:
- 15-second budget on the 15-minute Price Storage coordinator,
- advisory overlap guard,
- previous-month rollup bounded to one Set per invocation,
- bounded set-history coverage,
- indexed cheap history-presence RPC,
- supporting queue/scrape/monthly-claim indexes.

### Live serving state

The client-facing prepared surface is coherent:
- serving generation: `60c274ea-aed6-45b5-a701-ca0d29eb5f11`,
- serving directory rows: 193,
- serving Set markets: 156,
- serving sealed markets: 5,
- serving comparison watermark: 2026-09-22.

The mutable workspace directory may carry another generation; public directory reads use
`pokemon_market_explorer_prepared_serving_directory_v1`, so the v3 constituent reader and
directory are generation-aligned.

The explicit vintage scope contract and Explorer v2 surface are still not deployed to
production because PR #357 remains open/unmerged.

### Exact live image audit

Current serving compact constituent coverage:

| Asset | Market class | Rows | Rows with image | Coverage |
|---|---:|---:|---:|---:|
| Cards | Set | 19,978 | 0 | 0.00% |
| Cards | Era | 33,978 | 33,698 | 99.18% |
| Cards | Quick/curated | 40,753 | 40,461 | 99.28% |
| Cards | prepared rarity | 5,949 | 5,947 | 99.97% |
| Sealed | prepared format | 376 | 0 | 0.00% |

Required Set examples:
- Fossil: 62/62 prepared rows lack image JSON, while 62/62 have an authoritative exact-variant image.
- HeartGold & SoulSilver: 124/124 prepared rows lack image JSON, while 124/124 have authoritative images.
- Base Set 2: 130/130 prepared rows lack image JSON, while 130/130 have authoritative images.
- Rare Ultra: 778/778 prepared rows have images.
- Rare Secret: 324/324 prepared rows have images.

This proves the Set-image issue is a publication/staging omission rather than missing artwork.

### Exact live rarity result

Latest accepted Market Date audited: 2026-09-24.

Rare Holo GX:
- 159 currently priced cards,
- 15 represented Sets,
- 159/159 authoritative images,
- existing custom query-cache row is failed/not maintained.

The current nine maintained ready rarity caches are:
- Double Rare,
- Hyper Rare,
- Illustration Rare,
- Rare Holo,
- Rare Rainbow,
- Rare Secret,
- Rare Ultra,
- Special Illustration Rare,
- Ultra Rare.

The registry refresh was corrected so a legacy maintained prepared rarity remains
`PREPARED` even if a current audit fixture temporarily contains no members for that
rarity. The no-current-data cleanup no longer downgrades a row with an existing
`prepared_market_key`.

### Exact live sealed inventory

The normalized classifier audit found current positively-priced inventory in all of these
families through 2026-09-24:

- Collection Product: 395
- Other: 310
- Case: 193
- Single-Pack Blister: 165
- Multi-Product Bundle: 164
- Loose Booster Pack: 139
- Elite Trainer Box: 78
- Three-Pack Blister: 77
- Booster Box: 55
- Display: 50
- Sleeved Booster Pack: 46
- Pokémon Center Elite Trainer Box: 40
- Booster Bundle: 36
- Fun Pack: 14
- Half Booster Box: 9
- Enhanced Booster Box: 2

The sealed product image columns yielded zero authoritative images in this audit, so null
image output remains correct for sealed until a trustworthy image source is added.

### Graded

Production coverage is exactly:
- 1 graded variant,
- 1 latest market row,
- 1 price observation.

`INSUFFICIENT_AUTHORITY` remains the correct production result.

### Raw composition correction

The first shadow Raw leaf strategy was rejected by live parity testing.

Broad eligible current variants produced:
- 33,965 leaves,
- $662,255.71,
versus persisted Raw 2026-09-24:
- 19,978 cards,
- $445,570.05.

Other live/current authorities were also proven insufficient as an exact frozen Raw leaf
source because membership or price timing can drift from the specific Set Value
publication.

The database contract is therefore corrected with a publication-time frozen Set Value
leaf authority:

- `pokemon_market_set_value_constituent_publications_v1`
- `pokemon_market_set_value_constituents_v1`
- `replace_pokemon_market_set_value_constituents_v1(...)`

New migration:
- `20260925061000_market_explorer_raw_frozen_set_value_constituents_v1.sql`

The Set Value application publisher must call the replacement RPC with the exact
canonical-card -> physical-variant rows it already computed for that root/date/methodology.
The RPC validates exact card count and Set Value before marking the roster READY.

Raw composition now:
1. reads the persisted Raw Set-level index row,
2. requires one matching READY frozen leaf publication for every Raw root,
3. unions only those frozen leaf rows,
4. checks global physical identity uniqueness through table constraints,
5. reconciles exact leaf count and basket value to Raw,
6. fails closed otherwise.

It no longer scans the full current card-variant universe and no longer invokes the
per-Set canonical price RPC 156/167 times during generation.

### Current PostgreSQL 17 validation

Current branch head at this audit:
`8967d99cbbd8ee5f3cae3b9f1a34a26fb90269b0`

Current-head workflows:
- Pattern Overlay Guardrails: SUCCESS
- Market Explorer DB Expansion Validation: SUCCESS

DB validation includes:
- 22 static contract tests passed,
- all expansion migrations compile on PostgreSQL 17,
- frozen Raw leaf publication + exact reconciliation acceptance,
- maintained-rarity preservation,
- Rare Holo GX candidate,
- normalized sealed lattice,
- Case exclusion from Total Sealed,
- contextual search,
- Graded fail-closed,
- generation mismatch/page-limit guards,
- DB-load hardening compile and bounded-maintenance execution.

Current fixture read smoke:
- directory: ~0.59 ms,
- rarity search: ~2.05 ms,
- sealed search: ~2.90 ms,
- Raw first page: ~0.70 ms.

### Additional application handoff requirement

Before a production v2 candidate can make Raw composition available, the Set Value
publisher must persist the exact leaf roster at the same time it publishes the Set Value.

This is not a frontend responsibility. The publisher already has the selected rows in
memory; it must pass them to
`replace_pokemon_market_set_value_constituents_v1(...)`.

Historical Raw composition for dates that predate this authority remains fail-closed
unless exact historical leaf membership is independently reconstructed and certified.
No latest/current roster may be stamped onto an older Raw date.

### Remaining production gate

Do not apply/promote the vintage-dependent Explorer expansion while PR #357 remains
open.

After the vintage prerequisite lands:
1. apply the additive Explorer migrations including the frozen Set Value leaf authority,
2. update the Set Value application publisher to persist exact leaf rosters,
3. generate the next Set Value/Raw publication with those frozen rosters,
4. refresh rarity/sealed authorities,
5. build the v2 Explorer candidate,
6. run full live parity/image/search/latency acceptance,
7. atomically promote the v2 serving pointer only if all gates pass.

No merge or frontend work is performed by this DB handoff.
