# Vintage Market DB Authority Audit — 2026-09-24

## Status

**DB design + real PostgreSQL validation complete; production not changed. Scoped cutover still waits on the application count/audit contract and explicit production authorization.**

Branch: `fix/market-vintage-db-authority-20260924`

Audit starting points:
- `develop`: `5ba004d05d8923ba8de474ade4d92bd3ca9015a5`
- DB branch before this final validation pass: `91bdb42d59f33ebdca186b767ee4183ee35aafb6`
- application branch / draft PR #357: `6431128987763504eeb77a5d19d6ec4679654493`

Both repair branches were verified 0 commits behind `develop` at audit time. PR #357 remains unmerged.

This branch is a DB-only replacement for the database portion of draft PR #357.  It does not merge the coordinator prototype and does not modify React or ordinary Python service code.

## A. Live schema audit

The durable market identity is:

- Standard: `set:<set_id>`
- Edition market: `set:<set_id>:<market_scope>`

Authoritative non-standard scopes remain the taxonomy already established by `20260904173530_canonical_market_root_set_universe_v1.sql`: `first_edition`, `unlimited`, and Base-only `shadowless`.

Live production contains exactly 10 edition-split roots and no additional ones.

| Root | set_id | Profile | Current scope authority |
|---|---|---|---|
| Base | 0010d2ec-894e-4c17-855d-5de6ff6fd204 | base_three_printings | first $28.71 / 0.98%; shadowless $0 / 0%; unlimited $0 / 0% — all unavailable |
| Fossil | c86889c9-ea25-4caa-b63c-7aa0b9796da8 | edition_split | first $3,357.16 / 100%; unlimited $1,210.99 / 100% |
| Gym Challenge | 497a77be-f0e9-4dda-bbdb-b561bc91f3b2 | edition_split | first $6,581.39 / 100%; unlimited $3,162.74 / 100% |
| Gym Heroes | 537d3312-9622-4015-9ef2-66e16a27287c | edition_split | first $4,554.87 / 100%; unlimited $2,045.64 / 100% |
| Jungle | 37e1b616-c5f4-4279-83c4-ea8dcdd83c69 | edition_split | first $3,107.25 / 100%; unlimited $1,097.63 / 100% |
| Neo Destiny | 42a3740d-4778-4857-9c28-e116f34b51f3 | edition_split | first $17,056.40 / 99.12% unavailable; unlimited $13,241.70 / 100% |
| Neo Discovery | a5e6c9df-5a1b-4ab9-92ef-9fac0984c8d2 | edition_split | first $3,615.77 / 100%; unlimited $2,393.35 / 100% |
| Neo Genesis | 3562f9c9-f879-4d49-9d69-d0ab511230f9 | edition_split | first $4,181.21 / 100%; unlimited $2,106.34 / 100% |
| Neo Revelation | 89e710d1-c378-4b4e-aaea-5994d8441f45 | edition_split | first $4,686.37 / 98.48% unavailable; unlimited $2,674.84 / 98.48% unavailable |
| Team Rocket | 4f84d317-e15d-4598-bc8d-52baa04b3485 | edition_split | first $3,624.66 / 100%; unlimited $1,966.60 / 100% |

Base is intentionally explicit-but-unavailable; no edition value is invented.

### Certified scoped history

All published certified scope history currently ends on the latest approved Market Date, 2026-09-22.

- Fossil, Gym Challenge, Gym Heroes, Jungle: first edition 2026-04-11..2026-09-22 (157 certified dates); unlimited 2026-04-25..2026-09-22 (143).
- Neo Destiny: unlimited 2026-04-21..2026-09-22 (147); first edition has zero certified dates.
- Neo Discovery: first edition 157 raw certified dates and unlimited 143. New publication withholds the first-edition history because of source defects.
- Neo Genesis: first edition 157 raw certified dates and unlimited 143. New publication withholds the first-edition history because of source defects.
- Neo Revelation: zero certified dates for both scopes.
- Team Rocket: first edition 157 raw certified dates and unlimited 143. New publication withholds the first-edition history because of source defects.
- Base: zero certified dates for all three scopes.

