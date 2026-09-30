# Explorer Focused Market Activity V1 — contract (FMA-0, corrected in FMA-0.1)

Status: **frozen as the build target for FMA-1, FMA-2 and FMA-3** (ownership in
§2). Contract version `market_activity_v1.1`; domain
`market_activity_domain_v1.1.0`; fixture set `market_activity_v1_fixtures_2`.
Fixture set 1 (`market_activity_v1`, domain 1.0.0) is **superseded** by the
FMA-0.1 review closure (`FMA0_REVIEW_CLOSURE.md`) and must not be built
against.

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

**Rule versions** (`versions` in every response): identity
`fma_exact_identity_v1`, grading `fma_grading_identity_v1`, observation
`fma_sold_observation_v1`, window readiness `fma_window_readiness_v2`, supply
`fma_supply_provenance_v2`, series `fma_activity_series_v1`, tie policy
`midrank_v1`, peer population `fma_peer_population_v2`, membership
`fma_membership_v2`, cursor `fma_cursor_v1`.

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
through the instrument detail read.

## 2. Reads and bucket ownership

**Ownership.**
- **FMA-1** owns the database: tables, projections/builders and RPCs
  (`SCHEMA_DECISION.md`).
- **FMA-2** owns the public API: routes, auth/entitlement, transport and
  serialization of the stored projections into these schemas.
- **FMA-3** owns the UI, built against the committed fixtures only.
- **FMA-0/0.1** own only this contract, the pure domain, schemas, fixtures and
  tests. Nothing here implements FMA-1/2/3.

**Transport (agreed contract).** Reads are **structured POST** reads with a
JSON body. This matches the existing Explorer read routes
(`POST /market/explorer/prepared`, `POST /market/explorer/query/constituents`).
FMA-2 owns the exact prefix and auth; the body and response shapes are fixed:

| Read | Body schema | Response schema |
|---|---|---|
| `POST /market/explorer/activity` | `activity_request` | `activity_response` (`kind: groupActivity`) |
| `POST /market/explorer/activity/constituents` | `constituent_page_request` | `constituent_page_response` |
| `POST /market/explorer/activity/instrument` | `instrument_detail_request` | `instrument_detail_response` |

The FMA-0 draft listed these as `GET`; that is withdrawn. A GET equivalent is
allowed only with a documented, approved mapping of every body field.

**Every body carries three independent pins** plus `marketKey`, `asOf` (date)
and `windowDays` (7, 30, 90 or 180):

1. `activityGenerationId` — the immutable activity projection (FMA-1
   `market_activity_generations_v1`). It must equal the generation the reader
   resolves, else `ACTIVITY_GENERATION_MISMATCH`. A retired generation is
   `ACTIVITY_GENERATION_EXPIRED`: the client restarts from the first page
   against the currently served generation.
2. `rosterRef` — the immutable roster, prepared or custom (§8). It must equal
   the roster the activity generation was built on, else
   `ROSTER_REVISION_MISMATCH`.
3. For pages, `cursor` — opaque and revision-bound (§8), or `null` for the
   first page. `limit` is 1 to 100.

The group and instrument bodies also take `chartRange` (`{startDate,
endDate}` or `null`): the canonical chart range the series is drawn against.
The instrument body takes `instrumentKey`.

Every response carries `contractVersion`, `versions`, `policy`, `request`,
`evaluatedAt`, `activityGenerationId` (the validated pin, or `null` when the
read is `UNAVAILABLE`), `availability` and `evidenceFingerprint`.
`evidenceFingerprint` is always the **SHA-256** of the canonical evidence
inputs. It is never an activity UUID; the activity generation is echoed in
its own field.

## 3. Representation rules

- **Money** is `{"amount": "12.34", "currency": "USD"}`. The amount is a
  decimal string with exactly two places and never a float. Only USD is
  supported, and any other currency becomes `CURRENCY_UNSUPPORTED`.
