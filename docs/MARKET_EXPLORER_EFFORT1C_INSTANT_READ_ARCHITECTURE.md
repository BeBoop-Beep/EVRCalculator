# Market Explorer Effort 1C: instant-read architecture gate

## Status and evidence boundary

Effort 1C cannot make an evidence-backed final authority decision yet because
Effort 1B is not deployed. Read-only production preflight on 2026-08-30 found
`PGRST205`/`PGRST202` for the interval table and all three Effort 1B RPCs. There
is consequently no interval cardinality, storage, refresh timing, interactive
plan, or interval-vs-fact benchmark to compare. No production DDL was applied.

The correct state is **decision deferred**, not a fabricated Decision B. The
repository now contains a non-deploying TEMP-table benchmark fixture at
`backend/research/market_explorer/effort1c_interval_vs_fact_benchmark.sql` so a
representative database can generate the missing evidence without creating a
persistent fact table first.

## Measured production baseline

Read-only REST measurements:

| Measurement | Result |
| --- | ---: |
| Canonical cards | 20,651 |
| Total `card_variants` | 40,654 |
| Previously resolved Market variants | 35,172 |
| Canonical Market dates | 140 |
| Full resolved fact upper bound | 4,924,080 rows |
| Existing Pokemon subject links | 17,244 |
| Existing prepared snapshot payload | 653,395 bytes |
| Existing prepared snapshot REST wall time | 236.56 ms |
| Exact raw observation count | timed out (`57014`, 8.118 s) |

The upper bound is variants multiplied by dates; actual fact rows will be lower
where a variant had no valid price yet. It is a sizing bound, not a claimed
post-materialization count. The existing prepared publication is already a
lookup, but one large mixed snapshot misses the new 10–50 ms aspiration and is
not a standardized exact-spec lookup.

Earlier committed production evidence for the legacy canonical interval path
showed 6,356 ms improving to 569 ms for a three-set bounded scan, while a
22-set scope still took 12.2 seconds and required a 1,570 MB covering source
index. Those measurements explain the daily-fact hypothesis but do not prove
the new variant interval table loses to facts.

## Candidate daily fact design

The benchmark candidate intentionally stays narrow:

- identity: `market_date`, `card_variant_id`, `canonical_card_id`, `set_id`,
  `era_id`;
- point-in-time measures: `market_price`;
- deterministic atomic dimensions: `rarity_segment`, `edition`,
  `printing_type`, `special_type`, `price_segment`, `release_age_segment`.

It omits condition because the table contract is exclusively authoritative
Near Mint USD. It omits names, images, legacy ID, and source from historical
rows because those are not filtering or index-math dimensions. Current Top 25
presentation can join compact current identity metadata. This avoids copying
wide display text across roughly five million rows.

Each fact row is expanded only across canonical READY/LEGACY_VERIFIED Market
dates covered by the interval's `[valid_from, valid_to)` range. Price segment is
calculated from that row's point-in-time price. Release age is calculated from
that row's market date and the set release date. There is no raw-observation
dependency, look-ahead, or projection of today's classifications backward.

## Current-state candidate

`pokemon_market_variant_current` should contain one latest canonical-Market row
per variant and mirror the narrow searchable dimensions. Current total/count
uses the full filtered population. A separate ordered query returns only the
Top 25 presentation rows by `market_price DESC, card_variant_id`; that limit
must never affect market arithmetic.

At the known resolved coverage its upper bound is 35,172 rows. Publication
should replace affected variants after the daily fact append, not scan history
on an interactive request.

## Pokemon many-to-many decision gate

Candidate default is **Option C**, an indexed `EXISTS` against
`pokemon_card_desirability_links` by canonical card and
`pokemon_reference_id`. The 17,244-row bridge is small, already durable, and
membership currently has no effective-date semantics. Copying arrays into five
million facts or creating a daily bridge would multiply timeless membership.
The fixture benchmarks this exact shape. Move to an undated variant/Pokemon
bridge only if its plan loses materially; use a daily bridge only if Pokemon
membership itself becomes point-in-time.

