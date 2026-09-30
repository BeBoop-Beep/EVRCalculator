# FMA V1 — schema decision (proposed for FMA-1, not applied)

Status: **proposal**, corrected by FMA-0.1 (`FMA0_REVIEW_CLOSURE.md`). This
bucket (FMA-0/0.1) creates no migration and applies nothing.

**Ownership.**
- **FMA-1** owns the database: DDL, projections/builders and RPCs.
- **FMA-2** owns the public API: structured POST read routes, auth and
  entitlement, transport and serialization.
- **FMA-3** owns the fixture-backed UI.

FMA-1 must keep the identity keys, generation rules and stored shapes below,
and FMA-2 must keep the reader shapes, because the frozen fixtures and schemas
(fixture set `market_activity_v1_fixtures_2`, contract `market_activity_v1.1`)
depend on them.

## Decision summary

1. **Activity is a generation-pinned, precomputed read model.**
   - Request-time reads never scan sold evidence or supply listings.
   - Request-time reads never invoke the heavy canonical query builder
     (`run_market_explorer_query`).
   - A builder evaluates the pure domain (`market_activity.py`) once per
     activity generation and writes immutable rows.
2. **Every activity generation pins exactly one roster revision**, from one of
   two sources:
   - the V2 surface generation that the Explorer serves (the active adapter,
     `market_explorer_surface_v2.read_v2_constituents`); or
   - a published custom-query revision from the sidecar below.

   A bare query fingerprint is never accepted as a revision.
3. **Every table is additive and new.**
   - No existing evidence table is altered.
   - No legacy row is rewritten, backfilled or re-classified in place.
   - Legacy sold and ask rows are evaluated at build time under V1 rules, and
     their results are stored only in the new activity tables.
4. **Grants.**
   - RLS is enabled on every table.
   - `REVOKE ALL` from `PUBLIC`, `anon` and `authenticated`.
   - `service_role` gets only the verbs the builder needs: insert on the
     generation's tables, and update on the generation/serving rows only.
   - The public read path goes through the backend API, as the prepared
     Explorer surfaces already do.

## Audit: why a fingerprint is not a revision

`pokemon_market_explorer_query_cache` is keyed by `query_fingerprint`
(`UNIQUE`). The table has one row per specification, and a rebuild replaces
that row in place.

Trigger `trg_sync_market_explorer_query_cache_constituents` runs
`DELETE ... WHERE query_fingerprint = NEW.query_fingerprint` followed by
`INSERT` into `pokemon_market_explorer_query_cache_constituents`, which is
keyed by `(query_fingerprint, rank)`.

`get_pokemon_market_explorer_query_cache_constituent_page(p_query_fingerprint,
p_limit, p_after_rank)` has no revision parameter. As a result:

- Page 1 read before a rebuild and page 2 read after it can mix two different
  rosters. Nothing detects this.
- `computed_through` is a freshness watermark, not an identity. Two builds on
  the same date can differ.
- `updated_at` is documented as not being publication freshness.

The V2 prepared surface does not have this problem:
- `pokemon_market_explorer_surface_constituents_v2` is keyed by
  `(generation_id, market_key, rank)`.
- A generation is promoted through the `pokemon_market_explorer_surface_serving_v2`
  singleton, and its rows are not mutated afterwards.
- The reader returns `GENERATION_MISMATCH` rather than mixing generations.

Activity V1 therefore reuses V2 generation pinning.

## Proposed tables

### A. Custom-query roster sidecar (makes custom markets pinnable)

```
pokemon_market_explorer_query_cache_revisions_v1
  revision_id          uuid primary key default gen_random_uuid()
  query_fingerprint    text not null references pokemon_market_explorer_query_cache(query_fingerprint)
  computed_through     date not null
  constituent_count    integer not null check (constituent_count >= 0)
  build_token          uuid not null            -- the lease that produced it
  published_at         timestamptz not null default clock_timestamp()
  unique (query_fingerprint, build_token)

pokemon_market_explorer_query_cache_revision_members_v1
  revision_id          uuid not null references ..._revisions_v1 on delete restrict
  rank                 integer not null check (rank >= 1)
  card_variant_id      uuid not null
  item                 jsonb not null
  primary key (revision_id, rank)
  unique (revision_id, card_variant_id)
```

**Generation rule.** Revision rows are written *inside*
`publish_pokemon_market_explorer_query_cache_build`, in the same transaction
that flips `status` to `ready`. They are insert-only.

**Custom-market mapping.**
- A custom market is requested as `marketKey = custom:{query_fingerprint}` with
  `rosterRef = {kind: QUERY_CACHE_PUBLISHED_REVISION, queryFingerprint,
  revisionId, computedThrough}`.
