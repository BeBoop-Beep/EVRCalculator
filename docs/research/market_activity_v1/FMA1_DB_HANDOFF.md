# FMA-1 database and projection handoff

Status: implementation complete for review; no production migration, backfill,
schedule, provider request, deployment, merge, or serving promotion was run.

## Identity and authority

- Starting SHA: `8e86b6b3ab83422d95299107a66510a56ae5c336`
- Branch: `fma1-market-activity-db-projection`
- Implementation SHA: `2687a8996b1525a2e492ff0dbfd583f029f9072a`
- Reconciliation implementation SHA: `7d5359ca955c034f3031bcca33d744a9782c5a42`
- Final SHA: the PR head is authoritative (a commit cannot embed its own SHA)
- PR: https://github.com/BeBoop-Beep/EVRCalculator/pull/494
- Schema: `market_activity_projection_v1`
- Contract: `market_activity_v1.1`
- Domain: `market_activity_domain_v1.1.0`
- Fixtures: `market_activity_v1_fixtures_2`
- Canonical fixture manifest SHA-256:
  `e6235d9c73dc7ce6e38b81431bcfe60e4a32ae27f2780632aae45d407705e007`

## Changed implementation

The byte-identical migration
`20260930210000_market_activity_projection_v1.sql` exists in both migration
trees. It adds:

- immutable custom-query headers and members:
  `pokemon_market_explorer_query_cache_revisions_v1` and
  `pokemon_market_explorer_query_cache_revision_members_v1`;
- activity generation and independent serving authority:
  `market_activity_generations_v1`, `market_activity_serving_v1`;
- pinned roster headers/members: `market_activity_rosters_v1`,
  `market_activity_roster_members_v1`;
- exact-tier windows and asks: `market_activity_instrument_windows_v1`,
  `market_activity_instrument_asks_v1`;
- peer populations: `market_activity_peer_ranks_v1`;
- sparse series: `market_activity_daily_v1`,
  `market_activity_supply_daily_v1`,
  `market_activity_instrument_series_meta_v1`;
- compact contract read models: `market_activity_instrument_payloads_v1`,
  `market_activity_group_payloads_v1`.

Database functions are `promote_market_activity_generation_v1`,
`get_market_activity_group_v1`, `get_market_activity_instrument_v1`, and
`get_market_activity_constituent_page_v1`. The existing custom-query publisher
is transactionally replaced so a READY card build and its immutable revision
publish together. Sealed cache publication remains unchanged and creates no
FMA card revision. Application readers are in
`backend/db/services/market_activity_v1.py`.

The real service-role database adapters are
`SupabaseMarketActivitySource` and `SupabaseMarketActivitySink` in
`backend/db/services/market_activity_projection_repository.py`. The source
pins either the served V2 generation or a published custom revision; loads the
full sibling variant set, cutoff-bounded sold rows, sync/collection state,
optional real receipts, and completed/partial supply snapshots; and makes no
provider call. The sink stages generation, roster, normalized facts, and
payload rows and performs persisted-state reconciliation before validation.
The manual command supports `--plan` (read-only), explicitly confirmed
`--stage --confirm-stage FMA1_STAGE`, and fixture-only `--dry-run`. It never
promotes or schedules a generation.

No new secondary evidence index was added. Instrument, page, group, and sparse
series reads use primary-key prefixes. Builder scans use the existing sold
variant/date and supply variant indexes identified in the accepted schema
decision. At Core Panel scale, the normalized upper bound per raw tier is 828
window rows (207 x 4), 37,260 sparse sale-date rows (207 x 180 worst case), and
37,260 sparse supply-date rows. Actual sparse storage is bounded by observed or
proven dates and should be materially smaller.

## Consistency and generation proof

The builder captures a cutoff before evidence reads and requires its source
adapter to return only committed evidence first seen at or before that cutoff.
UUID order, `created_at`, `updated_at`, and maximum timestamps are not treated
as commit watermarks. The roster is pinned first by immutable surface
generation or custom revision ID. Custom READY publication and membership are
one database transaction.

Sold evidence is immutable and filtered by the first-seen cutoff. In-progress
walks do not prove completeness. Completed partial walks preserve observed
facts but remain partial/unproven; only valid bound receipts and explicit
boolean `hasMore=false` establish exhaustion. Late evidence after reconciliation
fails the domain right-edge rule. Supply includes only completed/partial source
runs pinned by ID and uses provider confirmation timestamps; running runs are
not a source snapshot. Missing collector receipts are never synthesized.