## Prepared resolution and cache target

Prepared equivalence already exists on the frontend for global Raw, Sealed,
card rarity, and sealed-family series. The final planner must move that
equivalence behind the API and key it by the same normalized, versioned query
fingerprint. Era/per-set prepared authorities must be inventoried from their
published snapshots before adding mappings; labels are not identities.

Recommended persistent custom cache is a hybrid:

- header keyed by `(query_contract_version, query_fingerprint)` with normalized
  spec, current aggregate, current Top 25, `computed_through`, request counters,
  last request/computation timestamps, and status;
- child table with one compact row per market date for basket/common-cohort
  inputs and the chain-linked value.

This avoids a large mutable JSON history while keeping current presentation a
single header read. Daily publication appends/upserts one child point and
updates the header. Methodology-version changes fingerprint apart. Cold entries
become lazy according to a documented operations policy; promotion thresholds
remain configuration, not hardcoded product behavior.

## Planner and concurrency contract

The asset-neutral planner order is:

1. exact versioned prepared equivalence;
2. current persistent cache hit;
3. one-date incremental cache update;
4. novel atomic fact intersection;
5. chain link;
6. persist header/history;
7. return the unchanged API contract.

Internal `executionSource` is one of `prepared`, `cache_hit`,
`cache_incremental`, or `novel_fact_query`. Cards use `card_variant_id`; Sealed
uses `sealed_product_id`. The normalized spec remains the future Prompt Bar's
only output—never arbitrary SQL.

The current API cache is process-local, limited to 128 entries, expires after
five minutes, and has no request coalescing. It cannot prevent a thundering herd
across workers. The persistent builder should use a unique cache identity plus
`pg_try_advisory_xact_lock` derived from the fingerprint. One request builds;
followers briefly re-read the cache and return the durable result rather than
launching identical calculations. Failed builders leave no `ready` generation.

## Security and asset boundaries

Fact/current/cache tables remain backend authorities with RLS enabled and all
privileges revoked from PUBLIC, `anon`, and `authenticated`; service role gets
only required operations. Existing API authentication, Index Plus entitlement,
abuse control, and `no-store` response boundary stay in force. Prepared Basic
projections remain separate. None of these facts replace
`pokemon_canonical_card_market_prices_latest`, whose one-card representative
semantics remain authoritative for Set Value.

Sealed should use the same planner/cache contract. Because its source volume is
small, a sealed daily/current fact is optional until its interval-vs-direct
benchmark shows material value; do not force Cards' storage shape onto it.

## Required acceptance run

After Effort 1B schema and a representative backfill:

1. run the TEMP fixture and record fact rows plus heap/index size;
2. run interval and fact shapes twice for every requested scope;
3. capture planning/execution time, rows, buffers, WAL, storage, and build time;
4. benchmark Option C Pokemon membership against array/bridge alternatives only
   if Option C is not already within target;
5. measure current aggregate/Top 25 and prepared/cache payload reads;
6. choose Decision A, B, or C from those results;
7. only then generate persistent migrations and wire the planner.

No new fact indexes are approved yet. The TEMP candidate uses four deliberately
limited indexes—variant/date uniqueness, set/date, era/date, and
date/classifications—so plans can show which earn their storage/write cost.
BRIN and GIN are excluded until measured evidence supports them.

## Effort 2 UX TODO (preserved verbatim in scope)

1. Clear Graph near timeframe buttons; one click removes every chart series.
2. Proper empty-chart state; Builder Clear remains separate.
3. Variant-aware First Edition, Unlimited, Holo, Reverse Holo, and special
   printing constituent labels.
4. Constituents before detailed Market Comparison Analysis.
5. Active Markets above Constituents; Market Comparison remains primary.
6. Expose variant/printing filters only after backend authority is stable.

