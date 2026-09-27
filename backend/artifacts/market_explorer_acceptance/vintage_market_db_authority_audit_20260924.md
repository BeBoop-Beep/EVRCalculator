# Vintage Market DB Authority Audit — 2026-09-24

## Status

**DB design complete; production not changed.**

Branch: `fix/market-vintage-db-authority-20260924`

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

For `pokemon_explore_set_value_snapshot_latest`, current service and audit code define `set_count` as the number of rows in `payload_json.sets`.  It is therefore a **market-row count** and should become 167 after scope activation.

Do **not** change unrelated root-cohort counts:

- `pokemon_market_date_quality.cohort_set_count` remains a root-set count.
- global raw/top10 index `set_count` remains its existing root/cohort semantic.

Non-DB follow-up required: the current Python global Set Market publication audit treats `setId` as unique and will reject scoped sibling rows.  The code agent must switch that identity check/index to `marketKey` (and update tests / historical one-off repair workflows that hard-code snapshot `set_count == 156`).

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

Migration adds:

- `pokemon_market_set_scope_contract_v1`
- `validate_pokemon_market_set_scope_payload_v1`
- `validate_pokemon_market_scoped_history_baskets_v1`
- `get_pokemon_market_root_set_card_prices_as_of_v1`
- `pokemon_market_scoped_history_large_move_reviews_v1`
- `pokemon_market_scoped_history_market_certification_v1`
- explicit-scope prepared directory/history logic
- explicit-scope lightweight workspace sync
- date-pinned scoped constituent staging with exact certified-roster validation

Security: fixed search paths, service-role-only new internal authorities, RLS/no public writes on the review ledger, bounded statement timeouts, no generated UUID literals.

The migration dynamically patches only the marked Set/history/constituent sections of the deployed refresh/staging functions.  Live marker checks passed.  The deployed constituent advisory lock and guarded publisher `already_current` shortcut are outside those patches and remain intact.

## J. Required tests

The SQL test file asserts:

- Standard root -> one Standard market.
- edition_split -> exactly first + unlimited.
- Base -> exactly first + shadowless + unlimited identities.
- no generic edition-split key.
- unique market key.
- fixed physical identity per canonical+scope.
- constant complete certified basket.
- Base fail-closed behavior.
- known source-defect histories withheld.
- post-activation prepared Set count equals snapshot market-row count.
- prepared scope metadata.
- no generic vintage prepared row.
- date/scope-consistent prepared constituents.
- withheld history absent.
- v3 constituent serving function preserved.

Read-only live shadow/parity checks passed.  The migration/test script itself still requires execution on a real migrated PostgreSQL database before production.

## K. Rollback

No destructive down migration is planned.

Before cutover, capture the current serving generation id and the current global Set Market snapshot row.

If the new generation fails validation:

1. call `rollback_pokemon_market_explorer_prepared_generation_v1(previous_generation_id, operator_path)`;
2. restore the captured prior global Set Market snapshot if the scoped snapshot had already been committed;
3. deploy a forward corrective migration.

Immutable prior generation rows are not mutated by this migration.

## L. Production sequence

1. **Real PostgreSQL gate:** create/use an isolated Supabase development branch, apply the migration, run `supabase/tests/explicit_vintage_market_scopes.sql`, and run shadow publisher validation.
2. Code agent updates the global Set Market snapshot writer to emit `marketScope`, `marketKey`, `baseSetName`, scoped current values/status, no generic edition root, and `set_count=len(market rows)`.
3. Code agent updates publication audit identity from `setId` to `marketKey`.
4. Apply this DB migration to production.
5. Dry-run scoped snapshot and verify 167 rows / 156 distinct root ids / 0 generic vintage keys.
6. Capture current serving generation id + previous snapshot row.
7. Commit the scoped global Set Market snapshot.
8. Run the guarded full prepared publisher for the required approved Market Date; do not rely on lightweight sync for serving cutover.
9. Validate the new serving generation: 167 Set markets, 204 directory rows total (assuming non-Set count remains 37), single comparison watermark, exact scoped constituents, source-defect histories absent.
10. Only then retire the old generic contract in application expectations.

## M. Operations still requiring explicit authorization

No production database write has been performed.

Authorization is still required for:

1. **Creating a paid Supabase development branch** (none currently exists) to execute the migration/tests on real PostgreSQL.
2. **Applying the migration to production and running the production scoped publication/promotion sequence.**