Rows are staged under `BUILDING`, checked against roster and domain invariants,
and become `VALIDATED` or `REJECTED`. Projection rows have update guards after
validation. Promotion locks the singleton, accepts only `VALIDATED`, verifies a
prepared generation still matches Explorer serving authority, retains the old
generation, and atomically swaps current/previous. Failure leaves the prior
generation serving. Tests and dry-run never promote.

The builder is bounded (`1..500` members per write batch) and deterministic for
a fixed generation/cutoff. Resume requires an existing `BUILDING` generation,
an identical cutoff and roster reference, the same market header, contiguous
unique ranks `1..resume_after_rank`, and complete payload/window/series-meta
facts for that prefix. Before `VALIDATED`, the sink rereads persisted state and
requires exactly `1..N`, the roster denominator, unique instruments/cards, one
payload and series envelope per member, and four exact window rows per member.
A fresh generation with a nonzero checkpoint is rejected before any write.
Requests read precomputed tables;
they never scan sold evidence, call PkmnPrices, or invoke the custom query
builder. The service re-evaluates expiring ask capabilities at read time.

## Validation evidence

Local commands and results:

- `python -m backend.scripts.build_market_activity_projection --dry-run`:
  19/19 accepted fixtures exactly reconciled and schema-validated; provider
  calls 0; production writes 0; wall time below 1 second locally.
- accepted FMA domain/contract/review tests plus focused projection/migration
  and bounded-reader tests: 158 passed in 1.90 seconds.
- adjacent sold/supply pipeline regressions: 59 passed in 3.18 seconds.
- migration mirrors are byte-equal; `git diff --check` passes.

The measured 207-member in-memory build uses 208 logical source loads (one
roster plus one bounded evidence bundle per member), five member batches at
size 50, plus sink writes. Instrument/group application reads use three calls:
generation pin, roster pin, and payload. Constituent pages also use exactly
three calls: generation pin, roster header, and one bounded joined RPC. Query
count tests measured 3 calls for 100, 207, and 990-member rosters; no full
roster or per-member payload reads occur.

PostgreSQL receipt: GitHub Actions run
https://github.com/BeBoop-Beep/EVRCalculator/actions/runs/36666290256 on an
ephemeral PostgreSQL 16 service emitted `FMA1_POSTGRES_VALIDATION_OK`. It
applied the relevant baseline and migration, verified byte-identical mirrors,
executed the custom card revision publisher, tested promotion and all three
RPCs, proved BUILDING/REJECTED payloads remain hidden, and transactionally
parsed the disable/drop rollback before rolling it back. `service_role`
successfully read protected tables; direct anon read/write and authenticated
read each failed with `permission denied`.

Actual `EXPLAIN (ANALYZE, BUFFERS)` results on the isolated one-row fixture:

- instrument: Result, shared buffers hit 4, execution 0.163 ms;
- group: Result, shared buffers hit 4, execution 0.161 ms;
- page: Function Scan, shared buffers hit 6, execution 0.305 ms.

These are syntax/access-path receipts, not production-scale latency claims. No
live Supabase or production database was queried.

## Apply, disable, and rollback

Apply only after review by running the mirrored migration through the normal
staging migration process, then execute role/RLS tests and EXPLAIN the three
reader functions. Do not point `market_activity_serving_v1` at a generation
until it is `VALIDATED` and separately approved.

Immediate disable is non-destructive: stop FMA builder/read routing and leave
the activity serving singleton unchanged or null. Rollback before data use may
drop the four functions, restore the prior query-cache publisher definition,
then drop new tables in reverse foreign-key order. After publication, prefer
disable over destructive rollback because revisions and retained generations
are cursor authority. Canonical pricing and Explorer serving pointers require
no rollback because this migration never mutates them.

## Known data limitations and collector dependencies

Current data has no accepted complete-window receipt authority. Observed exact
sales are displayable; `provenCount` and compatible peer ranks remain
unavailable until collectors publish valid walk and right-edge receipts.
Collector work must provide bound committed run IDs, typed cursor chains,
explicit pagination exhaustion, verified combined/filtered stream semantics,
and provider-confirmed supply timestamps/provenance. This bucket does not
advance watermarks, fabricate receipts, backfill, schedule, or spend provider
credits.
