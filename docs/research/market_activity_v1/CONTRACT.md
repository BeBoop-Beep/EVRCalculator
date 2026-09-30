# Explorer Focused Market Activity V1 — contract (FMA-0)

Status: **frozen for FMA-1 (database/API) and FMA-3 (fixture-backed frontend)**.
Contract version `market_activity_v1`; domain `market_activity_domain_v1.0.0`;
fixture set `market_activity_v1_fixtures_1`.

This page gives the rules in prose. The executable rules are in:

| Artifact | Path |
|---|---|
| Pure domain rules | `backend/domain/pokemon/market_activity.py` |
| Schema validator + fingerprints | `backend/domain/pokemon/market_activity_contract.py` |
| JSON Schemas | `docs/research/market_activity_v1/contracts/*.schema.json` |
| Fixtures + manifest | `docs/research/market_activity_v1/fixtures/` |
| Generator (offline) | `backend/scripts/build_market_activity_v1_contract_artifacts.py` |
| Tests | `backend/tests/unit/domain/pokemon/test_market_activity*.py` |

If this document and the code disagree, the code and its tests win. Any rule
change needs a version bump, a regenerated fixture set and a new manifest.

## 1. Scope and non-goals

The feature is read-only and applies only to `/Market/Explorer`, its focused
graph and its constituents panel. It is not an input to canonical prices, Set
Value, the Market Index, RIP, Collector Appeal, Fair Value, population sourcing,
condition-to-NM conversion or the main Market tab.

V1 does not include buy/sell signals, OHLC bars, demand or scarcity
composites, turnover, or sales inferred from disappearing listings. Those
features stay explicitly unavailable (`supplyTurnover` and
`inferredSalesFromListings` always return `FEATURE_DISABLED_V1`).

Only the `cards` asset is supported. `sealed` and the `graded` Explorer asset
return `UNSUPPORTED_ASSET`. Graded tiers of a card variant are covered
through the instrument detail endpoint.

## 2. Endpoints (proposed for FMA-1, read-only)

| Endpoint | Request schema | Response schema |
|---|---|---|
| `GET /market/explorer/activity` | `activity_request` | `activity_response` (`kind: groupActivity`) |
| `GET /market/explorer/activity/constituents` | `constituent_page_request` | `constituent_page_response` |
| `GET /market/explorer/activity/instrument` | `instrument_detail_request` | `instrument_detail_response` |

All requests carry `marketKey`, `generationId`, `asOf` (a date) and
`windowDays` (one of 7, 30, 90 or 180). The constituent page also takes
`afterRank` (0 or more) and `limit` (1 to 100). The instrument request takes
`instrumentKey`. Every response carries `contractVersion`, `versions`, `policy`,
`request`, `evaluatedAt`, `availability` and `evidenceFingerprint`.

## 3. Representation rules

- **Money** is `{"amount": "12.34", "currency": "USD"}`. The amount is a
  decimal string with exactly two places and never a float. Only USD is
  supported, and any other currency becomes `CURRENCY_UNSUPPORTED`.
- **Percentages** are one-decimal strings, such as `"57.1"`.
- **Timestamps** are UTC `YYYY-MM-DDTHH:MM:SSZ`, and **dates** are
  `YYYY-MM-DD`.
- **Null means "not established".** `0` means proven zero. A count or price is
  null whenever proof is missing. It is never `0`.
- **Reasons** are registered codes (`REASON_CODES`) emitted in canonical
  order and de-duplicated. The schema enum matches the registry exactly.
- **Availability** is `AVAILABLE`, `PARTIAL` or `UNAVAILABLE`.
  `UNAVAILABLE` is used only for request-level faults: an unsupported asset, a
  generation mismatch, an invalid key, an unstable roster revision, or an
  instrument that is not in the roster.
- **Capabilities** are reported per feature as `{available, reasons}` for
  `saleCount`, `salePriceSummary`, `activityPercentile`, `currentAsks`,
  `askDepth`, `landedAsk`, `supplyTurnover` and `inferredSalesFromListings`.
  Each availability dimension (identity, sales window, grading, ask freshness,
  depth, roster, peers) is evaluated on its own. A failure in one dimension
  never hides facts from another.