- **Percentages** are one-decimal strings, such as `"57.1"`.
- **Timestamps** are UTC `YYYY-MM-DDTHH:MM:SSZ`, and **dates** are
  `YYYY-MM-DD`.
- **Null means "not established".**
  - `provenCount = 0` means proven zero activity.
  - `observedCount = 0` means a **known collection** holds no matching row.
    It is an observation, not proof of zero.
  - Any count or price is `null` when there is no collection evidence at all
    (`NOT_COLLECTED`). It is never `0`.
- **Reasons** are registered codes (`REASON_CODES`) emitted in canonical
  order and de-duplicated. The schema enum matches the registry exactly.
- **Availability** is `AVAILABLE`, `PARTIAL` or `UNAVAILABLE`.
  `UNAVAILABLE` is used only for request-level faults:
  - an unsupported asset;
  - a generation, activity-generation or roster mismatch;
  - an expired activity generation;
  - an invalid or mismatched cursor;
  - an invalid key;
  - an unstable roster revision, or a roster that fails integrity;
  - an instrument that is not in the roster.
- **Capabilities** are reported per feature as `{available, reasons}` for
  `saleCount`, `observedSales`, `salePriceSummary`, `activityPercentile`,
  `currentAsks`, `askDepth`, `landedAsk`, `supplyTurnover` and
  `inferredSalesFromListings`.
  - `currentAsks`, `askDepth` and `landedAsk` also carry `expiresAt` (§7).
  - `observedSales` is the explicit observed-facts capability: exact observed
    counts and dated observations. It never implies `saleCount`, which is the
    proven, complete-volume capability.
  - Each availability dimension (observation, identity, sales window, grading,
    ask freshness, depth, roster, peers) is evaluated on its own. A failure in
    one dimension never hides facts from another.
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

**Row validation comes before de-duplication.** A row without a
`providerCardId` or `listingId`, or with invalid money, an invalid sold date,
or an invalid ingestion or collection timestamp, is quarantined as
`INVALID_EVIDENCE_ROW` first. Such a row can never raise an error, collapse
into a valid listing, or conflict with one.

Valid rows are then de-duplicated on `(source, providerCardId, listingId)`:
- Identical economics (price, currency, soldAt): the earliest-collected copy
  is kept, compared by parsed instant, and the rest count as
  `EVIDENCE_DUPLICATE`.
- Conflicting economics: every copy is excluded as `EVIDENCE_CONFLICT`.

`excludedRecordCounts` counts each excluded record once, under its first
canonical reason. The counts are deterministic.

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

## 6. Observation and window readiness

### 6a. Observation (`fma_sold_observation_v1`)

Collection evidence is separate from completeness proof. `sales.observation`
is `{state, basis, reasons}`. The card is `OBSERVED` when there is, in order
of strength:
- `WALK_RECEIPT`: a committed walk receipt bound to the card's provider card;
- `COLLECTION_RECORD`: an explicit collection record for the provider card,
  such as a sync-state row;
- `STORED_ROWS`: stored evidence rows for the card.

Otherwise it is `NOT_COLLECTED`.

- **OBSERVED**
  - `observedCount` is the exact count of eligible rows in the window. It can
    be 0: a known collection with no matching row.
  - The price summary is computed over those rows and labelled
    `basis: OBSERVED_ONLY`, or `PROVEN_WINDOW` when the window is proven.
  - The dated observations appear in the series (§10).
  - Without a completeness receipt the window is `UNPROVEN` with
    `COMPLETENESS_RECEIPT_MISSING`, so `provenCount`, `saleCount`,
    `salePriceSummary` and peer ranks stay unavailable.
- **NOT_COLLECTED:** both counts and the summary are `null`.

This is the legacy-no-receipt beta case: fixture 12.

### 6b. Window readiness (`fma_window_readiness_v2`)