## B. Affected blended-history cohort

Observed first physical-variant flip in the old generic constituent authority:

- Neo Destiny: 2026-04-22.
- Jungle, Fossil, Team Rocket, Gym Heroes, Gym Challenge, Neo Genesis, Neo Discovery, Neo Revelation: 2026-04-25.
- Base: no physical flip observed from 2026-04-11 through 2026-09-22, but its edition identity coverage is too incomplete to treat generic history as an edition authority.

The repair does **not** rewrite modern unaffected history.  New prepared publication ignores the generic blended history for edition-split roots and consumes the canonical scope histories only from genuine certified coverage dates.

## C. PR #357 prototype audit

Accepted concepts:

1. Explicit `set:<id>:<scope>` machine keys.
2. No generic `set:<id>` market for an edition-split root after activation.
3. `marketScope`, `baseSetName`, and scope-contract metadata in the prepared directory.
4. Stale generic-key deletion logic.
5. Direct Set Value normalization for an edition scope **only after fixed-basket proof**.

Rejected/replaced pieces:

1. The prototype mixed DB, Python and frontend work; this DB branch does not inherit non-DB files.
2. Prototype constituent staging used `get_pokemon_market_root_set_card_prices_latest_v1` and stamped those latest prices with an older generation date.  Replaced with a date-pinned scoped constituent RPC.
3. Prototype had no fixed-basket guard.  Added validation for one physical variant per canonical+scope and constant certified expected-card membership.
4. Prototype had no exact payload-to-authoritative-scope validator.
5. Prototype silently accepted large scoped source anomalies.  Added an explicit review ledger and fail-closed history withholding.
6. Prototype treated the lightweight workspace sync as if it were the serving generation.  Live generation architecture proves the current sync is workspace-only once the serving pointer references an immutable generation; serving scope cutover therefore requires a full guarded generation promotion.

## D. Market Index proof

Current live metadata has **zero** cases with more than one physical `card_variant_id` for the same `(canonical_card_id, market_scope)`.

For every one of the 15 scoped markets with certified history, every certified date was rebuilt from that fixed physical variant map against `pokemon_market_price_intervals_v2_shadow`.

Result:

- priced-count mismatches: **0**
- Set Value mismatches: **0**
- maximum absolute Set Value difference: **$0.00**

Therefore, while the fail-closed invariants hold, `100 * SetValue(t) / SetValue(base)` is mathematically the same fixed-basket price index that a common-cohort chain would produce.  The migration validates those invariants before scoped history is used.

## E. Residual large-move review

The source review found nine certified scoped moves at or above 10%, plus the handoff's ~10% Fossil residual.

### Withheld as SOURCE_DEFECT

- Neo Discovery / first edition / 2026-05-10: -19.48%, Umbreon NM 1799.99 -> 974.47 while LP remained 1500.
- Neo Discovery / first edition / 2026-05-14: +23.78%, Umbreon snapped 974.47 -> 1799.99 with unchanged LP.
- Neo Discovery / first edition / 2026-05-18: -19.11%, Umbreon 1799.99 -> 982.97 with LP 1500.
- Neo Discovery / first edition / 2026-05-21: -23.74%, Umbreon 982.97 -> 165.95 with LP 1500.
- Neo Genesis / first edition / 2026-05-12: -10.25%, Lugia NM 165.50 while LP/MP/HP/DMG were 1299.96/1034.34/751/600.
- Team Rocket / first edition / 2026-05-23: -14.45%, Dark Charizard NM 707.16 -> 247.15 while LP/MP/HP remained 493.06/390.80/303.20.

These three market histories are withheld as a whole from the new prepared generation until corrected source authority exists. Current values and current scoped constituents can still publish when current coverage is valid.

### Explicitly accepted reviews

