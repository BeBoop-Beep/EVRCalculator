# FMA V1 — schema decision (proposed for FMA-1, not applied)

Status: **proposal**. This bucket (FMA-0) creates no migration and applies
nothing. FMA-1 owns the DDL. It must keep the identity keys, generation rules
and reader shapes below, because the frozen fixtures and schemas depend on
them.

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
that flips `status` to `ready`. They are insert-only. A reader stores
`revision_id` in its page cursor.

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
  contract_version        text not null   -- 'market_activity_v1'
  domain_version          text not null   -- 'market_activity_domain_v1.0.0'
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

**Promotion rule.** Promotion is a single-row update of the singleton,
guarded so that only a `VALIDATED` generation whose `surface_generation_id`
equals the currently served V2 generation can be promoted.

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

**Validation.** `count(*)` per roster must equal `roster_denominator`, and
ranks must be contiguous. The same invariant is enforced in the V2 surface.

### D. Per-instrument facts

```
market_activity_instrument_windows_v1
  activity_generation_id uuid not null references market_activity_generations_v1 on delete cascade
  instrument_key         text not null
  window_days            smallint not null check (window_days in (7,30,90,180))
  card_variant_id        uuid not null
  tier                   text not null           -- 'RAW' | 'GRADED:PSA:10:-' ...
  start_date, end_date   date not null
  readiness_state        text not null check (readiness_state in ('PROVEN','PARTIAL','UNPROVEN','NOT_COLLECTED'))
  readiness_reasons      text[] not null default '{}'
  proven_lower_bound_date date, exhausted boolean not null, reconciled_through timestamptz
  observed_count         integer check (observed_count >= 0)
  proven_count           integer check (proven_count >= 0)
  summary_state          text check (summary_state in ('AVAILABLE','THIN','NO_RECORDS'))
  price_record_count     integer, median_price numeric(12,2), low_price numeric(12,2), high_price numeric(12,2)
  excluded_record_counts jsonb not null default '{}'
  evidence_fingerprint   text not null
  primary key (activity_generation_id, instrument_key, window_days)
  check (proven_count is null or readiness_state = 'PROVEN')
  check (readiness_state <> 'NOT_COLLECTED' or (observed_count is null and proven_count is null))

market_activity_instrument_asks_v1
  activity_generation_id uuid not null references market_activity_generations_v1 on delete cascade
  card_variant_id        uuid not null
  supply_snapshot_id     uuid references market_active_supply_snapshots_v1   -- null when NOT_COLLECTED
  ask_state              text not null check (ask_state in ('NOT_COLLECTED','COLLECTION_FAILED','CONFIRMATION_MISSING','CONFIRMATION_INVALID','STALE','FRESH','ZERO_PROVEN','ZERO_UNPROVEN'))
  ask_reasons            text[] not null default '{}'
  provider_confirmed_at  timestamptz, collected_at timestamptz
  captured_listing_count integer, captured_quantity integer, quantity_provenance text
  depth                  text check (depth in ('LOWER_BOUND','COMPLETE_AT_SOURCE'))
  lowest_ask_basis       text check (lowest_ask_basis in ('LANDED_PROVEN','ITEM_ONLY','ITEM_ONLY_LEGACY_UNVERIFIED'))
  lowest_ask_amount      numeric(12,2)
  primary key (activity_generation_id, card_variant_id)

market_activity_peer_ranks_v1
  activity_generation_id uuid not null references market_activity_generations_v1 on delete cascade
  instrument_key         text not null
  window_days            smallint not null
  population_key         text not null
  state                  text not null
  eligible_other_peer_count integer not null
  activity_percentile    numeric(4,1), strict_below_pct numeric(4,1), tie_count integer
  primary key (activity_generation_id, instrument_key, window_days)
```

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
4. Promote through the singleton. The serving pointer never mixes generations.
   Readers echo `activity_generation_id` in `evidenceFingerprint` and in the
   page cursor.
5. Rows are never updated after `VALIDATED`. A fix means a new generation.

## Reader shapes

The reader output must equal the JSON Schemas in `contracts/`:
- `instrument_detail_response`
- `constituent_page_response`
- `activity_response`

FMA-1 must pass every fixture in `fixtures/manifest.json` through its API
serializer, feeding stored rows that match each fixture's `expected` block.

## How FMA-1 and FMA-3 proceed independently

- **FMA-1 (database/API)** implements the tables above, the builder and the
  three endpoints. Its acceptance test: the serializer reproduces every
  fixture's `expected` document and validates against the schemas with
  `SchemaRegistry`.
- **FMA-3 (frontend)** builds against the committed fixtures only, served by a
  mock route or a static loader. The schemas fix every field, null behaviour,
  reason code and label. The frontend therefore needs no database, and it must
  render each availability state that the fixtures cover.
- **Handshake.** Both sides pin `contractVersion=market_activity_v1` and the
  manifest fingerprint. A contract change requires a new fixture set version.