Windows are closed calendar ranges `[asOf − (d − 1), asOf]` for
d ∈ {7, 30, 90, 180}. The 30-day window ending 2026-09-29 is
2026-08-31..2026-09-29.

**A window is `PROVEN` only when all of these hold:**
- **Typed receipt.** Every page has:
  - an integer `pageIndex` equal to its position;
  - a non-negative integer `rowCount`;
  - a real boolean `hasMore`;
  - a non-empty `outputCursorHash` when `hasMore is true`, and none when it
    is `false`;
  - valid, ordered, non-future `minSoldAt`/`maxSoldAt` when it has rows;
  - no date bounds, and no `hasMore: true`, when it has zero rows.

  Otherwise the result is `WALK_RECEIPT_MALFORMED`. A non-boolean `hasMore`,
  including `null`, a missing value or `"false"`, is
  `WALK_PAGINATION_UNKNOWN`. **Unknown pagination is never exhaustion.**
- **Auditable walk.**
  - The sort is `date_desc`.
  - The walk starts from a known head: the first page has no input cursor,
    and `startedFromHead` is literally `true`.
  - The cursor chain is continuous: each page's input hash equals the previous
    page's output hash, and the previous page reported `hasMore: true`.
  - The filter fingerprint is identical on every page.
  - Sold dates do not increase from page to page.
- **Bound receipt.** The walk's `providerCardId` equals the instrument's
  provider card, and the walk names a `walkId` and `collectionRunId` with
  `committed: true`. Otherwise the result is `WALK_BINDING_MISMATCH`.
- **Lower boundary.** Either the walk is exhausted (`hasMore is false` on the
  last page), or the last fetched sold date is strictly earlier than the
  window start.
  - Stopping **on** the start date gives `BOUNDARY_DATE_PARTIALLY_FETCHED`
    (`PARTIAL`).
  - Stopping after the start date gives `LOWER_BOUNDARY_NOT_REACHED`
    (`UNPROVEN`).
  - Lifetime exhaustion is **not** required.
- **Stream coverage.**
  - A `RAW_ONLY` stream proves only the raw tier.
  - A `COMBINED` stream proves all tiers only when
    `combinedSemanticsVerified` is true.
  - A `GRADE_FILTERED` stream proves only the tier with the same grader and
    grade, including every qualifier of that grade.
- **Right edge.** A reconciliation proves the right edge only when all of
  these hold:
  - `completed` is literally `true`; a non-boolean value gives
    `RIGHT_EDGE_INVALID`.
  - `reconciledThrough` is valid and no later than `evaluatedAt` plus the
    policy skew. A later value gives `RIGHT_EDGE_IN_FUTURE`; for example, a
    2027 reconciliation at a 2026 evaluation is never proof (fixture 13).
  - It is bound to the same `providerCardId`, `stream`, `filterFingerprint`,
    `graderFilter`/`gradeFilter`, head walk (`headWalkId == walkId`) and
    committed `collectionRunId`. Otherwise the result is
    `RIGHT_EDGE_BINDING_MISMATCH`.
  - It falls on a date after the window end (otherwise
    `RIGHT_EDGE_DAY_OPEN`).
  - It is at most 36 hours old (otherwise `RIGHT_EDGE_STALE`).
  - No window record was ingested after it (otherwise
    `LATE_INGESTION_AFTER_RECONCILIATION`).

Completeness is never inferred from the oldest stored date, the number of
stored records, or sync status `CURRENT`. `readiness_from_sync_state` always
returns `SYNC_STATUS_NOT_PROOF`.

**Response rules:**
- `observedCount` is non-null whenever the card is `OBSERVED` (§6a), and is
  labelled.
- `provenCount` is non-null only when the window is `PROVEN`.
- `NOT_COLLECTED` makes both counts null.

**Checkpoints.** This bucket does not advance any collector watermark.
`checkpoint_advance_decision` freezes the rule for collectors:
- A `sold_desc` walk may advance only after it fully drains
  (`hasMore is false`). Unknown pagination never permits an advance.