- Neo Discovery / first edition / 2026-08-19: +12.02%, `STALE_TO_FRESH_REPRICE`; fresh NM coverage resumed for Umbreon and Ursaring and persisted.
- Neo Genesis / first edition / 2026-08-02: +18.99%, `STALE_TO_FRESH_REPRICE`; Typhlosion NM resumed at 699.99 after an NM gap, with persistent observations.
- Neo Discovery / unlimited / 2026-08-31: +12.23%, `REAL_PRICE_MOVE`; Umbreon NM 500 -> 752.74 and persisted.
- Fossil / first edition / 2026-07-29: +9.96%, `REAL_PRICE_MOVE`; Gengar NM 315.25 -> 601.49 and persisted.

## F. Shadow count / publication result

Current `/Market` root cohort: **156 root Sets**.

Expected explicit market rows:

- Standard: **146**
- Vintage scoped: **21**
- Total Set markets: **167**
- Unique market keys: **167**
- Forbidden generic vintage rows: **0**

Of the 21 vintage scope identities:

- current publishable: **15**
- unavailable/incomplete: **6**
- current + history publishable after source review: **12**
- current only / history withheld for source defect: **3**

Current non-Set Explorer rows: **37**.

Expected prepared Explorer directory after full scoped generation: **204 total rows** = 167 Set markets + 37 non-Set markets.

## G. `set_count` semantics

Final compatibility contract:

- `pokemon_explore_set_value_snapshot_latest.set_count` = **distinct root Sets represented**.
- `pokemon_explore_set_value_snapshot_latest.market_count` = **published Set-market identities in `payload_json.sets`**.
- `market_count` is database-maintained from `jsonb_array_length(payload_json->'sets')`.
- A CHECK constraint requires `market_count == payload row count` and `market_count >= set_count`.
- For the current scoped cohort the expected row is **set_count=156, market_count=167**.

This is intentionally different from the earlier draft conclusion that `set_count` should become 167. Keeping `set_count` as roots preserves the long-standing semantic used by Market Date Quality, historical repair gates, human alerts and the raw/top10 Market Index cohort. The new `market_count` makes the larger explicit market cardinality first-class without calling 167 markets “167 Sets.”

The migration also installs a BEFORE INSERT/UPDATE-of-payload trigger that derives `market_count`. This allows the DB migration to deploy before application code learns the new column; the current singleton writer can omit `market_count` without failing a NOT NULL insert/upsert.

### Consumer matrix

