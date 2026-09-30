# FMA-2 authenticated API handoff

Status: implementation complete for review. No production migration, activity
build/promotion, provider request, deployment, schedule change, or merge was
performed.

## Delivery identity

- Starting SHA: `0689a04de41379da670fc8f1787d6548a11d6f12`
- Branch: `fma2-market-activity-api`
- Final SHA: the PR head is authoritative (a commit cannot embed its own SHA)
- Implementation SHA: `66fb824393bf0f8e5983324a7f5b4a68df774207`
- Reconciliation implementation SHA: `79c433b6634fcd74b0b0a49cd99700acd8956cda`
- PR: https://github.com/BeBoop-Beep/EVRCalculator/pull/499
- Contract: `market_activity_v1.1`
- Domain: `market_activity_domain_v1.1.0`
- Projection: `market_activity_projection_v1`
- Fixture set: `market_activity_v1_fixtures_2`
- Fixture manifest SHA-256: `e6235d9c73dc7ce6e38b81431bcfe60e4a32ae27f2780632aae45d407705e007`

## Public transport

All routes are authenticated structured POST reads and return
`Cache-Control: private, no-store`:

- `/market/explorer/activity/capabilities`
- `/market/explorer/activity`
- `/market/explorer/activity/constituents`
- `/market/explorer/activity/instrument`

The three data reads validate requests and responses with
`SchemaRegistry` against, respectively, `activity_*`, `constituent_page_*`,
and `instrument_detail_*` committed schemas. Extra fields are rejected.
Routes return only the curated contract DTOs and never import or call provider
collectors or `run_market_explorer_query`.

Capability discovery accepts 1..10 `{focusKey, marketKey, rosterRef}` entries,
further bounded by the authenticated plan's active-market limit, and one of
7/30/90/180 days. Duplicate frontend identities or market keys are invalid.
It batch-resolves each market's independently published current
`VALIDATED`/`SERVING` Activity generation, checks every prepared generation's
surface pin against the current Explorer surface, compares
the requested immutable roster reference exactly, requires a persisted group
payload for the window, and copies `evidenceFingerprint` only from that
payload. Bare custom query fingerprints are never resolved to a newest
revision and therefore return unavailable.

## Authentication and entitlement

The named `_require_market_activity_access` helper enforces the order:
authenticate the repository token authority, resolve `index_plan` from the
server-side profile, authorize the plan, then allow Activity reads. Anonymous
requests return 401; Basic/no-paid-plan requests return 403. Index Plus and
Premium can read prepared card Activity. Any `custom:` market requires Premium,
as does any request whose authoritative `rosterRef.kind` is
`QUERY_CACHE_PUBLISHED_REVISION`, regardless of market-key spelling.
No client plan, user id, or capability flag is accepted. Tests prove denied
requests cause zero Activity reader calls.

## Status and error mapping

- Invalid request or extra field: HTTP 400,
  `MARKET_ACTIVITY_REQUEST_INVALID`.
- Repository authentication failures: existing HTTP 401 patterns.
- Insufficient plan: HTTP 403, `MARKET_ACTIVITY_PLAN_REQUIRED`.
- Valid but unavailable generation, roster, cursor, or instrument: HTTP 200
  with the contract-defined `UNAVAILABLE` response.
- Reader failure: bounded HTTP 500, `MARKET_ACTIVITY_READ_FAILED`.
- Stored/reader response failing its committed schema: bounded HTTP 500,
  `MARKET_ACTIVITY_CONTRACT_VIOLATION`; logs include only schema and the first
  three validation diagnostics, never the payload.

Explicit reads accept `VALIDATED` generations in `SERVING` or `RETAINED` state.
`RETIRED` maps to `ACTIVITY_GENERATION_EXPIRED`; `BUILDING` and `REJECTED` are
hidden. The FMA-1 unavailable envelopes were completed so every normal domain
unavailability remains schema-valid rather than becoming a transport 500.

## Bounded-read measurements

Instrument and group reads each use generation, roster, and one payload read:
3 database calls. Constituent pages retain the FMA-1 bound of 3 calls:
generation, roster, and one bounded joined RPC. Capability discovery uses a
constant 5 calls for populated serving authorities: one batched per-market
serving read, one referenced-generation batch, one Explorer surface pointer,
one roster batch, and one group-payload batch. Measured test counts are 5 for
batches of 1, 3, and 10 independently served generations. With no serving
generation discovery exits after 1 call. No sold-ledger scan exists on these
paths.

## Per-market serving reconciliation