- An `ingested_asc` walk may advance only to a timestamp strictly below its
  last page's maximum, because rows with the same ingestion timestamp may
  continue on the next page.

## 7. Asks and supply provenance (`fma_supply_provenance_v2`)

- **Freshness** comes only from provider confirmation (`providerSnapshotAt`).
  Local collection time (`observedAt`) and `listingUpdatedAt` are reported but
  never prove freshness.
- **Confirmed and unconfirmed offers.** An offer is *confirmed* when it has a
  valid provider confirmation that is not beyond the future skew.
  - An *unconfirmed* offer has a missing or unparseable confirmation
    (`SOURCE_CONFIRMATION_MISSING`), or one more than 5 minutes in the future
    (`SOURCE_CONFIRMATION_IN_FUTURE`). Its reason is
    `UNCONFIRMED_OFFERS_EXCLUDED`.
  - Unconfirmed offers **never** set `lowestAsk`, `capturedListingCount`,
    `capturedQuantity` or `depth`.
  - They are reported separately under `unconfirmedOffers` as
    `{count, futureCount, capturedQuantity, lowestAsk, reasons}`, with their
    shipping and quantity provenance kept.
- **Effective confirmation** is the **oldest** confirmed offer's
  confirmation. Differing confirmations give `SOURCE_CONFIRMATION_MIXED`. The
  same confirmation as the previous snapshot gives
  `SOURCE_CONFIRMATION_REPEATED`.
- **States.**
  - `FRESH` (current; `offerQualification: CURRENT`): every captured offer is
    confirmed and the effective confirmation is at most 24 hours old.
  - `PARTIALLY_CONFIRMED`: confirmed offers mixed with unconfirmed ones. Facts
    are last-known (`NOT_CURRENT`), and `currentAsks`, `askDepth` and
    `landedAsk` are withheld.
  - `STALE`: the effective confirmation is older than 24 hours. Observed
    prices are still shown, labelled `NOT_CURRENT`.
  - `CONFIRMATION_MISSING` or `CONFIRMATION_INVALID`: no confirmed offer.
- **Pagination.** `hasMore` must be a real boolean:
  - `true` gives `depth=LOWER_BOUND` (`DEPTH_TRUNCATED`);
  - `false` gives `COMPLETE_AT_SOURCE`, unless unconfirmed offers were
    excluded, which gives `LOWER_BOUND`;
  - anything else gives `depth=UNKNOWN` (`SUPPLY_PAGINATION_UNKNOWN`), and
    `askDepth` is unavailable.

  Captured quantity is never total inventory.
- **Empty results.** An empty offer list gives `ZERO_PROVEN` only when all of
  these hold: `hasMore is false`, the provider supplied its own
  `sourceConfirmedAt`, and that confirmation is fresh.
  - `hasMore: true` with no offers is contradictory: `ZERO_UNPROVEN`
    (`SUPPLY_PAGINATION_CONTRADICTORY`).
  - An unknown `hasMore` is `ZERO_UNPROVEN` (`SUPPLY_PAGINATION_UNKNOWN`).
  - Without a source confirmation: `ZERO_UNPROVEN`
    (`EMPTY_WITHOUT_SOURCE_FRESHNESS`).
  - A missing snapshot is `NOT_COLLECTED`, and a failed or missing run is
    `COLLECTION_FAILED`.
- **Capability expiry.**
  - `currentUntil` equals the effective confirmation plus 24 hours. It is set
    only for `FRESH` and `ZERO_PROVEN`.
  - `currentAsks`, `askDepth` and `landedAsk` carry it as `expiresAt`.
  - A reader serving a cached generation must re-evaluate at read time
    (`reevaluate_capabilities`). After `expiresAt`, the capability is
    unavailable with `ASKS_STALE`, so a cached generation never stays current
    indefinitely.