- **Source and condition labels.** Sold data uses
  `source=pkmnprices_ebay_sold` and `conditionBasis=UNKNOWN_CONDITION`,
  because sold rows do not carry raw condition. Asks use
  `source=pkmnprices_tcgplayer_listings` and
  `conditionBasis=NEAR_MINT_LISTED`.

## 4. Exact identity (`fma_exact_identity_v1`)

**Instrument keys**
- Raw: `card:{card_variant_id}:raw`.
- Graded: `card:{card_variant_id}:graded:{GRADER}:{grade}:{qualifier|-}`.
  The grade and qualifier are percent-encoded opaque strings.

**A sold record counts toward an instrument only when all of these hold:**
1. Provider `attribution == "exact"`. The values `shared`, `unknown` and a
   missing attribution are all excluded.
2. The provider variant label is present and fully parsed. Unparsed tokens,
   such as `Staff Stamp`, are excluded.
3. Resolution runs against the **full sibling variant set** of the physical
   card (`candidateScope=FULL_CARD_VARIANT_SET`). A target-only list gives
   `CANDIDATE_SET_INCOMPLETE`.
4. Every dimension that could distinguish variants is stated by the provider:
   - If edition varies across siblings, or the matched candidate carries an
     edition the provider did not state, the result is
     `IDENTITY_EDITION_UNPROVEN`.
   - If printing varies and is unstated, the result is
     `IDENTITY_PRINTING_UNPROVEN`.
   - Special types, such as stamped cards, are unsupported.
5. The parser tests Non-Holo before Holo. The legacy order matched "Holo"
   inside "Non-Holo". This is covered by tests on 1st Edition, Unlimited,
   Shadowless, Reverse Holo and Non-Holo labels.
6. Currency is USD.

Legacy rows are evaluated with `evaluate_legacy_sold_row` and never
rewritten. The response reports the legacy verdict next to the V1 verdict.

Sold records are de-duplicated on `(source, providerCardId, listingId)`:
- Identical economics (price, currency, soldAt): the earliest-collected copy
  is kept, and the rest count as `EVIDENCE_DUPLICATE`.
- Conflicting economics: every copy is excluded as `EVIDENCE_CONFLICT`.

`excludedRecordCounts` counts each excluded record once, under its first
canonical reason.

## 5. Grading (`fma_grading_identity_v1`)

Grades are opaque strings. `"9.5"` stays `"9.5"`, and `"10.0"` does not equal
`"10"`. The ordinary grade pattern is `10` or `1`–`9` with an optional `.5`.

| Evidence | State | Certified tier? |
|---|---|---|
| No grader, grade or qualifier, and the provider did not flag the record as graded | `RAW` | yes |
| Grader and grade from `ACE`, `BGS`, `CGC`, `PSA`, `SGC` or `TAG`, with no qualifier | `GRADED` | yes |
| Grader and grade plus a registered qualifier (BGS Black Label; CGC Pristine/Perfect; TAG Pristine) | `GRADED_QUALIFIED` | yes, as its own tier |
| Missing grader or grade, a qualifier only, or a graded flag with no slab fields | `INCOMPLETE` | **no** (never falls back to raw) |
| Unknown grader, non-standard grade, or unregistered qualifier | `UNRECOGNIZED` | **no** (kept as an observed fact only) |

Raw and every graded tier have separate price distributions. A record from
another tier is excluded as `TIER_MISMATCH`.

## 6. Window readiness (`fma_window_readiness_v1`)

Windows are closed calendar ranges `[asOf − (d − 1), asOf]` for
d ∈ {7, 30, 90, 180}. The 30-day window ending 2026-09-29 is
2026-08-31..2026-09-29.

**A window is `PROVEN` only when all of these hold:**
- **Auditable walk.**
  - The sort is `date_desc`.
  - The walk starts from a known head (the first page has no input cursor, and
    `startedFromHead` is true).
  - The cursor chain is continuous: each page's input hash equals the previous
    page's output hash, and the previous page reported `hasMore`.
  - The filter fingerprint is identical on every page.
  - Sold dates do not increase from page to page.