| Consumer | Current assumption | Final semantic / action |
|---|---|---|
| `backend/db/services/pokemon_explore_set_value_service.py` | writes `set_count=len(published)` | **MUST CHANGE**: `set_count=len(distinct setId)`; may also emit `market_count=len(published)` although DB derives it |
| `backend/scripts/audit_pokemon_market_publication.py` | `set_count == len(payload sets)`; rejects duplicate `setId` | **MUST CHANGE**: root `set_count == distinct setId`; `market_count == payload rows`; uniqueness by `marketKey` |
| `backend/tests/unit/scripts/test_audit_pokemon_market_publication.py` | old one-row-per-set assumption | **MUST CHANGE** with audit contract |
| `backend/tests/unit/scripts/test_run_daily_opening_publication.py` | fixtures reflect old snapshot shape | update fixtures/selects if they materialize the Global Set Market row |
| live `refresh_pokemon_market_explorer_prepared_directory_v1` | prepared Set rows compared with snapshot `set_count` | migration patches comparison to **market_count** |
| live `sync_pokemon_market_explorer_set_directory_v1` | payload length + directory rows compared with `set_count` | migration uses **market_count** and returns both snapshotSetCount/snapshotMarketCount |
| live snapshot->Explorer trigger | watches set_count + payload | migration also watches **market_count** |
| `backend/alerts/pipeline_alerts.py::alert_global_market` | displays “Sets: set_count” | no semantic change; now correctly remains root Sets |
| `backend/scripts/refresh_stale_public_snapshots.py` | passes candidate set_count to alert | follows corrected writer; no separate DB change |
| `backend/db/services/post_scrape_publication_trigger.py` | uses table as global date authority, not count | unaffected |
| `backend/scripts/audit_pokemon_market_index_publication.py` | direct snapshot read is payload/overview; other set_count fields belong to Market Index rows | unaffected |
| `pokemon_market_date_quality.cohort_set_count` | root cohort | **unchanged** |
| `pokemon_market_index_daily_history.set_count` raw/top10 | root/cohort count | **unchanged** |
| `20260911200916_market_explorer_phase5_refresh_prepared_directory.sql` + backend mirror | historical definition uses set_count as Set rows | already-applied migration remains immutable; forward migration supersedes live function |
| `20260914190614_sync_explorer_directory_with_global_set_market.sql` + mirror | older sync generation | immutable history; superseded |
| `20260914211525_lightweight_explorer_set_directory_sync.sql` + mirror | latest pre-repair sync equates set_count with payload rows | immutable history; forward migration replaces live function |
| `063_create_pokemon_explore_set_value_snapshot.sql` | original table has only set_count | immutable schema history; forward migration adds market_count |
| `.github/workflows/sep22-market-publication-repair.yml` | asserts snapshot set_count=156 | remains semantically correct as a historical root-count assertion |
| `.github/workflows/repair-sep22-market-publication.yml` | reads snapshot set_count | remains root-count semantic |
| `.github/workflows/repair-30th-market-publication-20260922.yml` | asserts snapshot set_count=156 | remains semantically correct for its historical root cohort |
| `.github/workflows/backfill-30th-celebration-metadata-20260922.yml` | asserts snapshot set_count=156; separately checks Market Index counts | remains correct; do not change Market Index cohort semantics |
| `backend/docs/POKEMON_MARKET_DATE_RECOVERY_RUNBOOK.md` | “Set count” means root cohort | remains root-count language |
| `backend/docs/public_snapshot_refresh_strategy.md` / acceptance docs | historical one-market-per-set wording | documentation should be updated when scoped cutover ships; no runtime gate |

The GitHub code sweep found 23 direct table/set_count references; the rows above cover all runtime, migration-mirror, test, workflow and documentation hits. No unrelated RIP/simulation count was redefined.

## H. Lightweight sync / generation architecture

Live serving uses `pokemon_market_explorer_prepared_serving_v1` to point at an immutable generation.  The active serving generation observed during this audit was `60c274ea-aed6-45b5-a701-ca0d29eb5f11` (comparison 2026-09-22).

`sync_pokemon_market_explorer_set_directory_v1` currently mutates only `pokemon_market_explorer_prepared_directory_v1`, not `*_directory_generations_v1` and not the serving pointer.  Therefore its explicit-scope update is retained as a correct workspace mirror, but it is **not accepted as the serving cutover mechanism** under the current architecture.

A scoped public serving cutover must use `run_market_explorer_guarded_publisher_v1(required_market_date)`, which rebuilds and promotes a new immutable generation.  Old generations remain untouched.

## I. DB migration branch

Files:

- `backend/db/migrations/20260924190000_explicit_vintage_market_scopes.sql`
- `supabase/migrations/20260924190000_explicit_vintage_market_scopes.sql`
- `supabase/tests/explicit_vintage_market_scopes.sql`

The two migration trees are byte-identical.

Final migration additions/replacements include:

- profile-driven `pokemon_market_set_scope_contract_v1`: edition market **existence** is derived from `pokemon_edition_split_root_sets_v2.profile`, not from today's certification row;
- missing current scope valuation rows remain explicit with null public value / `scope_authority_missing`;
- `market_count` on the Global Set Market snapshot, DB-maintained from the payload;
- exact market_count CHECK + count-aware snapshot trigger;
- `validate_pokemon_market_set_scope_payload_v1(payload, declared_market_count, declared_root_set_count)`;
- `validate_pokemon_market_scoped_history_baskets_v1`;
- `get_pokemon_market_root_set_card_prices_as_of_v1`;
- `pokemon_market_scoped_history_large_move_reviews_v1`;
- `pokemon_market_scoped_history_market_certification_v1`;
- explicit-scope prepared directory/history logic;
- explicit-scope lightweight workspace sync;
- date-pinned scoped constituent staging with exact certified-roster validation.

