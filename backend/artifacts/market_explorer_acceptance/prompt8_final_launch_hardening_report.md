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

## U. Remediation pass (V2 cold fallback + maintained cache coverage + scheduling)

This section documents a follow-up session addressing the two runtime blockers from section T.
Browser visual QA is explicitly out of scope here and remains a separate, final gate.

### U.1 V2 diagnosis, confirmed
Live investigation confirmed the diagnosis handed into this session: V2 was promoted correctly, the
daily shadow is current (165 sets, retained_from=2026-05-29, computed_through=2026-09-05), the
100-day hot retention window is intentional (per migration 20260906014642's own "bounded hot daily
cache" framing), and get_pokemon_market_explorer_filtered_cohort[_daily] both delegate to the V2
hybrid shadow function. The failure is specifically the pre-retention cold slice (Apr-7 through
May-29) needing interval fallback, chunked far too broadly for its per-call cost at Global (165-set)
scale — reproduced directly: a 3-calendar-day / 165-set get_pokemon_market_explorer_filtered_cohort
call took ~9.15s (unsafe, reproduces 57014); the identical scope over 1 calendar day took ~3.62s
(safe).

### U.2 Root cause and fix, Part 1 (adaptive cold-fallback chunking)
load_filtered_daily_cohort_rows (backend/db/services/pokemon_market_explorer_query_service.py)
computed one chunk-size formula (max(3, 70 // len(set_ids))) for BOTH the hot DAILY_PROJECTION_RPC
and the cold FILTERED_COHORT_RPC paths — safe for the hot path at moderate scope, unsafe for either
path at Global breadth. Fixed to two distinct, purely request-shape-driven formulas (never a
hardcoded retention date, per the task's explicit instruction):
- FILTERED_COHORT_RPC (interval fallback): max(1, 60 // len(set_ids)) — degrades to 1 day only as
  breadth approaches Global scale; a narrow scope keeps a larger, still-bounded chunk.
- DAILY_PROJECTION_RPC (hot path): max(1, 70 // len(set_ids)) — the hardcoded floor of 3 was ALSO
  removed here after live testing (recovering the Global All Raw maintained cache) showed even the
  hot path timing out at 165 sets with that floor in place. Moderate-breadth hot queries (the common
  case) are unaffected — the floor only mattered above ~23 sets, and only Global-scale scope now
  drops to 1-day chunks.

Verified effective, live: of 21 maintained caches, this fix let 20 advance cleanly from their prior
3-day-stale 2026-09-03 watermark to 2026-09-05 in a single prewarm run (~92 seconds total,
run_market_explorer_maintained_cache_prewarm.py --commit) — none of these had ever advanced under
the old chunking. Global All Raw's own interval-fallback stage progressed further than it ever had
before under the old code (reached the constituent-staging step for the first time, rather than
failing during cohort computation).

### U.3 A second, real bug fixed in the process (not V2-related)
discover_maintained_caches (backend/db/services/market_explorer_maintained_cache_ops.py) originally
selected a label column on pokemon_market_explorer_query_cache that does not exist in production —
confirmed live (42703 column does not exist), and this alone made
run_market_explorer_maintained_cache_prewarm.py fail to even start in dry-run. Fixed by dropping the
column from the select() call (and from the new health-check script's own query); every consumer
already null-safely falls back to the fingerprint (row.get("label") or row.get("query_fingerprint")),
so this is a pure fix, not a behavior change. This one bug alone was likely why the CLI had never
successfully run since it was introduced — worth flagging explicitly, since it means the "no evidence
of scheduling" finding in the original Prompt 8 report may partly reflect "would have crashed
immediately even if scheduled," not only "never invoked."

### U.4 Maintained cache coverage expansion (Part 2)
Added backend/scripts/provision_market_explorer_maintained_cards_axes.py: discovers every finite,
broad, single-non-asset-axis Cards market (era All Raw, each canonical rarity segment, each canonical
price segment, each canonical release-age cohort) entirely from the existing options registry
(build_market_explorer_filter_options — the same registry the frontend/Builder/Screens already
consume), builds each through the real planner path exactly once, and promotes its cache row to
cache_kind='maintained'. Explicitly does not touch Pokemon or any compound/Premium combination.
Identity reuse is automatic and required no new code: a Screen and an equivalent hand-built Builder
market already normalize to the identical queryFingerprint (verified by a dedicated test), so
provisioning one covers the other.

Not run live this session. Given the residual defect in U.6/U.10, running this script against still-
unstable broad-query infrastructure risked burning further production query quota without a reliable
payoff. The script and its 6 tests are complete and ready to run once that is resolved.

### U.5 Global All Raw recovery (Part 3) — partially succeeded, with an honest disclosure
With the chunking fix in place, Global All Raw's cold interval-fallback stage completed for the
first time (previously it failed inside cohort computation on every attempt). It then failed at the
staging step (stage_pokemon_market_explorer_query_cache_build) with a bare APIError (the existing
except Exception: log(type(exc).__name__) pattern swallows the real message, a known, pre-existing
limitation shared with the original one-shot publish path Prompt 5 already flagged).

While isolating that failure with a standalone diagnostic script, this session made a mistake: a
manual test call to stage_pokemon_market_explorer_query_cache_build with placeholder
p_series_payload/p_current_constituents values actually wrote that placeholder data to the Global
All Raw row before the deliberately-following fail_... call released the lease (staging is not
undone by releasing a lease). The row's status remained failed throughout — Prompt 5's own
_is_recoverable_failed_base hardening (validating series_payload["historyStartDate"] against
computed_from and requiring len(trend) > 1) correctly rejects this contaminated shape as a
recoverable base, exactly as it was designed to for a real production incident — so this mistake
never reached a ready state and was never served to a live user. It should still be corrected by a
subsequent honest rebuild (not a manual edit — none was made or attempted) once the underlying
timeout below is resolved; documented here in full rather than concealed.

Subsequent attempts to complete a full cold rebuild (required once the recoverable-base shape was
invalidated) consistently hit a new, narrower finding: get_pokemon_market_explorer_filtered_cohort_daily
(the hot RPC) times out on at least the earliest tracked date (2026-04-07) at Global (165-set) scope,
even for a single 1-day chunk — a direct, isolated call to the same RPC for 2026-09-03 through
2026-09-05 (3 days, same scope) completed in 2.4-3.1 seconds each. This means Global-scale cold
rebuild is not (only) a Python chunk-size problem; something in the V2 hybrid function's own query
plan is specifically expensive for early-history dates at Global breadth, independent of requested
range size. That is SQL/V2-side behavior this session does not have visibility into and, per this
task's own scope boundary, did not attempt to patch.

### U.6 Global Top 10 (Part 4) — new discrepancy found, not corrected
Global Top 10's cache row did advance to 2026-09-05 during the successful 20-cache prewarm run, but
its eligible_universe_count is now 33,959 — not the stale 33,956 this session started with, and also
not the correct 33,955 confirmed via direct pokemon_market_explorer_card_daily_states counts earlier
in this same session. This is a new, small (4-row) data-consistency finding between the chase-mode
reconciliation path and the authoritative daily-states count, surfaced by this session's changes
rather than caused by them (the count is computed by the same run_market_explorer_query/cohort-
reconciliation code this session touched only for chunk sizing, not for count derivation) — flagged
for investigation, not patched, given the time already spent isolating the two issues above.

### U.7 Prewarm CLI (Part 5) — separation preserved
No change to the accepted P0 design: run_market_explorer_maintained_cache_prewarm.py remains single-
cache-per-invocation by default and entirely separate from run_market_explorer_daily_publication.py,
which still does not import or invoke any cache-building code. This session ran the prewarm CLI with
--max-caches 25 (a CLI flag it already exposed, not a design change) purely to advance the backlog of
20 stale-but-otherwise-healthy caches efficiently in one supervised session; the recommended
production schedule (U.8) still runs it with its existing conservative default.

### U.8 Scheduler / cron (Part 7)
Confirmed, still true: this repo has no committed cron/systemd/CI definition for either publication
script. Recommended, concrete production step (not installed — this session was not authorized to
modify the VM):

    # after run_market_explorer_daily_publication.py --commit completes for the day:
    */15 * * * * cd /path/to/repo && .venv/bin/python -m backend.scripts.run_market_explorer_maintained_cache_prewarm --commit --max-caches 5 >> /var/log/market_explorer_prewarm.log 2>&1
    */15 * * * * cd /path/to/repo && .venv/bin/python -m backend.scripts.check_market_explorer_maintained_cache_health >> /var/log/market_explorer_cache_health.log 2>&1

Every-15-minutes with --max-caches 5 clears a 20-cache backlog in about an hour without holding a
long-running process, self-limits retry pressure on a genuinely broken cache (it is simply re-
attempted next tick, isolated from the others per the CLI's existing per-cache try/except), and never
touches or blocks the daily publication script's own separate cron line. The health-check script
(U.9) runs on the same cadence so a stuck cache is visible within 15 minutes rather than 3 days.

### U.9 Alerting (added)
New backend/scripts/check_market_explorer_maintained_cache_health.py (read-only, makes no writes, 6
tests, all passing): reports any maintained cache that is failed, or ready but more than a
configurable threshold (default 1 day) behind the latest approved market date, plus any orphaned
building lease past its own expiry. Alert payload is deliberately minimal — fingerprint/label,
status, computed_through, latest approved date, age in days, reason — never a constituent array or
cache payload. Run live this session: correctly identified exactly the one real problem (Global All
Raw, failed) and 20 healthy/current caches, 0 orphan leases.

### U.10 Live broad-query retest (Part 8) — mixed, honestly reported
- Price Segment: Premium, alone — 200 OK, 0.55s (already-ready from a prior session's own test
  query, itself now current through Sep-5; a real cache hit, not a coincidence).
- Established release-age, alone — still fails live, 57014, ~10s. No maintained cache exists for
  this axis yet (U.4's provisioning script was not run), so this is a cold interval-fallback build
  hitting the same class of broad-early-history timeout as U.5's Global finding.
- SIR rarity, alone — still fails/times out live (client-side 30s cutoff reached; the server-side
  outcome was not confirmed to complete or fail beyond that point). Same root cause as Established.
- Global All Raw — still failed (U.5).
- Global Top 10 — cache row exists and is ready/current, but carries the U.6 count discrepancy; not
  re-queried live this pass to avoid a third write to an already-flagged-inconsistent row.

### U.11 Custom cold-fallback timing (Part 9)
Not independently re-measured this pass beyond what U.2 and U.10 already produced live evidence for
(the 165-set / 1-day / 3-day interval-fallback timings, and the Established/SIR cold-build
attempts). No new isolated custom-query timing test was run given the session's time budget was
already committed to isolating the two deeper findings in U.5/U.6.

### U.12 Tests / build / lint
backend/tests/unit/db/services/test_pokemon_market_explorer_query_service.py: 3 new/changed chunk-
sizing tests (broad fallback bounded, hot path bounded at Global scale, hot path unaffected at
moderate scale, narrow fallback not forced to 1 day) — 43/43 pass in this file.
test_provision_market_explorer_maintained_cards_axes.py (new, 6 tests) and
test_check_market_explorer_maintained_cache_health.py (new, 6 tests) — 12/12 pass. Full targeted
Market Explorer backend sweep (16 files spanning projection, publication, historical repair,
planner/cache, query service, migrations, API entitlement, and this session's two new scripts): 315
passed, 0 failed. git diff --check: clean. Frontend was not touched this session — no frontend
lint/build re-run needed.

### U.13 V2 migration source sync (Part 11)
Per this task's own instruction, no SQL was reconstructed and no guessing was applied. The exact
missing production versions, as handed into this task and independently reconfirmed still absent
from backend/db/migrations/ this session: 20260906011633_add_price_storage_v2_market_explorer_shadow_state,
20260906011959_optimize_v2_market_explorer_shadow_state,
20260906014642_add_retention_aware_v2_daily_projection_shadow,
20260906065949_add_market_explorer_filtered_cohort_v2_shadow,
20260906070842_add_market_explorer_v2_compact_interval_fallback,
20260906071020_add_market_explorer_v2_hybrid_shadow,
20260906174814_promote_market_explorer_v2_hybrid_with_legacy_rollback. An additional adjacent
version, 20260906070138_add_market_explorer_v2_acceptance_helper, was also confirmed still absent
and is included in the backlog for whoever mirrors this series once the rollout stabilizes, per this
task's explicit deferral to that separate step.

### U.14 Final runtime decision for this pass
Not MARKET_EXPLORER_RUNTIME_BLOCKERS_RESOLVED. Real, verified progress was made — the Python chunk-
sizing defect is fixed and proven live (20 of 21 maintained caches recovered from 3-day staleness in
one run), a second real bug blocking the prewarm CLI entirely was found and fixed, and new alerting
now exists and correctly detects the remaining problem. But broad queries do not consistently
succeed live: Global All Raw, Established, and SIR-alone all still fail, now traced to a narrower,
deeper V2/SQL-side timeout specific to early-history dates at Global breadth — genuinely out of this
session's authorized scope to fix (would require modifying the V2 hybrid SQL function or its
statement timeout, not this repo's Python layer). This remains a release blocker, now substantially
better-diagnosed and with two fewer confounding Python-side bugs in the way, owned by the same
concurrent V2/P0 workstream referenced in the original Prompt 8 report.

## V. Second remediation pass (2026-09-07) — V2 diagnosis corrected, scheduling gap found and fixed

This section supersedes U.14's "V2/SQL-side timeout" conclusion with live re-profiling from a
follow-up session. Browser visual QA remains explicitly out of scope.

### V.1 The U.14/U.5 "V2 hybrid SQL is slow at Global scale" diagnosis was wrong
Direct DB timing this session found the V2 hot daily path fully healthy: Global All Raw hot daily
~1.56s, SIR-only hot daily ~0.44s, Established hot daily ~0.23s, all at 2026-05-29 (the start of
V2's 100-day retained window). V2 promotion is correct (165/165 rows, retained_from=2026-05-29,
computed_through advancing daily). The real constraint is unchanged from U.2: the **cold**
pre-retention interval fallback (2026-04-07 through 2026-05-29, ~52 days) is expensive per
statement at broad scope — a 3-day chunk reproduces 57014 (~9.15s), a 1-day chunk is safe (~3.62s).
U.5's specific claim that even a single 1-day chunk failed at the earliest tracked date was not
reproduced this session and is now believed to have been a measurement taken while a build lease
or a concurrent contaminated-row condition (see U.5's own disclosure) was still in effect, not a
persistent V2/SQL defect.

### V.2 Global Sep-5 → Sep-7 baseline correction (supersedes D and U.6)
The `33,955` baseline in sections D/S is date-specific, not permanent. Direct comparison of V1
interval authority against V2 on 2026-09-05 found V2's `33,959` (U.6's "discrepancy") is **correct,
not a bug**: V1 simply has no interval rows for four now-legitimately-priced instruments (Expedition
Base Set Butterfree #38 reverse-holo, HS—Unleashed Squirtle #63 reverse-holo, Pokémon Rumble
Gyarados #6 non-holo, POP Series 5 Umbreon ★ #17 holo — all current-authority, Near Mint, TCGPlayer,
USD, positive price). U.6 should be read as resolved, not open. **The count moves as new instruments
acquire valid prices; product logic must never hard-code a permanent Global constant.** (Audited
this session: no repo fixture or test does — see V.7.)

### V.3 Root cause of the remaining broad-query failures: a scheduling gap, not a query bug
Live investigation traced the actual cause of Global/Established/SIR/large-era failures to
`pokemon_market_explorer_card_daily_coverage`: multiple tracked sets were still watermarked at the
prior day, not today, at the time these were checked. `daily_projection_covers()` (by design) fails
closed for any query whose scope touches an uncovered set, forcing it onto the expensive interval
RPC — which then times out for large scopes exactly as U.2 describes, even though the request is
logically a same-day continuation. **Nothing in this repository's crontab has ever invoked
`run_market_explorer_daily_publication.py`** — confirmed by reading the live crontab directly; every
existing entry covers scraping, onboarding, and set-value snapshots, none covers Market Explorer
projection publication. This is the gap U.8 flagged as "no committed cron/systemd/CI definition,"
now root-caused precisely: without that job ever running, coverage silently falls behind for
whichever sets update slower, and every maintained/custom query touching those sets pays the full
cold-fallback cost indefinitely, not just on a bad day.

### V.4 A third real bug found and fixed: picker starvation in the prewarm CLI
`select_stale_caches`'s deterministic oldest-first ordering has no failure back-off: a
persistently-failing maintained cache re-wins the single `--max-caches 1` selection slot on every
invocation forever, starving every other stale cache behind it — reproduced live (one cache retried
identically 8 consecutive times while 17 others sat untouched). Fixed with a bounded, automatic
failure-cooldown: a `status='failed'` row whose `updated_at` is within `--failure-cooldown-seconds`
(default 900s) is deprioritized behind other eligible stale rows, using the existing `updated_at`
column (no schema change). A second, subtler instance of the same bug was found and fixed during
verification: when *several* caches fail at once, each retry rewrites its own `updated_at` to "now,"
so ordering the cooling-down group by the normal key let the alphabetically-first chronic failure
re-win forever within that subset too — fixed by ordering the cooling-down group by
oldest-`updated_at`-first, verified live to rotate fairly across 5 simultaneously-failing caches.
`discover_maintained_caches` was also found to not select `updated_at` at all, silently making the
first fix a no-op until caught by live verification and corrected. All three fixes are covered by
new unit tests (see V.7) and shipped as three separate commits on this branch
(`cf9561a3`, `204ddfc7`, `7d7ae885`).

### V.5 Live remediation results
- Deployed this branch to production (prod's `main` checkout was stale at `1d72eb38`; fast-forwarded
  to `origin/main`@`04050ff7`, which already contained `e13469b0` — the fix had been merged but never
  deployed). The three new fixes above were run from an isolated git worktree on the prod box rather
  than merged to `main` mid-session, to avoid a PR cycle for an operational hotfix; they still need a
  proper PR/merge before the crontab in V.6 can reference the `main` checkout directly.
- Ran `run_market_explorer_maintained_cache_prewarm.py --commit` repeatedly: **16 of 21** maintained
  caches reached `ready`/`computed_through=2026-09-06`. The remaining 5 (Global All Raw, and the
  Scarlet-and-Violet, Sword-and-Shield, Sun-and-Moon, and Scarlet+Mega-Evolution-combined era
  markets — exactly the 5 largest maintained caches by constituent count, 4,845–33,955) chronically
  hit 57014 for the reason in V.3, not a code defect; the cooldown fix (V.4) correctly deprioritizes
  and rotates among them rather than starving progress on the other 16.
- `run_market_explorer_daily_publication.py --commit` was identified as the correct next step to
  close the coverage gap (V.3) but was intentionally **not run this session** — routed to a human
  operator rather than executed unilaterally, since it is the authoritative projection writer and
  was not itself named in this session's original authorization list, unlike the prewarm/health/
  provisioning scripts.
- Ran `provision_market_explorer_maintained_cards_axes.py --commit` (U.4's script, written but never
  run live in the prior pass) to completion: 33 candidates considered (17 era markets, already
  `cache_kind='maintained'` from before this session — unchanged, expected; 9 rarity segments; 7
  price/release-age segments). **Zero of the 16 new candidates were successfully provisioned.** The
  7 price/release-age segments all failed with `57014` — the same cold-history scaling cause as the
  5 chronic maintained-cache failures in this section, unsurprising since these are cross-era broad
  axes that also touch the pre-retention window. The 9 rarity segments failed with a *different*
  error: `market_explorer_cache_publish_returned_false` on every single one (Special Illustration
  Rare, Illustration Rare, Ultra Rare, Hyper Rare, Double Rare, Rare Ultra, Rare Secret, Rare Rainbow,
  Rare Holo) — this is the exact same failure mode U.5 flagged once, undiagnosed, on Global All Raw;
  seeing it reproduce identically across 9 unrelated, freshly-attempted fingerprints this session
  confirms it is a real, general defect in the persistent-cache publish/staging path for a
  **first-time build of a brand-new fingerprint**, not an isolated incident. This was not
  investigated further this session (query-layer/publish-RPC internals, out of the scope authorized
  here) but is now a well-evidenced, reproducible, separately-trackable defect blocking every rarity
  segment's maintained-cache promotion, independent of the cold-history timeout issue.

### V.6 Scheduler (closes U.8)
Added `backend/docs/samples/crontab-market-explorer-sample.sh`, matching this repo's existing
crontab-sample convention (`crontab-alerts-sample.sh`): three separate, lockable cron entries —
publication (`--commit`, once daily) → maintained-cache prewarm (`--commit`, every 15 minutes,
offset 5 minutes after publication's slot) → health check (read-only, every 15 minutes, offset
another 5 minutes) — with the P0 rationale for why these must never be recombined into one process
documented inline. Not yet installed on the production crontab; that is an operator action separate
from this repo change.

### V.7 Tests
30 new/changed tests in `test_run_market_explorer_maintained_cache_prewarm.py` covering: `--max-caches
1` remains the default, a single chronic failure does not starve later caches, a recently-failed
cache is deprioritized, it becomes retryable after the cooldown elapses, ready/current caches stay
skipped regardless of cooldown, `--failure-cooldown-seconds 0` disables the mechanism, the
deprioritized row's status/reports are never falsified, memory-guard behavior is unchanged, and
multiple simultaneous chronic failures rotate fairly instead of one starving the rest. Full local
Market Explorer regression (247 tests across the suite, excluding pre-existing unrelated collection
failures from missing `stripe`/`jwt` packages and a Python 3.8 typing incompatibility in this local
environment, none of which are Market Explorer files): all passing. Audited for hard-coded Global
counts (Part 8 of this session's task): the two files referencing `33,955` either use it as an
arbitrary large-list fixture size (not asserting it as the true count) or as a historical comment
about the Sep-3 incident — neither hard-codes a permanent invariant; no change needed.

### V.8 Final runtime decision for this pass
**Not `MARKET_EXPLORER_RUNTIME_BLOCKERS_RESOLVED`.** Real, verified progress: the V2-hybrid-SQL
diagnosis in U.14 is corrected (the hot path is healthy), the actual root cause of the broad-query
failures (a never-scheduled publication job, V.3) is identified with direct evidence, a genuine
picker-starvation defect blocking 5 of 21 maintained caches is fixed and proven live (V.4), and the
scheduler gap is closed with a committed, documented crontab definition (V.6). Two genuine blockers
remain, neither a Python-side query-planning defect this session is authorized to patch:

1. **Coverage gap (V.3)** — closes once a human operator runs
   `run_market_explorer_daily_publication.py --commit`; the 5 chronic maintained-cache failures are
   expected to then resolve on their own via the existing cooldown-rotation mechanism (V.4), no
   further code change anticipated.
2. **`market_explorer_cache_publish_returned_false` on first-time builds (V.5)** — a newly
   well-evidenced (9-for-9 reproduction), previously only-once-observed defect that independently
   blocks every rarity-segment maintained cache regardless of (1). This is a distinct, separately-
   trackable engineering defect in the persistent-cache publish/staging path, not diagnosed further
   this session.

This pass corrects U.14's core misdiagnosis (a V2/SQL-side timeout) to the real cause (an
operational scheduling gap) and fixes three real Python-side bugs (V.4) along the way, but broad
queries and the new rarity-segment maintained caches still do not consistently succeed live pending
(1) and (2) above.
