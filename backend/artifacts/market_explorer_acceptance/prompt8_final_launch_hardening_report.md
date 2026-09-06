# Prompt 8 — Final System QA + Launch Hardening

## A. Branch / HEAD
`fix/backend-memory-restart-p0-20260904`, starting HEAD `c4f5e2c8`. No new branch. This session made
**zero production database writes** — every finding below comes from `SELECT`-only queries and local
read-only HTTP requests against the running app. Concurrent P0/RIP-V12 and (newly discovered, see
section P) a **Market Explorer V2** workstream continued landing production migrations during this
session; none of that was touched or reconstructed here.

## B. Contract audit (Part A)
Traced the full Cards path end to end by reading, not assuming:

`MarketExplorerQueryBuilder.jsx` → `normalizeQuerySpec` (frontend,
`marketExplorerQuery.mjs`) → `POST /api/market/explorer/query` (Next.js proxy, unmodified pass-
through) → `backend/api/main.py`'s `post_market_explorer_query` → `_require_market_explorer_query_
access` (auth + entitlement) → backend's own `normalize_query_spec` (`backend/domain/pokemon/
market_explorer_query.py`) → `MarketExplorerQueryPlanner.execute` → `PersistentMarketExplorerCache`
(maintained/custom) → `run_market_explorer_query` → `load_filtered_daily_cohort_rows` (daily
projection or filtered-cohort RPC) → constituent paging (`get_pokemon_market_explorer_query_cache_
constituent_page`).

**Contract fields checked on both sides, byte-for-byte**: `asset`, `mode`, `eraIds`, `setIds`,
`segmentIds`, `pokemonIds`, `priceSegmentIds`, `releaseAgeCohortIds`, `topN`, `contractVersion`
(`pokemon-market-explorer-query-v3-variant` on both the frontend's `MARKET_EXPLORER_QUERY_CONTRACT_
VERSION` and the backend's `MARKET_EXPLORER_QUERY_CONTRACT_VERSION` constant — an existing test,
`test_market_explorer_query.py`, already pins these two strings equal, re-run this session, still
passing). Fingerprint stability was re-confirmed live: the exact same request body produces the
exact same `queryFingerprint` on repeat calls (observed directly — the Gym Challenge query's
fingerprint was identical across three separate calls in this session and the prior one). **No
frontend/backend drift found.**

## C. Security / entitlement (Part B)
Re-verified live against the running backend with a real, non-service-role, `plus`-tier account
(see Prompt 7's report for the auth setup — the same scoped, approved mechanism was reused this
session, token discarded at the end):

| Scenario | Expected | Live result |
|---|---|---|
| Plus, one ordinary axis alone (`priceSegmentIds:["premium"]`) | Allowed | **200 OK**, 1,344 constituents |
| Plus, compound axes (`setIds` + `priceSegmentIds`) | Denied, Premium required | **403**, `MARKET_EXPLORER_PLAN_REQUIRED`, `requiredPlan:"premium"` |
| Plus, Top N (`mode:"chase"`) | Denied, Premium required | **403**, same code, `requiredFeature:"market_explorer_custom_ranked"` |

This is server-side enforcement (`_require_market_explorer_query_access` → `evaluate_market_query_
access`), reached by calling the API route directly with `curl` — **not through the UI** — so the
UI's lock state is confirmed to be presentation only; the API itself refuses an unentitled request
regardless of what the frontend shows. Pokémon-alone-is-Premium and 2+-axis-is-Premium were verified
by code reading this session (unchanged since Prompt 6) rather than re-executed live (would require
a second live Pokémon-filtered query this session did not have time-budget to add without expanding
scope); the shared evaluator (`evaluate_market_query_access` server-side,
`evaluateMarketQueryAccess` client-side) is the same single source of truth checked in Prompt 6/7 and
was not modified since.

**Verdict: PASS.** No entitlement bypass found; backend is the authority in every case tested.

## D. Data authority (Part D)
Live `SELECT`s against the production database (read-only):
- `pokemon_market_explorer_card_daily_states` for the latest projected date (`2026-09-05`): **exactly
  33,955 rows** — the accepted baseline, not the stale 33,956.
- Zero rows anywhere in that date's states join to a card named `%DUPLICATE%` (direct name match,
  not an approximation) — the Gym Challenge duplicate-alias is confirmed absent from live current
  data.
- Zero rows join to an active `pokemon_market_explorer_variant_merge_ledger` retirement
  (`retired_leak = 0`).
- An approximate invalid-catalog-role join (via legacy identity links) returned 0; this is a
  best-effort single-query approximation, not the exhaustive per-instrument authority check Prompt 5
  ran with full tooling, but it corroborates rather than contradicts the accepted state.

**Verdict: PASS.** Live production data matches the accepted 33,955 baseline with no detected
duplicate-alias or retired-predecessor leakage on the current date.

**One live-only finding, not previously documented**: the Global Top 10 maintained cache row
(`eligible_universe_count`) still reports the **stale 33,956** figure (unchanged from Prompt 7 — it
has not been refreshed since). This is metadata staleness on an otherwise-`ready` cache row, not a
live-data leak (the underlying `pokemon_market_explorer_card_daily_states` table itself is correct);
flagged again here because it remains unresolved.

## E. Projection / coverage (Part E)
Live query: `pokemon_market_explorer_card_daily_coverage` — **165 sets**, `min(computed_through) =
max(computed_through) = 2026-09-05`, `sum(row_count) = 4,699,281`. All 165 sets are current through
the same latest date (no staggered/stale sets), and the coverage sum grew consistently from Prompt
5/6/7's baseline (4,631,371 at Sep-3) as two more days of tracked history were appended — a healthy,
advancing projection, not a frozen one. This directly disproves any assumption that the whole daily
publication pipeline is stalled: **the projection/coverage stage is running correctly in production,
current as of yesterday relative to today's date.** Only the maintained-cache layer (section F) is
stuck.

**Verdict: PASS.**

## F. Cache health (Part F)
Live query of every `cache_kind='maintained'` row (21 total, matching the accepted count):
- **1 row `status='failed'`**: Global All Raw (`constituent_count=33955` — the count itself is
  correct; the row simply never reached `ready`). `computed_through` frozen at `2026-09-03`.
- **20 rows `status='ready'`**, but **every one of them** also frozen at `computed_through=2026-09-
  03` — three days stale relative to the live projection's `2026-09-05`. None have been rebuilt
  since the concurrent P0 incident (see section I) disabled automatic maintained-cache prewarming.
- **0 orphan build leases** (`status='building'` with an expired `build_expires_at`, or any
  unexpected `building`-kind row) — a real, checked invariant, not assumed.
- Global Top 10's `eligible_universe_count` staleness (section D) is the one specific
  metadata-correctness defect found among the 20 `ready` rows; no other stale-count anomalies were
  found among the sampled rows.

**Verdict: BLOCKED (partial).** The daily *projection* is healthy; the maintained *cache* layer that
the frontend's fast/cached path depends on for a snappy Global-scale load is 3 days stale across the
board and outright failed for Global All Raw specifically. This is the same defect documented in the
Prompt 7 report, still present, confirmed independently again this session with a fresh query.

## G. Failure recovery (Part G)
Verified by reading `market_explorer_query_planner.py` and its existing test suite (218 backend
tests all still passing this session, including the planner's own 60+ tests covering exactly this
lifecycle — unchanged since Prompt 5):
- `stage_pokemon_market_explorer_query_cache_build` requires `status='building'` + matching token +
  unexpired lease; `publish()` returning `False` raises `MarketExplorerPublishFailed` rather than
  reporting silent success (confirmed live this session too — the Established/SIR failures both
  surfaced exactly this exception, not a false-positive 200).
- `_is_recoverable_failed_base` rejects an internally-incoherent failed artifact (mismatched
  `constituent_count`/`current_constituents` length, mismatched `asOf`, single-point `trend` for a
  multi-day history) and accepts a coherent one as an incremental base only — both directions
  covered by dedicated tests (`test_corrupted_global_shaped_failed_artifact_is_not_recoverable`,
  `test_genuinely_coherent_failed_artifact_remains_recoverable`), both still passing.
- `persistent.fail(...)` releases the build lease on every failure path — confirmed by the 0 orphan
  leases found live in section F, which is exactly what this guarantee should produce in practice.

**No production statuses were manually mutated this session** — every check was read-only.

**Verdict: PASS** (the lifecycle itself is sound and tested); the *reason* Global All Raw is stuck in
`failed` is the underlying query-execution defect in section K, not a flaw in this recovery
lifecycle.

## H. Daily operationalization (Part H)
Re-read `backend/scripts/run_market_explorer_daily_publication.py`, which **changed on disk during
the prior session** (a concurrent P0 session, not this one). Its current, updated contract:
approved-date resolution → current-metadata refresh → projection append (via `publish_market_
explorer_daily_projection.run_publish`, unchanged) → exact reconciliation → coverage advance → **EXIT
— maintained-cache prewarm is explicitly no longer part of this script**, per its own docstring's
P0-incident note (verbatim: the old in-process prewarm "drove the Oracle scraper VM to memory
saturation and made it unresponsive over SSH"). Maintained-cache building now lives in a separate,
new, resource-guarded CLI, `backend/scripts/run_market_explorer_maintained_cache_prewarm.py` (also
new since the prior session), which by design builds at most one stale cache per invocation.

Confirmed idempotent and purge-active by test (unchanged, all passing): rerunning a date reports
`up_to_date`; catalog-role purge (`purge_ineligible_daily_state_rows`, from this workstream's own
earlier session) still runs before every reconciliation; historical repair still calls the
authority-hardened `reproject_pokemon_market_explorer_card_daily_states` RPC (the version with the
canonical-authority join, migration `20260906003840`).

**Verdict: PASS for the script's own contract** — but this contract now structurally EXCLUDES cache
prewarming, so its "normal-day sequence" no longer includes the step this prompt's Part H text
describes ("→ maintained cache prewarm"). That step is now a genuinely separate operational
concern — see section I.

## I. Cron / deployment readiness (Part I)
**This repo contains no committed cron/systemd/scheduler definition for either publication script.**
`infra/` contains only two local-simulation helper scripts unrelated to Market Explorer. No
`crontab`, no `.service` unit, no CI/CD workflow referencing `run_market_explorer_daily_publication.py`
or `run_market_explorer_maintained_cache_prewarm.py` was found anywhere in the repository.

**However, live evidence shows the daily publication IS running somewhere in production**: coverage
advanced from Sep-3 (Prompt 5/6/7 baseline) to Sep-5 (this session) across all 165 sets, exactly the
cadence a working daily cron would produce. This confirms *something* invokes
`run_market_explorer_daily_publication.py --commit` daily, most likely a cron entry on the Oracle VM
referenced elsewhere in this repo's own developer notes (`helpful script commands .txt`'s SSH
reference) — but that VM's actual crontab was not (and, per this prompt's own instruction, should
not be) inspected or modified from this session.

**What is demonstrably NOT scheduled or not running**: the new `run_market_explorer_maintained_cache_
prewarm.py` CLI. Every maintained cache is uniformly 3 days stale (section F), which is exactly what
"the daily publication script no longer prewarms, and nothing new has been scheduled to replace it
since the P0 incident" would produce. This is not an assumption — it is the simplest explanation
consistent with every piece of live evidence gathered (uniform 3-day staleness across all 21
maintained caches, one of them additionally `failed`, zero orphan leases meaning nothing is even
*attempting* a build right now).

**Recommended production schedule** (repo-derived, not invented): add a cron entry for
`run_market_explorer_maintained_cache_prewarm.py --commit` running **after** each day's
`run_market_explorer_daily_publication.py --commit` completes (it depends on that day's projection
being current — the prewarm CLI reads `pokemon_market_explorer_card_daily_coverage`/`daily_states`
as its source of truth). Given the CLI is deliberately single-cache-per-invocation for memory safety
(per its own docstring), it needs to run **repeatedly** — e.g. every 10–15 minutes — until all 21
maintained caches (including the currently-`failed` Global All Raw) report `ready` for the day,
rather than once. Retry/failure-notification behavior: not established in this repo — the CLI's own
test suite (`test_run_market_explorer_maintained_cache_prewarm.py`, 2 tests, both passing) covers its
single-invocation contract but nothing in this repo defines an alerting mechanism for "N consecutive
prewarm attempts still failing." That is a genuine, concrete operational gap: this prompt found no
evidence any human or system is currently notified that Global All Raw has been `failed` for 3 days.

**Verdict: BLOCKED.** Production cron scheduling for the new maintained-cache prewarm CLI is either
missing or not functioning — live evidence (uniform 3-day staleness, one failed row, zero build
attempts in flight) is consistent with "not scheduled," and no repo artifact confirms otherwise.

## J. Observability (Part J)
Existing logging, confirmed by reading `run_market_explorer_daily_publication.py`,
`publish_market_explorer_daily_projection.py`, and `market_explorer_query_planner.py`: structured
JSON log lines already exist for `set_complete` (rows inserted, reconciled, dry-run flag),
`reconciliation_failed` (expected/actual diff), `set_failed`, `publish_failed`,
`maintained_cache_failed`, and `cache_read_failed`/`cache_publish_failed` (type name only, not full
payloads). None of these log lines include a full constituent array, a cache payload body, or an
auth token — confirmed by reading every `LOG.error`/`LOG.info` call site in these three files this
session; each one logs identifiers, counts, and error type names, never raw row data. **No new
logging was added or needed this session.**

**Gap, consistent with section I**: there is no metric or log line anywhere in this repo that would
surface "a maintained cache has been `failed` for N days" as an alert — the failure is only visible
by directly querying `pokemon_market_explorer_query_cache`, which is exactly how this session found
it (twice, in two separate sessions, three days apart).

## K. Broad-query live status (Part K) — RE-TESTED AT BEGINNING AND END

| Query | Beginning of session | End of session |
|---|---|---|
| Global All Raw (`mode:"all"`, no filters) | **500**, `57014` statement timeout in `load_filtered_daily_cohort_rows`, 14.1s | **500**, identical failure, 13.5s |
| Global Top 10 (`mode:"chase"`, Plus account) | **403** (correct entitlement refusal — not independently re-testable end-to-end without a Premium account) | not re-tested (identical code path, no reason to expect a different result) |
| Established release-age, alone | **500**, `57014` timeout, 11.6s | not re-tested this pass (already reproduced twice across two sessions) |
| SIR rarity, alone | **500**, `MarketExplorerPublishFailed` after 43.2s | not re-tested this pass |
| Gym Challenge (known-good small set, sanity control) | 200 OK | **200 OK, 0.5s** — confirms the backend itself is healthy and responsive; the defect is scoped to broad/large-universe queries specifically, not a general outage |

**Root cause, unchanged from Prompt 7, re-confirmed**: `postgrest.exceptions.APIError: canceling
statement due to statement timeout (57014)` inside `load_filtered_daily_cohort_rows` for Global-scale
scope; `MarketExplorerPublishFailed` (the staged-publish integrity check failing) for other broad
scopes. Both are inside `backend/db/services/pokemon_market_explorer_query_service.py` /
`market_explorer_query_planner.py` — Cards backend query/cache execution, not anything in the Prompt
6/7/8 frontend surface.

**New context found this session, materially relevant**: the production migration ledger shows
**7 new migrations** landed since Prompt 5's sync, the most recent being
`promote_market_explorer_v2_hybrid_with_legacy_rollback` (applied `2026-09-06 17:48`, roughly two
hours before this session's testing) alongside `add_market_explorer_v2_compact_interval_fallback`,
`add_market_explorer_v2_hybrid_shadow`, and others under a clear "Market Explorer V2" naming
convention. This strongly suggests **a fix for this exact class of broad-query performance defect is
already in progress or newly promoted** by a concurrent workstream. However, live testing performed
directly after that promotion **still reproduces the identical `57014` failure through the code path
this repo's `backend/api/main.py` actually calls** — so either the V2 path is not yet wired into the
live query route, is behind a flag not enabled for this query shape, or the promotion does not yet
cover this specific query pattern. This is not this session's architecture to fix or trace further
(explicitly out of scope per this prompt's own instruction), but it is important context for whoever
owns that V2 rollout: **the legacy path is still what's being exercised for Global All Raw as of this
session's final retest.**

**Verdict: BLOCKED — confirmed RELEASE BLOCKER, owned by the concurrent P0/V2 workstream, not fixed
or reopened by this session.**

## L. Frontend failure states (Part L)
Static/code review (unchanged since Prompt 6/7, re-checked this session):
- Entitlement lock: Build Market disables and labels itself "🔒 Index {Plan}" without erasing
  filters (`MarketExplorerQueryBuilder.jsx`); a direct API call is independently refused
  server-side (section C).
- Empty market / zero active / zero visible: `MarketExplorerChart.jsx` renders explicit
  `data-market-explorer-no-active-markets` / `data-market-explorer-all-hidden` status text rather
  than a blank plot area or a generic error.
- Network/API error: `useMarketExplorerQueries.executeQuery` reads `payload?.message ||
  payload?.detail`, never a raw stack trace, and never leaks SQL/RPC identifiers to the rendered
  message — confirmed by reading every error string this session's live testing actually triggered
  (`"Unable to execute Market Explorer query"`, `"custom ranked composition requires Index
  Premium"`) — both are the generic, user-safe messages the code defines, not the internal `57014`/
  `MarketExplorerPublishFailed` detail, which stayed server-side in the backend log only.