- **Shipping provenance.** `EXPLICIT` (including explicit 0.00, which means
  free), `UNKNOWN`, or `LEGACY_UNVERIFIED`. `lowestAsk.basis` is:
  - `LANDED_PROVEN` only when every counted offer's shipping is explicit;
  - otherwise `ITEM_ONLY`, or `ITEM_ONLY_LEGACY_UNVERIFIED`.
- **Quantity provenance.** `EXPLICIT`, `DEFAULTED` or `LEGACY_UNVERIFIED`.
  The captured quantity is `PROVEN` only when every quantity is explicit.
  Otherwise it is `DEFAULTED_LOWER_BOUND` or `LEGACY_UNVERIFIED`.
- **Existing rows.** Rows written by the current normalizer have no provenance
  markers, so they stay `LEGACY_UNVERIFIED`. Provenance is never
  reconstructed.

## 8. Membership, pins and pagination (`fma_membership_v2`, `fma_cursor_v1`)

- **Mode.** V1 uses `CURRENT_ROSTER_RETROSPECTIVE`, labelled **"Activity for
  current constituents"**. Today's roster is applied to past windows. This is
  not point-in-time membership.
- **Roster fields.** Every roster carries `rosterAsOf`, `rosterRevision` (the
  validated `rosterRef`) and the full `rosterDenominator`. Coverage counts
  always use the full roster.
- **Accepted `rosterRef` kinds.**
  - Prepared markets: `SURFACE_V2_GENERATION` (`generationId` +
    `marketKey`).
    - The active serving adapter is
      `market_explorer_surface_v2.read_v2_constituents`, which reads the
      immutable `pokemon_market_explorer_surface_constituents_v2` rows keyed
      by `(generation_id, market_key, rank)`.
    - `marketKey` must equal the ref's `marketKey`.
    - The ref's `generationId` must equal the served surface generation,
      otherwise `GENERATION_MISMATCH`.
  - Custom markets: `QUERY_CACHE_PUBLISHED_REVISION` (SHA-256
    `queryFingerprint` + immutable `revisionId` + `computedThrough`). This is
    the FMA-1 sidecar in `SCHEMA_DECISION.md`.
    - The request `marketKey` is `custom:{queryFingerprint}`.
    - The roster is read from the published revision members. The canonical
      query builder (`run_market_explorer_query`) is **never** invoked.
- **Rejected ref.** A bare query fingerprint (`QUERY_CACHE_FINGERPRINT`) gives
  `QUERY_FINGERPRINT_IS_NOT_A_REVISION`, because a fingerprint names a
  specification, not a snapshot.
- **Roster integrity.** A roster fails with `ROSTER_INTEGRITY_VIOLATION` unless
  all of these hold:
  - it has exactly `rosterDenominator` members;
  - ranks are unique and contiguous, `1..N`;
  - variants and instrument keys are unique.

  Members are always processed in rank order, whatever order they are
  supplied in.
- **Cursor.** `nextCursor` is an opaque string,
  `fmac1.<hex(canonical JSON)>.<check>`.
  - It binds the cursor version, `activityGenerationId`, the SHA-256 of
    `rosterRef`, `marketKey`, `asOf`, `windowDays` and the last rank served.
  - `limit` may change between pages.
  - A malformed or tampered cursor gives `CURSOR_INVALID`.
  - A cursor whose bindings differ from the request gives `CURSOR_MISMATCH`.
    This includes an activity refresh under an unchanged market generation,
    which is never allowed to mix pages (fixture 17).
  - A cursor lives exactly as long as its activity generation is `SERVING` or
    `RETAINED`. Once the generation is `RETIRED`, the read is
    `ACTIVITY_GENERATION_EXPIRED`, and the client restarts with
    `cursor: null` (fixture 18).
- **Page cap.** The UI page is capped at 100 rows. The cap applies only to
  constituent pages. Group aggregation always walks the full roster (fixture
  19 uses 101 members).