- The reader resolves members from `..._revision_members_v1` by
  `revision_id`. It never invokes `run_market_explorer_query`.
- The page cursor binds the SHA-256 of that `rosterRef` (CONTRACT §8).

**Indexes.** Only the two keys above. The PK serves rank pagination. The
unique key serves `INSTRUMENT_NOT_IN_ROSTER` checks and prevents duplicate
members.

**Retention.** Keep a revision while any activity generation references it.
Prune older ones by `published_at` in a later reviewed job.

### B. Activity generations and serving pointer

```
market_activity_generations_v1
  activity_generation_id  uuid primary key default gen_random_uuid()
  as_of                   date not null
  surface_generation_id   uuid null references pokemon_market_explorer_surface_generations_v2
  query_revision_id       uuid null references pokemon_market_explorer_query_cache_revisions_v1
  roster_ref              jsonb not null  -- the exact rosterRef readers must echo
  contract_version        text not null   -- 'market_activity_v1.1'
  domain_version          text not null   -- 'market_activity_domain_v1.1.0'
  serving_state           text not null check (serving_state in ('SERVING','RETAINED','RETIRED'))
  policy                  jsonb not null  -- DisplayPolicy.as_contract()
  fixture_manifest_sha256 text not null check (fixture_manifest_sha256 ~ '^[0-9a-f]{64}$')
  sold_evidence_through   timestamptz     -- max reconciled right edge used
  supply_run_ids          uuid[] not null default '{}'
  state                   text not null check (state in ('BUILDING','VALIDATED','REJECTED','RETIRED'))
  diagnostics             jsonb not null default '{}'
  created_at, built_at, validated_at timestamptz

market_activity_serving_v1
  singleton smallint primary key default 1 check (singleton = 1)
  activity_generation_id uuid references market_activity_generations_v1
  previous_activity_generation_id uuid references market_activity_generations_v1
  promoted_at timestamptz
```

**Promotion rule.** Promotion is a single-row update of the singleton. It is
guarded so that only a `VALIDATED` generation whose `surface_generation_id`
equals the currently served V2 generation can be promoted.

**Pins and expiry (activity generation versus market generation).**
- An activity refresh creates a new `activity_generation_id` even when the
  surface/market generation is unchanged. The activity pin is therefore
  independent of `generationId`.
- On promotion the previous generation becomes `RETAINED`. Readers keep
  serving pages for a `RETAINED` generation so that in-flight pagination
  completes on one generation.
- A later job marks old generations `RETIRED`. Reads pinned to them return
  `ACTIVITY_GENERATION_EXPIRED`.
- A cursor from one activity generation is `CURSOR_MISMATCH` under another.

### C. Rosters

```
market_activity_rosters_v1
  activity_generation_id uuid not null references market_activity_generations_v1 on delete cascade
  market_key             text not null
  roster_revision        jsonb not null   -- {kind, generationId, marketKey} or {kind, queryFingerprint, revisionId, computedThrough}
  roster_as_of           date not null
  roster_denominator     integer not null check (roster_denominator >= 0)
  primary key (activity_generation_id, market_key)

market_activity_roster_members_v1
  activity_generation_id uuid not null
  market_key             text not null
  rank                   integer not null check (rank >= 1)
  instrument_key         text not null    -- card:{uuid}:raw in V1 rosters
  card_variant_id        uuid not null
  primary key (activity_generation_id, market_key, rank)
  unique (activity_generation_id, market_key, instrument_key)
  foreign key (activity_generation_id, market_key) references market_activity_rosters_v1
```

**Validation.** `count(*)` per roster must equal `roster_denominator`. Ranks
must be unique and contiguous (`1..N`), and variants and instrument keys must
be unique. The same invariant is enforced in the V2 surface and by
`validate_members` (`ROSTER_INTEGRITY_VIOLATION`). Group aggregation reads the
full roster, never one 100-row page.

### D. Per-instrument facts