The mirrored follow-up migration
`20260930220000_market_activity_per_market_serving_v1.sql` replaces the global
singleton with `market_activity_market_serving_v1`, keyed by `market_key` and
holding current generation, market-local previous generation, and promotion
time. Ordered application after the FMA-1 migration is safe from a fresh
baseline; a valid single-market legacy pointer is copied before the obsolete
singleton table is dropped.

`promote_market_activity_generation_v1` now requires exactly one roster/market
for the target `VALIDATED` generation, verifies a prepared surface pin against
current Explorer authority, locks only that market's serving row, retains only
that market's prior generation, and advances only its rollback pointer.
PostgreSQL validation published two markets containing the same card
instrument simultaneously, replaced one market, and proved the other market's
current generation remained unchanged while the replaced market retained its
own previous generation.

## Verification

Run from the worktree root:

```text
py -3.11 -m pytest backend/tests/unit/db/services/test_market_activity_v1.py backend/tests/unit/db/services/test_market_activity_capabilities.py backend/tests/unit/api/test_market_activity_api.py backend/tests/unit/domain/pokemon/test_market_activity.py backend/tests/unit/domain/pokemon/test_market_activity_contract.py backend/tests/unit/domain/pokemon/test_market_activity_review_closure.py -q -p no:cacheprovider
250 passed, 3 dependency deprecation warnings in 3.50s

py -3.11 -m backend.scripts.build_market_activity_v1_contract_artifacts --check
{"drift": []}

git diff --check
exit 0
```

The HTTP suite sends all 19 accepted fixture request/response pairs through
the appropriate route serializer without modifying fixture outputs. It also
covers authentication ordering, Plus/Premium prepared access, Premium-only
custom access, request/extra-field rejection, bounded contract violations,
private no-store headers, duplicate capability identities, and plan bounds.
Service tests cover no/current/stale serving authority, exact/mismatched
rosters, missing group payloads, immutable custom revisions, bare custom
fingerprints, hidden nonvalidated states, three simultaneous generations with
an overlapping instrument, and 1/3/10 independent-generation batch call
counts. Auth tests prove a Plus request carrying a published-revision roster is
denied before Activity DB access even when its market key does not start with
`custom:`.

An isolated temporary PostgreSQL 16.15 cluster on loopback port 55439 applied
the fresh baseline, FMA-1 migration, and mirrored FMA-2 follow-up migration,
then emitted `FMA2_PER_MARKET_POSTGRES_VALIDATION_OK`. It verified market-local
promotion/rollback, cross-market isolation, prepared-surface mismatch failure,
service-role access, anon/authenticated denial, group/page/instrument reads,
1/3/10 indexed serving batches, destructive rollback parsing inside a rolled
back transaction, and clean shutdown/removal of the temporary cluster.
Representative execution receipts: serving batch 1 index scan 0.019 ms;
batch 3 bitmap scan 0.028 ms; batch 10 bitmap scan 0.018 ms; instrument 0.154
ms; group 0.122 ms; constituent page 0.225 ms. These are isolated correctness
and access-path receipts, not production latency claims.
The byte-identical follow-up migration mirrors have canonical local SHA-256
`90a8186af30a9ff1441c73136ad502bb2ee7b947c33f8c91554e2ac03f163fc1`.
GitHub Actions PostgreSQL 16 run
https://github.com/BeBoop-Beep/EVRCalculator/actions/runs/36673160788 also
completed successfully for reconciliation implementation SHA
`79c433b6634fcd74b0b0a49cd99700acd8956cda`, including mirror verification,
the fresh migration chain, and the full publication/RLS/read/EXPLAIN/rollback
validation job.

## Known data limitations and FMA-4 instructions

Current evidence lacks accepted complete-window receipt authority. Observed
exact sales can be shown, while proven counts and compatible ranks remain
unavailable until collectors publish the required bound receipts. FMA-2 does
not collect, backfill, build, promote, or infer missing evidence.

FMA-4 should call capability discovery once for the active focused-market set,
key results by echoed `focusKey`, and enable transport only when `available` is
true. It must pass the returned `activityGenerationId`, exact `rosterRef`,
`asOf`, `windowDays`, and persisted evidence identity into the existing FMA-3
scope checks. Use the three POST endpoints exactly as listed, preserve opaque
page cursors byte-for-byte, send normal credentials/cookies, treat 401/403 as
auth/upgrade states, treat HTTP-200 `UNAVAILABLE` as a scope restart, and do
not cache these paid responses in shared storage.

FMA2_RECONCILIATION_READY
