# FMA-2 authenticated API handoff

Status: implementation complete for review. No production migration, activity
build/promotion, provider request, deployment, schedule change, or merge was
performed.

## Delivery identity

- Starting SHA: `0689a04de41379da670fc8f1787d6548a11d6f12`
- Branch: `fma2-market-activity-api`
- Final SHA: the PR head is authoritative (a commit cannot embed its own SHA)
- Implementation SHA: `66fb824393bf0f8e5983324a7f5b4a68df774207`
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
It advertises only the current `VALIDATED`/`SERVING` Activity generation,
checks its prepared surface pin against the current Explorer surface, compares
the requested immutable roster reference exactly, requires a persisted group
payload for the window, and copies `evidenceFingerprint` only from that
payload. Bare custom query fingerprints are never resolved to a newest
revision and therefore return unavailable.

## Authentication and entitlement

The named `_require_market_activity_access` helper enforces the order:
authenticate the repository token authority, resolve `index_plan` from the
server-side profile, authorize the plan, then allow Activity reads. Anonymous
requests return 401; Basic/no-paid-plan requests return 403. Index Plus and
Premium can read prepared card Activity. Any `custom:` market requires Premium.
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
constant 5 calls for a populated serving authority: Activity serving pointer,
generation, Explorer surface pointer, batched rosters, and batched group
payloads. Measured test counts are 5 for batches of 1, 3, and 10. With no
serving generation discovery exits after 1 call. No sold-ledger scan exists on
these paths.

## Verification

Run from the worktree root:

```text
py -3.11 -m pytest backend/tests/unit/db/services/test_market_activity_v1.py backend/tests/unit/db/services/test_market_activity_capabilities.py backend/tests/unit/api/test_market_activity_api.py backend/tests/unit/domain/pokemon/test_market_activity.py backend/tests/unit/domain/pokemon/test_market_activity_contract.py backend/tests/unit/domain/pokemon/test_market_activity_review_closure.py -q -p no:cacheprovider
183 passed, 3 dependency deprecation warnings in 2.37s

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
fingerprints, hidden nonvalidated states, and 1/3/10 batch call counts.

The machine used for the final local run has neither Docker nor `psql`, so a
new local PostgreSQL 16 service could not be started. The unchanged FMA-1
projection baseline and PostgreSQL integration suite remain the database
authority; its accepted ephemeral PostgreSQL 16 receipt is GitHub Actions run
`36666290256` (`FMA1_POSTGRES_VALIDATION_OK`). FMA-2 changes no migration or
SQL function and exercises the same three bounded readers at the API boundary.
The PR should run the repository CI PostgreSQL service before merge.

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

FMA2_API_READY