```
market_activity_instrument_windows_v1
  activity_generation_id uuid not null references market_activity_generations_v1 on delete cascade
  instrument_key         text not null
  window_days            smallint not null check (window_days in (7,30,90,180))
  card_variant_id        uuid not null
  tier                   text not null           -- 'RAW' | 'GRADED:PSA:10:-' ...
  start_date, end_date   date not null
  observation_state      text not null check (observation_state in ('OBSERVED','NOT_COLLECTED'))
  observation_basis      text check (observation_basis in ('WALK_RECEIPT','COLLECTION_RECORD','STORED_ROWS'))
  readiness_state        text not null check (readiness_state in ('PROVEN','PARTIAL','UNPROVEN','NOT_COLLECTED'))
  readiness_reasons      text[] not null default '{}'
  proven_lower_bound_date date, exhausted boolean not null, reconciled_through timestamptz
  observed_count         integer check (observed_count >= 0)
  proven_count           integer check (proven_count >= 0)
  summary_state          text check (summary_state in ('AVAILABLE','THIN','NO_RECORDS'))
  summary_basis          text check (summary_basis in ('PROVEN_WINDOW','OBSERVED_ONLY'))
  price_record_count     integer, median_price numeric(12,2), low_price numeric(12,2), high_price numeric(12,2)
  excluded_record_counts jsonb not null default '{}'
  evidence_fingerprint   text not null check (evidence_fingerprint ~ '^[0-9a-f]{64}$')  -- SHA-256
  primary key (activity_generation_id, instrument_key, window_days)
  check (proven_count is null or readiness_state = 'PROVEN')
  check ((observation_state = 'NOT_COLLECTED') = (observed_count is null))
  check (observation_state = 'OBSERVED' or proven_count is null)

market_activity_instrument_asks_v1
  activity_generation_id uuid not null references market_activity_generations_v1 on delete cascade
  card_variant_id        uuid not null
  supply_snapshot_id     uuid references market_active_supply_snapshots_v1   -- null when NOT_COLLECTED
  ask_state              text not null check (ask_state in ('NOT_COLLECTED','COLLECTION_FAILED','CONFIRMATION_MISSING','CONFIRMATION_INVALID','STALE','PARTIALLY_CONFIRMED','FRESH','ZERO_PROVEN','ZERO_UNPROVEN'))
  ask_reasons            text[] not null default '{}'
  provider_confirmed_at  timestamptz, collected_at timestamptz
  current_until          timestamptz      -- confirmation + policy age; readers re-evaluate against it
  offer_qualification    text not null check (offer_qualification in ('CURRENT','NOT_CURRENT'))
  captured_listing_count integer, captured_quantity integer, quantity_provenance text   -- confirmed offers only
  depth                  text check (depth in ('LOWER_BOUND','COMPLETE_AT_SOURCE','UNKNOWN'))
  lowest_ask_basis       text check (lowest_ask_basis in ('LANDED_PROVEN','ITEM_ONLY','ITEM_ONLY_LEGACY_UNVERIFIED'))
  lowest_ask_amount      numeric(12,2)    -- confirmed offers only
  unconfirmed_offers     jsonb            -- {count, futureCount, capturedQuantity, lowestAsk, reasons}; never current
  primary key (activity_generation_id, card_variant_id)
  check (current_until is null or ask_state in ('FRESH','ZERO_PROVEN'))

market_activity_peer_ranks_v1
  activity_generation_id uuid not null references market_activity_generations_v1 on delete cascade
  instrument_key         text not null
  window_days            smallint not null
  population_key         text not null    -- {start}..{end}|source|currency|tier|PROVEN|{kind}:{scopeId}@{cohortRevision}
  scope_kind             text not null check (scope_kind in ('RESEARCH_PANEL','MARKET_ROSTER'))
  scope_id               text not null
  cohort_revision        text not null
  state                  text not null
  eligible_other_peer_count integer not null   -- UNIQUE peer instruments
  quarantined_peer_count integer not null default 0
  duplicate_peer_row_count integer not null default 0
  activity_percentile    numeric(4,1), strict_below_pct numeric(4,1), tie_count integer
  primary key (activity_generation_id, instrument_key, window_days)
```

### E. Sparse daily activity projection (the chart series)

```
market_activity_daily_v1                   -- sold observations, one row per observed date
  activity_generation_id uuid not null references market_activity_generations_v1 on delete cascade
  instrument_key         text not null
  activity_date          date not null
  observed_count         integer not null check (observed_count >= 1)   -- sparse: never a zero row
  proof_state            text not null check (proof_state in ('PROVEN','OBSERVED_ONLY'))
  first_ingested_at, last_ingested_at timestamptz
  ingested_after_reconciliation boolean
  record_count           integer not null, low_price numeric(12,2) not null,
  median_price           numeric(12,2) not null, high_price numeric(12,2) not null
  primary key (activity_generation_id, instrument_key, activity_date)

market_activity_supply_daily_v1            -- offered supply, one row per provider-confirmation date
  activity_generation_id uuid not null references market_activity_generations_v1 on delete cascade
  card_variant_id        uuid not null
  activity_date          date not null     -- date of provider_confirmed_at, never of collection
  provider_confirmed_at  timestamptz not null
  first_collected_at, last_collected_at timestamptz not null
  collection_count       integer not null check (collection_count >= 1)   -- repeated confirmations
  confirmations_on_date  integer not null check (confirmations_on_date >= 1)
  state_at_collection    text not null, depth text
  listing_count          integer not null, listed_quantity integer not null, quantity_provenance text not null
  lowest_ask_basis       text, lowest_ask_amount numeric(12,2)
  primary key (activity_generation_id, card_variant_id, activity_date)

market_activity_instrument_series_meta_v1  -- per-instrument series envelope
  activity_generation_id uuid not null, instrument_key text not null
  proven_span_start, proven_span_end date   -- null unless a window is PROVEN
  reconciled_through     timestamptz
  excluded_supply_snapshots jsonb not null default '{}'
  primary key (activity_generation_id, instrument_key)
```