- **Lower boundary.** The walk is exhausted, or the last fetched sold date is
  strictly earlier than the window start. A walk that stops **on** the start
  date gives `BOUNDARY_DATE_PARTIALLY_FETCHED` (`PARTIAL`). A walk that stops
  after the start date gives `LOWER_BOUNDARY_NOT_REACHED` (`UNPROVEN`).
  Lifetime exhaustion is **not** required.
- **Stream coverage.**
  - A `RAW_ONLY` stream proves only the raw tier.
  - A `COMBINED` stream proves all tiers only when
    `combinedSemanticsVerified` is true.
  - A `GRADE_FILTERED` stream proves only the tier with the same grader and
    grade, including every qualifier of that grade.
- **Right edge.** A completed reconciliation whose `reconciledThrough` falls
  on a date after the window end (otherwise `RIGHT_EDGE_DAY_OPEN`) and is at
  most 36 hours old (otherwise `RIGHT_EDGE_STALE`). A window record ingested
  after the reconciliation gives `LATE_INGESTION_AFTER_RECONCILIATION`.

Completeness is never inferred from the oldest stored date, the number of
stored records, or sync status `CURRENT`. `readiness_from_sync_state` always
returns `SYNC_STATUS_NOT_PROOF`.

**Response rules:**
- `observedCount` is shown whenever anything was collected, and is labelled.
- `provenCount` is non-null only when the window is `PROVEN`.
- `NOT_COLLECTED` makes both counts null.

**Checkpoints.** This bucket does not advance any collector watermark.
`checkpoint_advance_decision` freezes the rule for collectors:
- A `sold_desc` walk may advance only after it fully drains.
- An `ingested_asc` walk may advance only to a timestamp strictly below its
  last page's maximum, because rows with the same ingestion timestamp may
  continue on the next page.

## 7. Asks and supply provenance (`fma_supply_provenance_v1`)

- **Freshness** comes only from provider confirmation (`providerSnapshotAt`).
  Local collection time (`observedAt`) and `listingUpdatedAt` are reported but
  never prove freshness.
- **Effective confirmation** is the **oldest** valid per-offer confirmation.
  - A null confirmation gives `SOURCE_CONFIRMATION_MISSING`.
  - A confirmation more than 5 minutes in the future gives
    `SOURCE_CONFIRMATION_IN_FUTURE`, and that offer is excluded.
  - Differing confirmations give `SOURCE_CONFIRMATION_MIXED`.
  - The same confirmation as the previous snapshot gives
    `SOURCE_CONFIRMATION_REPEATED`.
- **Ask age.** If the effective confirmation is older than 24 hours, the state
  is `STALE` and `currentAsks` is unavailable. Observed prices are still shown,
  labelled.
- **Empty results.** An empty offer list gives `ZERO_PROVEN` only when the
  provider supplied its own `sourceConfirmedAt` and that confirmation is
  fresh. Otherwise the state is `ZERO_UNPROVEN`. A missing snapshot is
  `NOT_COLLECTED`, and a failed or missing run is `COLLECTION_FAILED`.
- **Depth.** `hasMore` means `depth=LOWER_BOUND`. Captured quantity is never
  total inventory.
- **Shipping provenance.** `EXPLICIT` (including explicit 0.00, which means
  free), `UNKNOWN`, or `LEGACY_UNVERIFIED`. `lowestAsk.basis` is:
  - `LANDED_PROVEN` only when every offer's shipping is explicit;
  - otherwise `ITEM_ONLY`, or `ITEM_ONLY_LEGACY_UNVERIFIED`.
- **Quantity provenance.** `EXPLICIT`, `DEFAULTED` or `LEGACY_UNVERIFIED`.
  The captured quantity is `PROVEN` only when every quantity is explicit.
  Otherwise it is `DEFAULTED_LOWER_BOUND` or `LEGACY_UNVERIFIED`.
- **Existing rows.** Rows written by the current normalizer have no provenance
  markers, so they stay `LEGACY_UNVERIFIED`. Provenance is never
  reconstructed.

## 8. Group membership (`fma_membership_v1`)

- **Mode.** V1 uses `CURRENT_ROSTER_RETROSPECTIVE`, labelled **"Activity for
  current constituents"**. Today's roster is applied to past windows. This is
  not point-in-time membership.