## 9. Metrics and peers (`fma_peer_population_v2`)

- **Price summary** covers one exact tier and one window. It needs at least 5
  records; fewer gives `THIN` and zero gives `NO_RECORDS`.
  - The median of an even count is the mean of the middle two, rounded
    half-even to cents.
  - `low` and `high` are the minimum and maximum.
- **Peer scope.** Every peer population names its cohort and that cohort's
  revision. There is no global panel.
  - `RESEARCH_PANEL`: the frozen Core Panel V1, with a `cohortRevision` naming
    the panel/evidence revision.
  - `MARKET_ROSTER`: the current constituents of this market. Its `rosterRef`
    must equal the response roster, and its `cohortRevision` must equal the
    pinned activity generation.

  The response carries `scope` and `scopeLabel`. `claimsAllPokemon` is always
  `false`.
- **Peer population key.**
  `{startDate}..{endDate}|{source}|{currency}|{tier}|PROVEN|{kind}:{scopeId}@{cohortRevision}`.
  Peers bind to the **actual dated window**; the same duration over other
  dates does not match. Peers must match the key exactly. The target is
  excluded from the denominator.
- **Unique peers.** The denominator counts unique peer instruments.
  - Repeated rows for one instrument with the same value count once
    (`duplicatePeerRowCount`).
  - An instrument with conflicting or invalid values is quarantined
    (`quarantinedPeerCount`) and never counts toward the 30-peer threshold.
- **Activity percentile** (tie policy `midrank_v1`), labelled
  "Activity percentile": `(below + 0.5·ties) / N`.
- **Strict-below percentage.** `strictBelowPct` is the literal
  `below / N`. It never includes half the ties.
- **Peer states.**
  - `NO_PEERS`
  - `INSUFFICIENT_PEERS`: N < 30 unique other eligible peers.
  - `ALL_ZERO`: the target and all peers are 0.
  - `ALL_TIED`: all peers equal the target.
  - `UNAVAILABLE`: the target window is not proven.
  - `AVAILABLE`

  A zero target against non-zero peers is a valid position, and is
  `AVAILABLE`.
- **Change versus a prior window** (`window_change`):
  - missing on either side: `UNAVAILABLE`;
  - both 0: `NO_ACTIVITY`;
  - baseline 0: `ZERO_BASELINE`, with no percentage;
  - otherwise a one-decimal percentage.

## 10. Dated chart series (`fma_activity_series_v1`)

The focused graph's synchronized activity pane reads `series`. It is present
on the instrument detail and on the group response. Window totals are
summaries only, and **must never be drawn at, or repeated onto, a historic
hover date.**

**Envelope** (both responses): `version`, `storage: SPARSE_DAILY`, `asOf`,
`zeroRule: ABSENT_DATE_IS_ZERO_ONLY_INSIDE_PROVEN_SPAN`,
`outsideActivityRange: NOT_COLLECTED`, `canonicalRange` (the request
`chartRange`, or null) and `activityRange` (`[asOf − 179, asOf]`).

**Sparse daily storage.** A point exists only for a date that holds at least
one observation. The planned FMA-1 projection
`market_activity_daily_v1` (`SCHEMA_DECISION.md` §E) stores exactly these
rows and no zero rows.

**Zero versus missing.**
- A sales-count date with no point is **zero only inside `provenSpan`**, the
  widest PROVEN window.
- Everywhere else inside `activityRange`, a date with no point is
  **missing**, drawn as a gap.
- Every date of the canonical range outside `activityRange` is
  `NOT_COLLECTED`. For example, a 365-day price chart shows no activity before
  `activityRange.startDate` (fixture 15).
- Supply is never zero-filled or carried forward. A `ZERO_PROVEN` snapshot is
  an explicit `0` point.

**Separate axes.** Each axis is its own object with a fixed `unit`, and
dollars, counts and quantities never share one:

| Series | Unit | Point fields |
|---|---|---|
| `sales.counts` | `SALE_COUNT` | `date`, `observedCount` (≥1), `proofState` (`PROVEN` inside `provenSpan`, else `OBSERVED_ONLY`), `firstIngestedAt`, `lastIngestedAt`, `ingestedAfterReconciliation` (true/false; null without reconciliation) |
| `sales.prices` (instrument only) | `USD` | `date`, `recordCount`, `low`, `median`, `high` |
| `supply.listings` | `LISTING_COUNT` | `date`, `providerConfirmedAt`, `firstCollectedAt`, `lastCollectedAt`, `collectionCount`, `confirmationsOnDate`, `stateAtCollection`, `depth`, `value` |
| `supply.quantity` | `LISTED_QUANTITY` | `date`, `providerConfirmedAt`, `provenance`, `value` |
| `supply.lowestAsk` (instrument only) | `USD` | `date`, `providerConfirmedAt`, `basis`, `price` |

**Source timestamps and supply dating.**
- Sales points carry their ingestion bounds.
- A supply point is dated by the **provider confirmation**, never by local
  collection time.
- Each snapshot is evaluated at its own collection time.
- A repeated source confirmation (the same `providerConfirmedAt` collected
  again) is one point with `collectionCount > 1`. It is not new evidence.
- Snapshots with no valid confirmation are excluded and counted in
  `excludedSnapshots.byStateAtCollection`. Confirmations outside
  `activityRange` are counted in `excludedSnapshots.outsideActivityRange`.
  Current asks confirmed after `asOf` appear only in `asks`.

**Group series.**
- Sums over the **full roster**.
- Each point carries `contributingConstituents` and `provenConstituents`.
- `provenSpan` is the intersection of every constituent's proven span. It is
  null unless all constituents are proven.
- The group has **no dollar axis**, because a group has no single price.
- Group supply is labelled
  `LOWER_BOUND_SUM_OF_CONFIRMED_CONSTITUENT_SNAPSHOTS`.

## 11. Named display and operations policy (`fma_display_policy_v1`)

These are configurable product thresholds. They are not scientific claims.

| Name | Default |
|---|---|
| `askConfirmationMaxAgeHours` | 24 |
| `soldHeadReceiptMaxAgeHours` | 36 |
| `priceSummaryMinRecords` | 5 |
| `percentileMinOtherPeers` | 30 |
| `futureTimestampSkewSeconds` | 300 |

## 12. Fixtures

`fixtures/manifest.json` records:
- the SHA-256 of the canonical JSON of each schema and each fixture, which
  does not depend on CRLF/LF or key order;
- the versions and the policy.

Each fixture holds `inputs` (synthetic data, never production data) and the
`expected` response. The tests re-run the pure assembler and require
exact equality. They also validate each request body and each response
against its schema.

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
| 10 | constituent_page | AVAILABLE (opaque next cursor) |
| 11 | group_activity | PARTIAL (group series, 365-day canonical range) |
| 12 | legacy_no_receipts | PARTIAL (observed counts kept, proof unavailable) |
| 13 | future_right_edge | PARTIAL (future reconciliation is not proof) |
| 14 | mixed_unconfirmed_asks | PARTIAL (unconfirmed $1 offer never current) |
| 15 | multi_date_series | PARTIAL (gaps, late ingestion, repeated confirmation, proven-zero supply, 365 > 180 days) |
| 16 | constituent_page_cursor | AVAILABLE (second page through the cursor) |
| 17 | cursor_mismatch | UNAVAILABLE (activity refresh cannot mix pages) |
| 18 | activity_generation_expired | UNAVAILABLE |
| 19 | group_roster_101 | PARTIAL (full-roster aggregation above the page cap) |

To regenerate the fixtures (offline), run
`python -m backend.scripts.build_market_activity_v1_contract_artifacts --write`.
To check for drift, run the same command with `--check`.