**Zero versus missing (storage rule).**
- No zero rows are ever stored.
- A date without a row is zero only inside the stored proven span. Otherwise
  it is missing.
- Dates outside `[as_of − 179, as_of]` are `NOT_COLLECTED`.
- Supply dates without a row are missing and never carried forward. A proven
  empty snapshot is stored as an explicit row with `listing_count = 0`.
- Group series are aggregated from these rows over the full roster at build
  time, or by the reader over a primary-key prefix scan. They never repeat
  window totals onto dates.

**Indexes.** Every reader query is a primary-key prefix scan:

| Reader | Access path |
|---|---|
| Instrument detail | `(gen, instrument_key)` on windows and peers; `(gen, card_variant_id)` on asks |
| Constituent page | roster members by `(gen, market_key, rank > after)`, then PK lookups |
| Group activity | the same roster scan, aggregated |

No secondary index is justified at V1 volume: the Core Panel is 207 variants,
so at most 207 × 4 window rows per tier. For the builder's evidence scans:
- sold evidence is read through the existing
  `pkmnprices_ebay_sold_evidence_v1_variant_sold_idx`;
- supply is read through `market_active_supply_snapshots_variant_idx`.

Add a reviewed index only if FMA-1 `EXPLAIN` output shows a need.

## Build (generation) rules

1. Pin the currently served V2 generation, or a sidecar revision, together
   with `as_of`.
2. For every roster member and requested tier:
   - load evidence with bounded, batched reads;
   - load the walk receipts and right-edge receipts from the collector tables
     (see `COLLECTOR_HANDOFF.md`);
   - load the resolved full sibling variant set;
   - call `assemble_instrument_detail`.
3. Persist rows, then validate:
   - roster denominators;
   - the proven/null invariants;
   - reason codes are a subset of the registry;
   - `fixture_manifest_sha256` equals the committed manifest.

   A failed validation marks the generation `REJECTED`.
4. Promote through the singleton. The serving pointer never mixes
   generations.
   - Readers echo `activity_generation_id` in the response field
     `activityGenerationId`, and bind it inside the opaque page cursor.
   - `evidenceFingerprint` stays the SHA-256 of the canonical evidence
     inputs, stored per row as `evidence_fingerprint`. It is never an
     activity UUID.
5. Rows are never updated after `VALIDATED`. A fix means a new generation.

## Reader shapes

The reader output must equal the JSON Schemas in `contracts/`:
- `instrument_detail_response`
- `constituent_page_response`
- `activity_response`

FMA-1 must pass every fixture in `fixtures/manifest.json` through its API
serializer, feeding stored rows that match each fixture's `expected` block.

## How FMA-1, FMA-2 and FMA-3 proceed independently

- **FMA-1 (database/projections/RPCs)** implements the tables above
  (including §E), the builder and read RPCs keyed by
  `activity_generation_id`. Its acceptance test: the stored rows round-trip
  every fixture's `expected` document.
- **FMA-2 (public API/auth/transport)** implements the three structured POST
  reads (CONTRACT §2), auth and entitlement, pin validation, cursor handling
  and capability re-evaluation at read time (`reevaluate_capabilities`). Its
  acceptance test: the serializer reproduces every fixture's `expected`
  document and validates against the schemas with `SchemaRegistry`.
- **FMA-3 (UI)** builds against the committed fixtures only, served by a mock
  route or a static loader.
  - The schemas fix every field, null behaviour, reason code, label and series
    axis. The UI therefore needs no database.
  - It must render each availability state that the fixtures cover.
  - It must follow the series zero-versus-missing and hover rules
    (CONTRACT §10).
- **Handshake.** All three pin `contractVersion=market_activity_v1.1`, fixture
  set `market_activity_v1_fixtures_2` and the manifest fingerprint. A contract
  change requires a new fixture set version.