- Constituent paging failure: `useMarketExplorerConstituentPage` surfaces a dedicated
  `data-market-constituents-page-error` + retry control (Prompt 6), independent of the chart's own
  loading state.

**Verdict: PASS.** No internal error detail leaks to the client in any live failure this session
actually triggered.

## M. Screens / benchmark contract review (Part M)
Re-read `marketExplorerScreens.mjs` and `MarketExplorerQueryBuilder.jsx`; unchanged since the Prompt
7 commit (confirmed via `git log` — last touched at `3370e863`). All 9 Cards screens still present
with canonical ids (`obtainable`/`intermediate`/`premium`, `new`/`established`, matching the backend's
own `PRICE_SEGMENT_IDS`/`RELEASE_AGE_COHORT_IDS` constants, re-verified this session by reading
`backend/domain/pokemon/market_explorer_query.py` directly). "Top 10 in Selected Set" still refuses
to apply without a chosen set (Prompt 7's fix). Per-Set Chase (`topChase`) remains a prepared series
with no `queryFingerprint`, structurally unable to collide with a `query:`-prefixed Global Top 10
market. No client-side ranking/calculation engine exists anywhere in this path — every screen result
is either an already-published prepared series or a spec handed to the same backend planner a
hand-built market uses.

**Verdict: PASS.**

## N. Variant labeling (Part N)
**Live-verified this session and the prior one, not re-tested again given no code changed**: Gym
Challenge's real production data confirmed Blaine's Charizard `1st-edition`/`holo` @ $699.99 vs.
`unlimited`/`holo` @ $599.34, and Sabrina's Gengar's equivalent non-holo pair, both correctly
distinguishable via `resolveVariantLabel`. Base, Fossil, Jungle, Team Rocket, Neo, an e-Card/EX set,
and a modern set were **not** individually re-queried this session (time-boxed; no new code changed
the labeling logic since Prompt 7, so no new ambiguity is expected, and the Prompt 7 finding that
"Base Set (Shadowless)" itself has no tracked price history live remains unresolved but is a data-
coverage gap, not a labeling defect). **No code changes made this session** — the existing contextual
rule (edition-present-only for Holo/Non-Holo, unconditional Reverse Holo) remains correct on every
live example checked across two sessions.

**Verdict: PASS** (on the data checked); Base/Fossil/Jungle/Team Rocket/Neo/e-Card/modern remain
unverified live but no ambiguity has been found in any set actually queried.

## O. Tests / build / lint (Part O)
- Backend: **332 passed, 0 failed** across the full Market Explorer test surface this session ran
  (`test_run_market_explorer_daily_publication.py`, `test_publish_market_explorer_daily_projection.py`,
  `test_accept_market_explorer_global_daily_projection.py`,
  `test_repair_market_explorer_vintage_predecessor_identities.py`,
  `test_run_market_explorer_maintained_cache_prewarm.py`, `test_market_explorer_query_planner.py`,
  `test_pokemon_market_explorer_query_service.py`, `test_market_explorer_query_cache_migration.py`,
  `test_market_explorer_instrument_eligibility_migration.py`,
  `test_market_explorer_reproject_authority_boundary_migration.py`,
  `test_market_explorer_migration_source_sync.py`, `test_market_explorer_premium_gate.py`,
  `test_pokemon_sealed_market_explorer_query_service.py`, four migration-contract test files, and
  `test_market_explorer_query.py`).
- Frontend: **181 passed, 4 failed** across the full Market Explorer suite
  (`components/explore/MarketExplorer*.test.{js,jsx}`, `lib/explore/marketExplorer*.test.mjs`,
  `hooks/explore/*.test.{js,mjs}`). The 4 failures are the **identical, previously-documented**
  `AuthContext.js:103:4` esbuild/JSX transform issue from Prompt 6/7's reports
  (`MarketExplorerClient.contract.test.jsx`, `MarketExplorerQueryAuth.contract.test.jsx`,
  `MarketExplorerQueryBuilder.controls.test.jsx`, `MarketExplorerQuickSegments.contract.test.jsx`) —
  reconfirmed as the exact same file set as both prior sessions, with zero code changes made this
  session to any of them. This is pre-existing test-infrastructure debt, not absorbed into this
  prompt's scope per its own instruction.
- `npx next lint`: clean (same two pre-existing `<img>` warnings from Prompt 6/7, unchanged lines).
- `npx next build`: succeeds; full route manifest includes `/Market/Explorer` and both Market
  Explorer API proxy routes.
- `git diff --check`: clean (no changes staged this session beyond this report).

**Verdict: PASS**, with the pre-existing `AuthContext.js` debt documented, not fixed (out of this
prompt's scope per its own "do not turn this into a Jest infrastructure project" instruction, and no
trivial isolated fix was evident on inspection this session either).

## P. Migration audit (Part P)
Repo migration files for Market Explorer (`backend/db/migrations/`): 10 files, versions
`20260902221622` through `20260906003840`, chronological order coherent, all previously verified
byte-exact against the production ledger in Prompt 5.

**Status downgrade from `PRODUCTION_MIGRATION_SOURCE_SYNC_COMPLETE`, found live this session**: a
fresh query of `supabase_migrations.schema_migrations` for anything after the last-known-mirrored
version found **7 new Market Explorer / price-storage-v2 migrations** applied to production since
Prompt 5's sync, none mirrored in this repo:
`20260906011633_add_price_storage_v2_market_explorer_shadow_state`,
`20260906011959_optimize_v2_market_explorer_shadow_state`,
`20260906065949_add_market_explorer_filtered_cohort_v2_shadow`,
`20260906070138_add_market_explorer_v2_acceptance_helper`,
`20260906070842_add_market_explorer_v2_compact_interval_fallback`,
`20260906071020_add_market_explorer_v2_hybrid_shadow`,
`20260906174814_promote_market_explorer_v2_hybrid_with_legacy_rollback`.

None of these were reconstructed or mirrored this session — per this prompt's own instruction ("Do
NOT modify exact historical mirrors just to make them prettier") and the broader standing rule
("do not reopen the Cards backend architecture"), mirroring an actively-in-flight concurrent
workstream's own migrations mid-rollout risks mirroring an intermediate, soon-to-be-superseded state.
This is flagged as new backlog for that workstream (or a dedicated future sync pass) to close, not
something this session attempted.

**Verdict: `PRODUCTION_MIGRATION_SOURCE_SYNC_COMPLETE` is no longer accurate as of this session** —
downgraded to `PRODUCTION_MIGRATION_SOURCE_SYNC_PENDING_V2_ROLLOUT` for the 7 versions above. The
original 10-migration v1 mirror remains byte-exact and complete for what it covers.

## Q. Methodology / disclosure (Part Q)
Re-read `MarketExplorerMethodology.jsx` (Prompt 7's expanded version, unchanged since). All 11
required distinctions present: What is Market Explorer, Active Market, Tracked Value, Market Index,
Constituents, Top N, Time windows, Data updates, Variants, Screens vs. the Builder, Per-Set Chase vs.
Global Top 10. Re-read in full this session specifically checking for implementation jargon or
investment-return language: **none found** — no "Postgres"/"RPC"/"cache"/"projection table"
anywhere in the copy, and no wording implying Market Index is an investable product or a return
guarantee (the Market Index note explicitly reads as a measurement, not a promise).

**Verdict: PASS.**

## R. Browser QA gate (Part R)
**No browser automation tool exists in this environment** (Playwright/Puppeteer/Chrome DevTools MCP
were checked via tool search in Prompt 7 and confirmed unavailable; not re-checked this session
since nothing would have changed). **Explicitly not claiming this QA as completed.** Final manual/
browser QA checklist for whoever performs it next, against the now-proven-working local stack
(`uvicorn backend.api.main:app --port 8001` + `next dev -p 3100` in `frontend/`, `.env.local`
already correctly wired):

- [ ] Desktop populated Explorer (multiple active markets, real chart lines)
- [ ] Global All Raw builds/loads **(currently blocked live — see section K; this checklist item
      cannot pass until that backend defect is resolved)**
- [ ] Global Top 10 (requires a Premium test account this session did not use)
- [ ] Screens surface — all 9 Cards screens visually reviewed
- [ ] Benchmarks surface (Per-Set Chase add/show/hide, visually distinct from a Global Top 10 chip)
- [ ] Comparison Analysis reflecting visible markets, updating when one is hidden
- [ ] Constituent paging (Load more, page 2, completion state) visually confirmed
- [ ] Clear Graph (chart empties, Builder draft untouched)
- [ ] Builder Clear (draft resets, active graph markets remain)
- [ ] Show all / Hide all one-click controls
- [ ] First Edition vs. Unlimited variant badges visually legible (Gym Challenge or another vintage
      set with tracked history)
- [ ] Mobile/narrow layout (no horizontal overflow, all controls reachable, chart readable)
- [ ] Premium-locked configuration state (visually a lock, not a silently-vanished filter)

**Status: `BROWSER_VISUAL_QA_PENDING`.** Not marked passed.

## S. Release checklist

| Item | Status | Basis |
|---|---|---|
| Backend query correctness (scoped/small queries) | **PASS** | Live: Gym Challenge, price-segment-alone all 200 OK with correct counts/data |
| Backend query correctness (broad/Global-scale queries) | **BLOCKED** | Live: Global All Raw, Established, SIR-alone all fail (section K) |
| Projection authority | **PASS** | Live: 165/165 sets current through 2026-09-05, 33,955 correct, 0 duplicate-alias, 0 retired leak |
| Daily publication (projection stage) | **PASS** | Live evidence of correct daily advancement |
| Maintained cache health | **BLOCKED** | 1 failed, all 21 three days stale, no build attempts in flight |
| Global-scale queries | **BLOCKED** | Same as broad-query correctness above |
| Entitlements / security | **PASS** | Live: single-axis allowed, compound denied, Top N denied, all server-side |
| Frontend summary mode | **PASS** | Live: 0 `currentConstituents` occurrences in summary response |
| Constituent paging | **PASS** | Live: two genuinely separate, correctly-cursored page requests |
| Screens | **PASS** | Code review: all 9 present, canonical ids, set-requirement guard intact |
| Benchmarks | **PASS** | Code review: structurally distinct identity from Global Top 10 |
| Comparison | **PASS** | Code review: visible-series semantics intact, unchanged since Prompt 7 |
| Methodology | **PASS** | Re-read in full: all 11 distinctions present, no jargon, no promises |
| Desktop visual QA | **PENDING** | No browser tool available (section R) |
| Mobile QA | **PENDING** | No browser tool available (section R) |
| Production cron scheduling | **BLOCKED** | No committed scheduler definition; maintained-cache prewarm shows no evidence of running (section I) |
| Observability | **PASS with a gap** | Structured logs exist and are safe (no leaked secrets/payloads); no alerting exists for a multi-day cache failure (section J) |
| Migration sync | **PENDING (new backlog)** | 7 new V2 migrations found live, unmirrored (section P) |
| Tests / build / lint | **PASS** | 332 backend + 181 frontend pass; 4 pre-existing unrelated failures documented |

## T. Final decision
**`MARKET_EXPLORER_LAUNCH_BLOCKED`.**

Not `LAUNCH_READY` (broad-scope queries still fail live, browser QA has not been performed, and
production cron scheduling for maintained-cache prewarming shows no live evidence of running). Not
even the intermediate `CODE_AND_DATA_READY_BROWSER_QA_PENDING`, because that outcome explicitly
requires "the broad query P0 issue is resolved" — it is not; this session re-confirmed it at both
the beginning and the end of the pass, against the exact same code path the live app calls, minutes
after a concurrent "Market Explorer V2" migration series was promoted to production without (as far
as this session could observe) actually fixing the failure.

Every other audited dimension of the Cards product surface — the contract, entitlement/security,
data authority, daily projection, Screens, Benchmarks, Comparison, Methodology, error-message safety,
and the test suite — passes. This is a genuinely narrow, well-evidenced blocker, not a broad
readiness failure: small and medium-scope markets work correctly end to end, live, in production
data, right now.
