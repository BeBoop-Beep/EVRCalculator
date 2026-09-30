# FMA-0.1 — review closure for Explorer Focused Market Activity V1

Scope: correction and review closure of the FMA-0 contract work on branch
`fma0-explorer-focused-activity` (PR #485, base `develop`). The prior commit
`36a15dc0` is kept unchanged; this pass adds one commit on top.

**Outside this pass:**
- FMA-1: database, projections and RPCs.
- FMA-2: public API, auth and transport.
- FMA-3: the fixture-backed UI.
- Frontend files; canonical pricing, Set Value, the Market Index, RIP,
  Collector Appeal, Fair Value, and population or condition conversion.
- Provider calls, backfill, cron, credentials, SSH, merges, deploys and
  migrations.

**Result versions.**

| Item | Version |
|---|---|
| Contract | `market_activity_v1.1` (was `market_activity_v1`) |
| Domain | `market_activity_domain_v1.1.0` (was 1.0.0) |
| Fixture set | `market_activity_v1_fixtures_2` (was `_1`, now superseded), 19 fixtures (was 11) |
| New rule versions | observation `fma_sold_observation_v1`, series `fma_activity_series_v1`, peer population `fma_peer_population_v2`, cursor `fma_cursor_v1` |
| Bumped rule versions | window readiness `fma_window_readiness_v2`, supply `fma_supply_provenance_v2`, membership `fma_membership_v2` |
| Unchanged rule versions | identity `fma_exact_identity_v1`, grading `fma_grading_identity_v1`, qualifier registry `fma_qualifier_registry_v1`, tie policy `midrank_v1`, display policy `fma_display_policy_v1` |

**Manifest digest** (`fixtures/manifest.json`):
- SHA-256 of canonical JSON (the FMA fingerprint convention):
  `e6235d9c73dc7ce6e38b81431bcfe60e4a32ae27f2780632aae45d407705e007`
- raw-bytes SHA-256:
  `88c67090220ef1ab6587970f4fd6f38f369a17a5e461a63b4c41b60dc9cf45b7`

## Baseline and `develop` divergence

- `git fetch origin develop` brought `develop` to `d008a943`. That is PR #484:
  active-supply preflight and exact-207 health checks.
- `git diff --stat b5c4f5da d008a943` touches only four files:
  - `backend/scripts/check_market_active_supply_health.py`
  - `backend/scripts/preflight_market_active_supply_panel.py`
  - `backend/scripts/run_market_active_supply_snapshot.py`
  - `backend/scripts/test_market_active_supply_bucket_c.py`
- None of those files is touched by FMA-0 or FMA-0.1, so there is no conflict.
- The branch was **not** rebased or merged. It still diverges from `develop`
  at `b5c4f5da`. PR #484's work is preserved untouched and will combine
  cleanly on merge.

## Method

Reproduce first, then fix. All reproduction tests live in
`backend/tests/unit/domain/pokemon/test_market_activity_review_closure.py`.
- They were written **before** any code change and run against the
  unmodified FMA-0 module at `36a15dc0`.
- They build inputs through the generator's own fixture builders
  (`gen._detail`, `gen._roster_inputs`). The same test source therefore
  exercises the real assembler shapes before and after the fix.

Red-run command:

    py -3.11 -m pytest backend/tests/unit/domain/pokemon/test_market_activity_review_closure.py -q -p no:cacheprovider -rA --tb=line

Red-run summary line, verbatim: `35 failed, 2 passed in 0.12s`.

The 2 red passes were
`test_f2_malformed_or_unbound_receipts_fail_closed[inverted_dates]` and
`[missing_output_cursor]`. The FMA-0 date-order and cursor-chain checks
already caught those two cases, and the tests are kept as regression guards.
Every other test failed, with the per-finding output quoted below.

The review's own findings came from a harness outside the repository. Each
one was re-verified against the real module. One detail differed and is noted
under F1.

---

## F1 — Preserve observed facts when coverage receipts are absent

**Reproduction tests**
- `test_f1_legacy_rows_without_walk_receipts_keep_observed_counts`: the
  fixture 01 evidence with `walks=[]` must keep `observedCount == 8` for 30d,
  a non-null price summary, `observedSales` available, and `saleCount` and
  `activityPercentile` unavailable.
- `test_f1_missing_collection_differs_from_known_collection_with_zero_matches`:
  no rows and no receipts gives null counts. Stored rows with none in the 7d
  window give `observedCount == 0`, which is a known collection with zero
  matches.

**Red output (verbatim)**

    E   assert None == 8
    ...test_market_activity_review_closure.py:65: assert None == 8
    E   KeyError: 'observedSales'

The review's description was confirmed. `best_window_readiness([])` returned
NOT_COLLECTED, and `collected = readiness.state != 'NOT_COLLECTED'` nulled
`observedCount` and `priceSummary`. Verified detail: the stored rows *were*
classified. The information was lost only at the `collected` gate.

**Correction (`market_activity.py`)**
- New `sold_observation()` (`fma_sold_observation_v1`). It separates collection
  evidence from completeness proof. The bases, strongest first, are:
  - `WALK_RECEIPT`: a committed walk bound to the provider card;
  - `COLLECTION_RECORD`: an explicit collection record for the same provider
    card;
  - `STORED_ROWS`.
- `NOT_COLLECTED` applies only when none of these exist.
- When the card is observed but has no receipt, each window is `UNPROVEN`
  with the new reason `COMPLETENESS_RECEIPT_MISSING`. `observedCount` is the
  exact eligible-row count, where 0 means a known collection with zero
  matches, and `provenCount` is null.
- The price summary is kept and labelled `basis: OBSERVED_ONLY` (or
  `PROVEN_WINDOW`).
- New capability `observedSales`. `saleCount`, `salePriceSummary` and
  `activityPercentile` stay proven-only.
- Group `observedSaleCountLowerBound` now sums every non-null
  `observedCount`.

**Contract changes**
- `common.schema.json` adds `Observation`, `sales.observation`,
  `PriceSummary.basis`, the `observedSales` capability, and
  `observationState` on constituent rows.
- CONTRACT §3 null/zero rules and §6a.
- SCHEMA_DECISION adds `observation_state`/`observation_basis`, invariant
  checks, and `summary_basis`.

**New fixture:** `fma_fixture_12_legacy_no_receipts` (PARTIAL). It has
observed counts `[4, 8, 11, 12]`, all `provenCount` null, `observedSales`
available, `saleCount` unavailable, and peers `UNAVAILABLE`.

**Green:** both F1 tests pass (see the final run below), plus
`test_f1_explicit_collection_record_is_observation_not_proof`.

## F2 — Fail closed on malformed or future completeness proof

**Reproduction tests**
- `test_f2_future_right_edge_is_never_proven`: a completed right edge at
  2027-01-01 with evaluation at 2026-09-30.
- `test_f2_unknown_has_more_is_not_exhaustion`: a truncated walk whose last
  page has `hasMore: None`.
- `test_f2_malformed_or_unbound_receipts_fail_closed`, 11 cases:
  - wrong card;
  - right edge on the wrong card, filter or tier;
  - uncommitted collection;
  - missing or negative `rowCount`;
  - string `hasMore`;
  - inverted dates;
  - missing output cursor;
  - non-boolean `completed`.
- `test_f2_unknown_pagination_never_advances_a_checkpoint`.

**Red output (verbatim)**

    E   AssertionError: assert 'PROVEN' != 'PROVEN'        (future right edge)
    E   AssertionError: assert 'PROVEN' != 'PROVEN'        (hasMore None -> exhausted)
    E   AssertionError: wrong_card
    E   AssertionError: right_edge_wrong_card
    E   AssertionError: right_edge_wrong_filter
    E   AssertionError: right_edge_wrong_tier
    E   AssertionError: uncommitted_collection
    E   AssertionError: missing_row_count
    E   AssertionError: negative_row_count
    E   AssertionError: string_has_more
    E   AssertionError: right_edge_completed_not_bool
    E   assert (True is False)                              (checkpoint advanced on hasMore None)

**Correction (`fma_window_readiness_v2`)**
- `_page_type_reasons` requires typed page fields:
  - `pageIndex` equals the page position;
  - `rowCount` is a non-negative integer and not a bool;
  - `hasMore` is a real bool;
  - `hasMore is True` needs a non-empty output cursor, and `hasMore is False`
    needs none;
  - a page with rows has valid, ordered, non-future date bounds;
  - a zero-row page has no bounds and no `hasMore: true`.

  New reasons: `WALK_RECEIPT_MALFORMED` and `WALK_PAGINATION_UNKNOWN`.
- `exhausted = last_page.hasMore is False`, and the cursor chain requires the
  prior page's `hasMore is True`.
- `_walk_binding_reasons` binds the walk to the instrument's provider card
  through the new `provider_card_id` argument. It also requires `walkId`,
  `collectionRunId` and `committed is True`. New reason:
  `WALK_BINDING_MISMATCH`. Omitting `provider_card_id` fails closed.
- `_right_edge` checks the right-edge receipt:
  - `completed` must be literally true (`RIGHT_EDGE_INVALID`);
  - the timestamp must be valid and not in the future beyond the skew
    (`RIGHT_EDGE_IN_FUTURE`);
  - it must be bound to the same provider card, stream, filter fingerprint,
    grader/grade filter, head walk and committed collection run
    (`RIGHT_EDGE_BINDING_MISMATCH`).
- `checkpoint_advance_decision` drains only on `hasMore is False`. Unknown
  pagination is a structural failure. No watermark is advanced anywhere.

**Contract changes**
- CONTRACT §6b is rewritten.
- COLLECTOR_HANDOFF receipt DDL gains `collection_run_id`, `committed` and
  the right-edge binding columns, plus typed receipt rules.
- 7 reason codes are added to the registry and the schema enum.

**New fixture:** `fma_fixture_13_future_right_edge`. All windows are PARTIAL
with `RIGHT_EDGE_IN_FUTURE`, and there are no proven counts. Existing
fixtures' walks now carry full binding fields.

**Green:** all 14 F2 tests pass, plus `test_f2_bound_valid_receipt_still_proves`.

## F3 — Unconfirmed offers never set a current asking price

**Reproduction tests**
- `test_f3_unconfirmed_offer_cannot_set_current_lowest_ask`: a fresh $10
  offer plus an unconfirmed $1 offer.
- `test_f3_unconfirmed_offer_never_counts_toward_depth`.
- `test_f3_missing_has_more_is_unknown_depth`.
- `test_f3_empty_response_with_contradictory_or_unknown_pagination_is_not_zero`,
  with `hasMore` set to `True`, `None` and `"false"`.
- `test_f3_current_ask_capability_expires_with_provider_confirmation`.

**Red output (verbatim)**

    E   AssertionError: assert 'FRESH' != 'FRESH'           (fresh $10 + unconfirmed $1 -> FRESH)
    E   assert 2 == 1                                       (unconfirmed offer counted in depth)
    E   AssertionError: assert 'COMPLETE_AT_SOURCE' != 'COMPLETE_AT_SOURCE'   (missing hasMore)
    E   AssertionError: assert 'ZERO_PROVEN' != 'ZERO_PROVEN'  (x3: hasMore True / None / "false")
    E   KeyError: 'expiresAt'

The review's reproduction was confirmed: `usable` kept null-confirmation
offers, and the lowest ask was $1 under FRESH.

**Correction (`fma_supply_provenance_v2`)**
- Offers are split into confirmed and unconfirmed. Unconfirmed offers are
  missing, unparseable or future-confirmed.
- `lowestAsk`, `capturedListingCount`, `capturedQuantity` and `depth` use
  confirmed offers only.
- Unconfirmed offers are reported under `unconfirmedOffers`
  (`{count, futureCount, capturedQuantity, lowestAsk, reasons}`), with their
  shipping and quantity provenance preserved.
- New state `PARTIALLY_CONFIRMED` for a mix of confirmed and unconfirmed
  offers. `offerQualification` is `NOT_CURRENT`, and every current capability
  is withheld.
- `hasMore` must be a bool. Otherwise depth is `UNKNOWN` with
  `SUPPLY_PAGINATION_UNKNOWN`, and `askDepth` is unavailable.
- An empty offer list with `hasMore: true` is `SUPPLY_PAGINATION_CONTRADICTORY`
  and is never zero.
- `currentUntil` is the effective confirmation plus 24 hours. The
  `currentAsks`, `askDepth` and `landedAsk` capabilities carry it as
  `expiresAt`.
- New `reevaluate_capabilities(caps, at=...)` makes an expired capability
  unavailable with `ASKS_STALE`.

**Contract changes**
- New `ExpiringCapability`.
- `Asks` gains `currentUntil`, `offerQualification` and
  `unconfirmedOffers`.
- `AskState` gains `PARTIALLY_CONFIRMED`, and depth gains `UNKNOWN`.
- CONTRACT §7 is rewritten.
- The SCHEMA_DECISION asks table gains `current_until`,
  `offer_qualification`, `unconfirmed_offers` and a check.

**New fixture:** `fma_fixture_14_mixed_unconfirmed_asks`. The state is
`PARTIALLY_CONFIRMED`, the lowest ask is the confirmed $44.00 (never $1.00),
and `currentAsks` is unavailable.

**Changed old expectation (it was the bug).** In
`test_market_activity.py::test_null_future_mixed_and_repeated_confirmations`,
`capturedListingCount == 3` became `== 2`. The old value 3 counted the
null-confirmation offer toward depth, which is exactly this finding. The test
now also asserts `unconfirmedOffers` `count == 1` and `futureCount == 1`.

**Green:** all 7 F3 tests pass, plus
`test_f3_unconfirmed_offers_keep_their_provenance_separately`.

## F4 — Supply the actual chart contract

**Reproduction tests**
- `test_f4_group_and_instrument_responses_define_dated_series`: the schemas
  must define `series`, `GroupSeries` and `InstrumentSeries`.
- `test_f4_instrument_series_is_sparse_daily_and_never_repeats_window_totals`:
  the points are sparse (every point ≥1), sorted and unique, and the count
  points sum to the 180d observed count.

**Red output (verbatim)**

    E   AssertionError: assert 'series' in {'availability': {'$ref': 'common.schema.json#/$defs/Availability'}, 'contractVersion': {'const': 'market_activity_v1'...
    E   KeyError: 'series'

**Correction (`fma_activity_series_v1`)**
- `sales_series`, `supply_series` and `group_series` produce `series` on the
  instrument detail and the group response.
- **Envelope:**
  - `storage: SPARSE_DAILY`;
  - `zeroRule: ABSENT_DATE_IS_ZERO_ONLY_INSIDE_PROVEN_SPAN`;
  - `outsideActivityRange: NOT_COLLECTED`;
  - `canonicalRange`, from the new request `chartRange`;
  - `activityRange` (`[asOf−179, asOf]`).
- **Separate unit axes:**
  - `sales.counts` (`SALE_COUNT`), where each point has an observation or
    proof state and ingestion timestamps;
  - `sales.prices` (`USD`);
  - `supply.listings` (`LISTING_COUNT`);
  - `supply.quantity` (`LISTED_QUANTITY`);
  - `supply.lowestAsk` (`USD`).
- **Supply dating:** each point is dated by provider confirmation. A repeated
  confirmation collapses to one point with `collectionCount > 1`. There is
  never a zero-fill or carry-forward, and a proven empty snapshot is an
  explicit 0 point.
- **Group series:** they carry no dollar axis, and each point has
  `contributingConstituents` and `provenConstituents`. `provenSpan` is the
  intersection of the constituents' spans.

**Contract changes**
- `common.schema.json` adds series point, axis and envelope defs, and both
  response schemas gain `series`.
- CONTRACT §10 fixes the hover rule: window totals are never drawn at
  historic dates.
- SCHEMA_DECISION §E adds the sparse daily storage projection, with
  `market_activity_daily_v1`, `market_activity_supply_daily_v1` and a series
  meta table, and the zero-versus-missing storage rule.

**New fixture:** `fma_fixture_15_multi_date_series`. It covers:
- missing dates (gaps);
- a late-ingested 2026-09-05 sale, so 7d stays PROVEN while 30/90/180d are
  PARTIAL, and the point is flagged `ingestedAfterReconciliation: true`;
- two sales on one date;
- a sale before the activity range, which is excluded;
- a repeated source confirmation (`collectionCount: 2`);
- an unconfirmed snapshot, which is excluded;
- a `ZERO_PROVEN` supply point;
- a 365-day canonical range against the 180-day activity range.

Fixture 11 (group) now also carries a group series under a 365-day
`chartRange`.

**Green:** both F4 tests pass.

## F5 — Pin evidence, roster and pagination separately

**Reproduction tests**
- `test_f5_constituent_request_pins_activity_generation_roster_and_cursor`:
  the request schema must have `activityGenerationId`, `rosterRef` and
  `cursor`, and no `afterRank`. `nextCursor` must not be an integer.
- `test_f5_activity_refresh_under_unchanged_market_generation_is_rejected`.
- `test_f5_next_cursor_is_opaque_and_revision_bound`.
- `test_f5_docs_use_post_reads_and_sha256_fingerprint_with_separate_activity_id`.

**Red output (verbatim)**

    E   AssertionError: assert {'activityGen..., 'rosterRef'} <= {'afterRank',... 'windowDays'}
    E   AssertionError: assert 'AVAILABLE' == 'UNAVAILABLE'   (activity refresh accepted)
    E   assert (False)                                        (nextCursor was the int 2)
    E   AssertionError: assert 'GET /market...rer/activity' not in '# Explorer ...

**Correction (`fma_membership_v2`, `fma_cursor_v1`)**
- Every request now carries three independent pins, checked by
  `check_pins`:
  - `activityGenerationId`, which gives `ACTIVITY_GENERATION_MISMATCH` or,
    for a RETIRED generation, `ACTIVITY_GENERATION_EXPIRED`;
  - an immutable `rosterRef`, prepared (`SURFACE_V2_GENERATION`) or custom
    (`QUERY_CACHE_PUBLISHED_REVISION`), which gives
    `ROSTER_REVISION_MISMATCH` when it differs from the activity
    generation's roster;
  - for pages, an opaque `cursor`.
- For custom markets, the request's `marketKey` must be
  `custom:{queryFingerprint}`. The canonical query builder is never invoked.
- `encode_cursor`/`decode_cursor` produce `fmac1.<hex json>.<check>`. The
  cursor binds the cursor version, activity generation, SHA-256 of
  `rosterRef`, market, asOf, window and last rank. A tampered cursor gives
  `CURSOR_INVALID`, and a rebound one gives `CURSOR_MISMATCH`.
- Responses gain `activityGenerationId`. `evidenceFingerprint` stays SHA-256.
- Docs:
  - The reads are now structured POST, matching the existing
    `POST /market/explorer/prepared` and `/query/constituents`. GET is
    withdrawn.
  - SCHEMA_DECISION no longer says to echo the UUID in
    `evidenceFingerprint`.
  - Pin and expiry semantics are specified (SERVING/RETAINED/RETIRED).
  - Ownership is restored: FMA-1 owns the DB, projections and RPCs; FMA-2 the
    public API, auth and transport; FMA-3 the UI fixtures.

**Contract changes**
- All three request schemas are rebuilt around `activityGenerationId` and
  `rosterRef`. The page request has `limit` and `cursor`; the others have
  `chartRange`.
- New `Cursor` def, and `page.nextCursor` is a nullable `Cursor`.
- The envelope gains `activityGenerationId`.
- CONTRACT §2 and §8, and SCHEMA_DECISION §A, §B and build rule 4.

**New fixtures**
- `fma_fixture_16_constituent_page_cursor`: page 2 is read through the cursor.
- `fma_fixture_17_cursor_mismatch`: an activity refresh under the same market
  generation gives `CURSOR_MISMATCH`.
- `fma_fixture_18_activity_generation_expired`.

**Changed old expectation (it was the bug).** In
`test_market_activity_contract.py::test_fixture_states_match_their_scenarios`,
the constituent page expectation `"nextCursor": 2` was replaced. That bare
integer is the non-revision-bound cursor this finding is about. The test now
asserts the other page fields, decodes the opaque cursor (`k == 2`), and
checks row order `[1, 2]`.

**Green:** all 4 F5 tests pass, plus
`test_f5_custom_market_maps_by_published_revision_without_the_query_builder`
and `test_f5_tampered_or_rebound_cursor_is_rejected`.

## F6 — Full-roster and peer integrity

**Reproduction tests**
- `test_f6_group_aggregation_covers_rosters_larger_than_one_page[101|207]`.
- `test_f6_pages_are_rank_sorted_even_when_members_arrive_shuffled`.
- `test_f6_duplicate_or_gapped_ranks_are_rejected`.
- `test_f6_thirty_copies_of_one_peer_are_one_peer`.
- `test_f6_conflicting_peer_observations_are_quarantined`.
- `test_f6_peers_from_a_different_date_window_with_the_same_duration_are_excluded`.
- `test_f6_invalid_rows_are_quarantined_before_deduplication`.

**Red output (verbatim)**

    E   ValueError: group aggregation requires the full roster (<=100 members in V1 fixtures)   (x2: 101, 207)
    E   assert [5, 3] == [1, 2]                              (shuffled members sliced unsorted)
    E   AssertionError: assert 'AVAILABLE' == 'UNAVAILABLE'  (duplicate rank accepted)
    E   assert 30 == 1                                       (30 copies of one peer = 30 peers)
    E   assert 31 == 29                                      (conflicting peer counted twice)
    E   AssertionError: assert 'AVAILABLE' != 'AVAILABLE'    (other-dates 30d peers matched)
    E   ValueError: invalid money: 'ten dollars'             (raised before quarantine)

**Correction**
- `validate_members` enforces the roster invariants:
  - member count equals the denominator;
  - ranks are unique and contiguous, `1..N`;
  - variants and instrument keys are unique and parse correctly;
  - members are sorted by rank.

  A violation is `ROSTER_INTEGRITY_VIOLATION` (UNAVAILABLE) instead of
  raising.
- `aggregate_group_activity` no longer delegates to one 100-row page. It
  walks every validated member. The 1..100 cap stays on constituent pages
  only.
- Peers (`fma_peer_population_v2`):
  - The count is of unique peer instruments. Same-value duplicate rows count
    once (`duplicatePeerRowCount`). Instruments with conflicting or invalid
    values are quarantined (`quarantinedPeerCount`) and never count toward
    the threshold.
  - The population key binds the **actual dated window** plus an explicit
    scope: `peer_scope()` with `RESEARCH_PANEL` (plus `cohortRevision`) or
    `MARKET_ROSTER` (bound to the response `rosterRef` and the pinned
    activity generation).
  - Responses carry `scope`, and `claimsAllPokemon` is always false.
- `validate_sold_row` runs before deduplication. Missing listing identity,
  invalid money, date or timestamps give `INVALID_EVIDENCE_ROW`. Valid rows
  are preserved, and the excluded counts are deterministic and
  canonical-ordered. Duplicate "first seen" now compares parsed instants.

**Contract changes**
- The `Peers` schema gains `scope`, `quarantinedPeerCount` and
  `duplicatePeerRowCount`, and new `PeerScope` def. `scopeLabel` is no longer
  a constant.
- CONTRACT §4 (row validation), §8 (integrity, page cap) and §9 (peer scope
  and key).
- SCHEMA_DECISION: peer-rank scope and quarantine columns, and the roster
  validation text.

**New fixture:** `fma_fixture_19_group_roster_101`. 101 members are supplied
in a deterministic shuffled order and aggregated in full
(`rosterDenominator 101`, 5 observed constituents). Fixture 01 now includes a
duplicate peer row, counted once, and a same-duration other-dates peer,
excluded. `_raw_records()` now includes an invalid-money row, so
`INVALID_EVIDENCE_ROW: 1` appears in the fixture excluded counts.

**Green:** all 8 F6 tests pass, plus:
- `test_f6_pages_concatenate_to_the_full_roster_and_match_the_group_oracle`
  (101/100, 207/100 and 207/37; pages read through cursors concatenate to
  ranks `1..N` and sum to the group oracle);
- `test_f6_duplicate_variant_in_roster_is_rejected`;
- `test_f6_market_roster_peer_scope_is_bound_to_roster_and_activity_generation`.

---

## Test-helper shape updates (not expectation changes)

In `test_market_activity.py`, the `_walk` helper now emits the binding fields
that window readiness v2 requires, and `_eval` and `best_window_readiness`
pass `provider_card_id="1"`. The `KEY` constant uses the new
`peer_population_key` signature, which takes the dated window and scope key.
Every assertion in those tests is unchanged. Only the two expectations called
out under F3 and F5 were changed, because each encoded the defect.

## Final verification (actual output)

Commands, run from the worktree root on both runtimes:

    py -3.8  -m pytest backend/tests/unit/domain/pokemon/test_market_activity.py backend/tests/unit/domain/pokemon/test_market_activity_contract.py backend/tests/unit/domain/pokemon/test_market_activity_review_closure.py -q -p no:cacheprovider
    py -3.8  -m backend.scripts.build_market_activity_v1_contract_artifacts --check
    py -3.11 -m pytest (same three files) -q -p no:cacheprovider
    py -3.11 -m backend.scripts.build_market_activity_v1_contract_artifacts --check

Verbatim output:

    $ py -3.8 --version
    Python 3.8.10
    $ py -3.8 -m pytest <3 FMA test files> -q -p no:cacheprovider
    ........................................................................ [ 99%]
    .                                                                        [100%]
    145 passed in 0.74s
    $ py -3.8 -m backend.scripts.build_market_activity_v1_contract_artifacts --check
    {
      "drift": []
    }
    exit code: 0
    $ py -3.11 --version
    Python 3.11.9
    $ py -3.11 -m pytest <3 FMA test files> -q -p no:cacheprovider
    ........................................................................ [ 99%]
    .                                                                        [100%]
    145 passed in 0.61s
    $ py -3.11 -m backend.scripts.build_market_activity_v1_contract_artifacts --check
    {
      "drift": []
    }
    exit code: 0
    $ py -3.11 -m pytest backend/tests/unit/domain/pokemon/test_market_activity_review_closure.py -q -p no:cacheprovider
    47 passed in 0.25s

**What these runs cover**
- **Schemas:** `test_manifest_validates_and_pins_versions` and
  `test_fixture_validates_and_is_reproduced_by_the_domain` validate every
  fixture's request body and expected response against the schemas with
  `SchemaRegistry`. `--write` also re-validated every fixture.
- **Offline:** the provider-egress tripwire tests are among the passes.
  - `test_egress_tripwire_is_armed`;
  - `test_fresh_import_opens_no_connection_and_loads_no_client_modules`;
  - the autouse socket blockers in all three files.
- **Stdlib-only:** the import allowlist test still passes. No new imports
  were added; the cursor uses hex rather than `base64`.

**Out-of-scope pre-existing failure.** In a broader
`backend/tests/unit/domain/pokemon/` sweep,
`test_prepared_constituent_summary.py::test_no_historical_observation_leaks_into_the_summary`
fails with `RuntimeError: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be
set in the environment`. It fails identically at baseline `36a15dc0`, checked
in a temporary detached worktree that was then removed. It needs environment
credentials and is unrelated to this work.