- **Roster fields.** Every roster carries `rosterAsOf`, `rosterRevision` and
  the full `rosterDenominator`. Coverage counts always use the full roster.
- **Accepted revisions.**
  - `SURFACE_V2_GENERATION` (`generationId` + `marketKey`). This is the active
    serving adapter: `market_explorer_surface_v2.read_v2_constituents`, which
    reads the immutable `pokemon_market_explorer_surface_constituents_v2`
    rows keyed by `(generation_id, market_key, rank)`.
  - `QUERY_CACHE_PUBLISHED_REVISION`, the FMA-1 sidecar described in
    `SCHEMA_DECISION.md`.
- **Rejected revision.** A bare query fingerprint
  (`QUERY_CACHE_FINGERPRINT`) gives `QUERY_FINGERPRINT_IS_NOT_A_REVISION`,
  because a fingerprint names a specification, not a snapshot.
- **Generation mismatch.** A request whose `generationId` differs from the
  served generation returns `GENERATION_MISMATCH`, and no data from the two
  generations is mixed.
- **Canonical query builder.** Activity never invokes
  `run_market_explorer_query`.

## 9. Metrics and peers

- **Price summary** covers one exact tier and one window. It needs at least 5
  records; fewer gives `THIN` and zero gives `NO_RECORDS`.
  - The median of an even count is the mean of the middle two, rounded
    half-even to cents.
  - `low` and `high` are the minimum and maximum.
- **Peer population key.**
  `{days}d|{source}|{currency}|{tier}|PROVEN`. Peers must match it exactly. The
  target is excluded from the denominator.
- **Activity percentile** (tie policy `midrank_v1`), labelled
  "Activity percentile": `(below + 0.5·ties) / N`.
- **Strict-below percentage.** `strictBelowPct` is the literal
  `below / N`. It never includes half the ties.
- **Peer states.**
  - `NO_PEERS`
  - `INSUFFICIENT_PEERS`: N < 30 other eligible peers.
  - `ALL_ZERO`: the target and all peers are 0.
  - `ALL_TIED`: all peers equal the target.
  - `UNAVAILABLE`: the target window is not proven.
  - `AVAILABLE`

  A zero target against non-zero peers is a valid position, and is
  `AVAILABLE`.
- **Scope label.** Peers are "Core Panel V1 research panel (modern,
  price-balanced)". `claimsAllPokemon` is always `false`.
- **Change versus a prior window** (`window_change`):
  - missing on either side: `UNAVAILABLE`;
  - both 0: `NO_ACTIVITY`;
  - baseline 0: `ZERO_BASELINE`, with no percentage;
  - otherwise a one-decimal percentage.

## 10. Named display and operations policy (`fma_display_policy_v1`)

These are configurable product thresholds. They are not scientific claims.

| Name | Default |
|---|---|
| `askConfirmationMaxAgeHours` | 24 |
| `soldHeadReceiptMaxAgeHours` | 36 |
| `priceSummaryMinRecords` | 5 |
| `percentileMinOtherPeers` | 30 |
| `futureTimestampSkewSeconds` | 300 |

## 11. Fixtures

`fixtures/manifest.json` records:
- the SHA-256 of the canonical JSON of each schema and each fixture, which
  does not depend on CRLF/LF or key order;
- the versions and the policy.

Each fixture holds `inputs` (synthetic data, never production data) and the
`expected` response. The tests re-run the pure assembler and require
byte-for-byte equality.

| Fixture | Scenario | Availability |
|---|---|---|
| 01 | fresh_complete | AVAILABLE |
| 02 | partial_sales | PARTIAL |
| 03 | stale_asks | PARTIAL |
| 04 | zero_with_proof | AVAILABLE |
| 05 | not_collected | PARTIAL |
| 06 | missing_grade | AVAILABLE (incomplete slabs excluded) |
| 07 | insufficient_peers | AVAILABLE (no percentile badge) |
| 08 | unsupported_asset | UNAVAILABLE |
| 09 | generation_mismatch | UNAVAILABLE |
| 10 | constituent_page | AVAILABLE |
| 11 | group_activity | PARTIAL |

To regenerate the fixtures (offline), run
`python -m backend.scripts.build_market_activity_v1_contract_artifacts --write`.
To check for drift, run the same command with `--check`.