Security: fixed search paths, service-role-only internal sync, RLS/default-deny/no public writes on the review ledger, bounded timeouts, no generated UUID literals. Advisor verification shows anon/authenticated **cannot** execute the SECURITY DEFINER directory sync; service_role can.

The migration dynamically patches only the marked Set/history/constituent sections of the deployed refresh/staging functions. Live marker checks passed. The constituent advisory lock and guarded publisher `already_current` shortcut are outside the patches and remain intact.

## J. Required tests

SQL suite now asserts:

- Standard root -> one Standard market.
- edition_split profile -> first_edition + unlimited, independent of current valuation availability.
- Base profile -> first_edition + shadowless + unlimited.
- no generic edition-split key.
- unique stable market_key.
- fixed physical identity per canonical+scope.
- constant complete certified basket.
- Base fail-closed behavior.
- known source-defect histories withheld.
- `market_count` exists, is NOT NULL and is payload-derived.
- root set_count / market_count split validates against the authoritative scope contract.
- count normalizer trigger and exact payload equality constraint exist.
- scoped directory sync is not executable by anon/authenticated.
- post-activation prepared Set directory count equals snapshot market_count.
- prepared scope metadata.
- no generic vintage prepared row.
- date/scope-consistent prepared constituents.
- withheld history absent.
- v3 constituent serving function preserved.

### Real PostgreSQL result

A disposable Supabase Postgres 17 validation branch was created and used as a compiler harness because the project's preview branch did not bootstrap the production schema from repository migrations. The harness loaded the **exact deployed** definitions of:

- `refresh_pokemon_market_explorer_prepared_directory_v1()`
- `stage_pokemon_market_explorer_prepared_constituents_v1(uuid)`

plus minimal typed relation stubs.

Results:

- full migration revision with live dynamic-function markers: **PASS** on Postgres 17;
- SQL suite with deterministic Standard/Base/edition-split/source-defect fixture: **PASS**;
- profile-existence destructive-in-transaction probe (remove a current valuation row; identity must survive unavailable): **PASS**;
- legacy-writer compatibility probe (omit market_count; DB derives it): **PASS**;
- payload changes 1 -> 2 markets while root set_count stays 1: **PASS**;
- security advisor: public SECURITY DEFINER execute finding removed after explicit revoke;
- direct privilege probe: anon sync execute=false, authenticated=false, service_role=true; review-ledger anon/auth read=false, service_role CRUD=true.

The remaining advisor warnings are harness artifacts (stub tables without PKs and the minimal stub for an existing function); the review ledger's RLS-with-no-policy notice is intentional default-deny defense in depth.

## K. Rollback

No destructive down migration is planned.

Before cutover, capture the current serving generation id and the current global Set Market snapshot row.

If the new generation fails validation:

1. call `rollback_pokemon_market_explorer_prepared_generation_v1(previous_generation_id, operator_path)`;
2. restore the captured prior global Set Market snapshot if the scoped snapshot had already been committed;
3. deploy a forward corrective migration.

Immutable prior generation rows are not mutated by this migration.

## L. Production sequence

Strict cutover order:

1. Application code adopts the final count contract: root `set_count`, market `market_count`, and `marketKey` uniqueness.
2. Rebase/reconcile the DB and application branches onto current `develop` without merging PR #357.
3. Apply the DB migration to production.
4. Verify catalog/function signatures, grants, snapshot market_count backfill, live patch markers, and unchanged `run_market_explorer_guarded_publisher_v1` already_current behavior.
5. Resolve the required approved Market Date from `pokemon_market_date_quality` (currently 2026-09-22). Do **not** substitute latest component observations; scoped current/history/constituents must all be date-pinned to the approved date.
6. Dry-run the scoped Global Set Market snapshot and require:
   - set_count = 156 roots;
   - market_count = 167 market identities;
   - 167 unique marketKeys;
   - 0 generic edition-split keys;
   - 6 unavailable identities present with null public value, not $0.
7. Capture the pre-cutover Global Set Market snapshot row and current serving generation id `60c274ea-aed6-45b5-a701-ca0d29eb5f11`.
8. Commit the scoped Global Set Market snapshot.
9. Run `run_market_explorer_guarded_publisher_v1(required_market_date)` to build/stage/validate/promote a new immutable generation. Do **not** use lightweight directory sync as the serving cutover.
10. Require 167 Set markets + 37 unchanged non-Set markets = 204 directory rows, one comparison watermark, exact scope constituents, and no history for withheld markets.
11. Validate v3 pagination, five sealed markets, Eras, curated Quick Markets and rarity markets are unchanged.
12. Validate public API/application reads, then browser-check /Market and /Market/Explorer.
13. Retain the prior generation and snapshot until post-cutover acceptance is complete.

Latest root-scope observations can advance beyond the approved Market Date. On 2026-09-24, scope component dates reached 2026-09-24 while the latest approved Market Date remained 2026-09-22. The September-22 fixed-identity reconstruction matched certified September-22 scoped history at **$0.00 difference** for every certified scope; this is the publication value source until a newer date is approved.

## M. Operations still requiring explicit authorization

No production database write has been performed.

The temporary paid Supabase validation branch was used only for isolated Postgres validation and should be deleted after this handoff is frozen.

Still requiring explicit user authorization:

1. applying `20260924190000_explicit_vintage_market_scopes.sql` to production;
2. committing the scoped Global Set Market production snapshot;
3. running/promoting the new guarded prepared Explorer generation;
4. any historical source-data correction for the three withheld first-edition histories.

No destructive rewrite of the old mixed generic histories is required. They can remain archived/non-serving for rollback and forensics.

## N. Live 21-scope shadow matrix

All history/index values below are pinned to the latest approved Market Date, **2026-09-22**. “Variants” is the fixed physical variant authority count; every row has **0 wrong-edition variants and 0 duplicate canonical+scope identities**.

| Market | Status | Coverage | Sep-22 value | History | Index | Max | Variants | Prepared history |
|---|---:|---:|---:|---|---:|---:|---:|---|
| Base - 1st Edition | unavailable | 0.98% | — | 0 | — | — | 1/102 | unavailable |
| Base - Shadowless | unavailable | 0% | — | 0 | — | — | 0/102 | unavailable |
| Base - Unlimited | unavailable | 0% | — | 0 | — | — | 0/102 | unavailable |
| Fossil - 1st Edition | current | 100% | $3,339.27 | 157, 04-11..09-22 | 129.531490 | 9.9596% | 62/62 | ready |
| Fossil - Unlimited | current | 100% | $1,205.56 | 143, 04-25..09-22 | 120.813332 | 1.3029% | 62/62 | ready |
| Gym Challenge - 1st Edition | current | 100% | $6,576.93 | 157 | 117.221829 | 9.1367% | 132/132 | ready |
| Gym Challenge - Unlimited | current | 100% | $3,157.70 | 143 | 122.638652 | 2.3228% | 132/132 | ready |
| Gym Heroes - 1st Edition | current | 100% | $4,551.90 | 157 | 123.786447 | 5.1035% | 132/132 | ready |
| Gym Heroes - Unlimited | current | 100% | $2,044.22 | 143 | 129.564699 | 2.2990% | 132/132 | ready |
| Jungle - 1st Edition | current | 100% | $3,103.24 | 157 | 122.407570 | 4.3069% | 64/64 | ready |
| Jungle - Unlimited | current | 100% | $1,102.13 | 143 | 116.089448 | 1.6431% | 64/64 | ready |
| Neo Destiny - 1st Edition | unavailable | 99.12% | — | 0 | — | — | 112/113 | incomplete identity |
| Neo Destiny - Unlimited | current | 100% | $13,229.07 | 147, 04-21..09-22 | 120.601408 | 2.5441% | 113/113 | ready |
| Neo Discovery - 1st Edition | current | 100% | $3,650.90 | 157 raw | 84.321460 | 23.7795% | 75/75 | **withheld source defect** |
| Neo Discovery - Unlimited | current | 100% | $2,390.09 | 143 | 139.978448 | 12.2265% | 75/75 | ready, reviewed real move |
| Neo Genesis - 1st Edition | current | 100% | $4,158.60 | 157 raw | 133.359843 | 18.9947% | 111/111 | **withheld source defect** |
| Neo Genesis - Unlimited | current | 100% | $2,102.08 | 143 | 126.944097 | 1.9374% | 111/111 | ready |
| Neo Revelation - 1st Edition | unavailable | 98.48% | — | 0 | — | — | 65/66 | incomplete identity |
| Neo Revelation - Unlimited | unavailable | 98.48% | — | 0 | — | — | 66/66 identities, 65 priced | incomplete price |
| Team Rocket - 1st Edition | current | 100% | $3,627.75 | 157 raw | 107.909978 | 14.4454% | 83/83 | **withheld source defect** |
| Team Rocket - Unlimited | current | 100% | $1,966.34 | 143 | 118.256885 | 0.8880% | 83/83 | ready |

Current latest valuation rows are newer than Sep-22 and therefore differ slightly; they are **not** substituted into a Sep-22 prepared generation.

## O. Physical identity / subset / non-Set regressions

- All 21 vintage scopes: wrong-edition row count **0**.
- All 21 vintage scopes: duplicate `(canonical_card_id, market_scope)` physical identity count **0**.
- For every scope, set-based resolved physical-variant counts exactly equal `pokemon_market_root_set_value_latest_v1.resolved_variant_count`.
- No vintage edition root currently has a qualifying child/subset. The root/subset algorithm was separately checked on `ME: 30th Celebration` + `ME: 30th Celebration Classic Collection`: 188 eligible canonical cards = Standard root expected/resolved 188/188.
- Current serving non-Set rows: 17 Era + 6 curated + 9 prepared rarity + 5 sealed = **37**, one 2026-09-22 watermark and one generation.
- Existing serving Set rows before cutover: 156 generic Standard rows.
- No Set-market breadth widget/field is rendered by the prepared /Market or prepared Set Explorer surface. Set-page breadth remains outside this pass; custom Explorer query breadth is a separate filtered-market authority.
- Context ranking is explicitly deferred: live `get_pokemon_market_explorer_set_context_ranking_v1` accepts only `set_id` and reads edition-blind daily states. The application hides it for scoped markets.
- Scoped movers are also deferred: no scope-aware mover authority exists and the application hides generic movers for scoped markets.

## P. Application contract required after this DB design

The application branch already supports `marketKey`, `marketScope`, `baseSetName`, duplicate `setId` siblings and scoped history reads. The remaining required reconciliation is small but mandatory:

1. In `pokemon_explore_set_value_service.py`:
   - compute root set_count from distinct published `setId`;
   - expose/diagnose market_count as `len(published)`;
   - keep all 167 explicit identities, including null-valued unavailable scopes;
   - never use latest scope value for an older approved Market Date.
2. In `audit_pokemon_market_publication.py`:
   - select `market_count`;
   - require `set_count == distinct root setIds`;
   - require `market_count == len(payload_json.sets)`;
   - validate uniqueness by `marketKey`, not `setId`;
   - still require the distinct root IDs to match the expected root cohort.
3. Update corresponding unit fixtures/tests.
4. Keep scoped movers/context ranking hidden until their own scope-aware authorities exist.
5. Do not merge the coordinator prototype migration over this DB authority branch; reconcile the application files against this final contract.



No production database write has been performed.

Authorization is still required for:

1. **Creating a paid Supabase development branch** (none currently exists) to execute the migration/tests on real PostgreSQL.
2. **Applying the migration to production and running the production scoped publication/promotion sequence.**
