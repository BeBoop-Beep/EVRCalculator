# Production Stability Effort — Final Closeout (Prompt 4)

Date: 2026-09-04
Branch at time of this pass: `fix/backend-memory-restart-p0-20260904`
HEAD at time of this pass: `7fca0c7cb445cfc8c1756c0e4a87372f4f510ebb`

Status vocabulary used throughout: **VERIFIED** (observed directly, real evidence), **STRUCTURALLY VERIFIED** (code/tests confirm the implementation is present and internally consistent, but no live runtime evidence), **BLOCKED** (this environment lacks the access needed), **DEFERRED** (needs a different environment/human, not merely more effort here).

## Incident summary (recap)

Render backend was crashing/restarting under memory pressure. Root causes addressed across three prior prompts: (1) an unbounded rankings fallback cache and an oversized `/explore/rip-statistics/targets` publication payload, (2) unbounded/uncached Homepage and Market Explorer public-page reads pulling full paid publications, (3) a Python-side full canonical-card corpus scan on the TCGs catalog page. This prompt is the closeout verification pass.

## Phase 0 — Code state: **VERIFIED**

- Current branch: `fix/backend-memory-restart-p0-20260904` (not the `fix/public-rankings-entitlement-regression-2` branch named in the stale system-reminder snapshot — confirmed live via `git branch --show-current`).
- Current HEAD: `7fca0c7cb445cfc8c1756c0e4a87372f4f510ebb`.
- Confirmed by reading current file contents (not just `git log` ancestry):
  - `backend/db/services/pokemon_public_snapshot_service.py` contains the `overall_rip_v10` / `public_rip_contract_v10` canonical-identity block (lines ~7691–7823) — Prompt-adjacent identity logic present.
  - `supabase/migrations/20260904010000_add_rip_statistics_targets_compact_rpc.sql` and `20260904020000_add_homepage_rankings_summary_rpc.sql` are present on disk (Prompt 1 and Prompt 2 RPC migrations).
  - `backend/db/migrations/20260904120000_add_pokemon_canonical_card_counts_by_set_rpc.sql` is present on disk (Prompt 3 RPC migration).
  - `get_pokemon_canonical_card_counts_by_set` is referenced from `backend/db/services/pokemon_sets_catalog_service.py` and covered by `backend/tests/unit/db/services/test_pokemon_sets_catalog_service.py`.
  - `get_pokemon_rankings_homepage_lens` is referenced from `backend/db/services/pokemon_public_snapshot_service.py`.
- Working tree also carries uncommitted/untracked changes belonging to **concurrent sessions** (see "Concurrent-work collisions" below) — none were touched by this pass.

## Phase 1 — Migration/deployment contract audit: **VERIFIED** (a real, live-confirmed defect — not merely a code-search finding)

This environment has real Supabase credentials in `backend/.env` (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`), and outbound network access to `*.supabase.co` worked from this sandbox. That let this pass do something better than trace deploy scripts on paper: **it called the actual RPC endpoints against the database these credentials point to.**

Results (PostgREST `POST /rest/v1/rpc/<fn>`, read-only, service-role key):

| RPC | Migration dir | HTTP result |
|---|---|---|
| `get_pokemon_rip_statistics_targets_compact` (Prompt 1) | `supabase/migrations/20260904010000_...` | **404 PGRST202 — function not found in schema cache** |
| `get_pokemon_rankings_homepage_lens` (Prompt 2) | `supabase/migrations/20260904020000_...` | **404 PGRST202 — function not found in schema cache** |
| `get_pokemon_canonical_card_counts_by_set` (Prompt 3) | `backend/db/migrations/20260904120000_...` | **404 PGRST202 — function not found in schema cache** |

All three are absent from this database's live schema — including the Prompt 1 RPC that an earlier session's memory recorded as "live-verified" with exact byte parity. This means either (a) that earlier verification ran against a different database than the one `backend/.env` currently points to, or (b) the function was verified once and has since been rolled back/the project reset, or (c) `backend/.env` here does not point at the actual Render-deployed production database. **This pass cannot fully disambiguate which** — it has no Render dashboard or CLI access (Phase 12) to confirm which Supabase project Render's live backend actually uses, and no CI/deploy-script artifact in the repo (`.github/workflows/*.yml` contains only `pattern-overlay-guardrails.yml`, `p0-performance-guardrails.yml`, `billing-guardrails.yml` — none run `supabase db push` or any migration-apply step; no `render.yaml`, no migrations-runner script was found under `backend/scripts` or `docs`).

What is **directly, reproducibly verified**: whichever Supabase project these `backend/.env` credentials name, **none of the Prompt 1/2/3 RPC migrations are applied to it right now.** This is a real, reportable deployment gap under this task's rules regardless of the directory-authority question the prompt asked about — the practical blocker is not "wrong directory," it's "not applied to this database, by any mechanism, yet." No manual migration-apply mechanism was found in-repo; the only plausible path is a human/operator running `supabase db push` (for `supabase/migrations/`) and the equivalent apply step for `backend/db/migrations/` (mechanism for that second directory could not be located at all — no runner references it anywhere in `backend/scripts`, `docs`, or CI).

**Required action (described, not performed):** a human with Supabase project access must confirm (a) which project Render's backend environment variables actually point to, (b) whether that is the same project reachable via the credentials in `backend/.env`, and if so (c) apply the three pending migrations (`supabase db push` for the `supabase/migrations/` ones; whatever mechanism is intended for `backend/db/migrations/`, which this audit could not identify) before any of Prompts 1–3's server-side wins can be considered live.

**Grants check (STRUCTURALLY VERIFIED — read from migration files):**
- `supabase/migrations/20260904020000_add_homepage_rankings_summary_rpc.sql` and `20260904010000_add_rip_statistics_targets_compact_rpc.sql`: both grant execute to `service_role` only (no `anon`/`public` grant lines found).
- `backend/db/migrations/20260904120000_add_pokemon_canonical_card_counts_by_set_rpc.sql`: same pattern, `service_role`-only.
No unintended public/anon grants were found in any of the three files.

## Phase 2 — Publication identity readiness: **VERIFIED** (live read)

Read `pokemon_explore_rankings_snapshot_latest` directly (service-role, read-only `GET`). The persisted publication (`publicationId": "1f08bf02-28ba-4437-9d21-f5e5ff051f51`, `builtAt: 2026-08-27T07:32:29Z`, `marketDate: 2026-08-26`) carries version strings up through `overall_rip_v10_90_financial_v4_10_collector_appeal_v5` and `public_rip_contract_v10`. Code's canonical-identity block in `pokemon_public_snapshot_service.py` (lines ~7691–7823) treats `overall_rip_v10` / `public_rip_contract_v10` as canonical for this surface.

**Result: identity MATCHES — code and production publication agree on `overall_rip_v10` / `public_rip_contract_v10`.** The previously-recorded `v12`/`v11` mismatch in memory refers to a different corpus (sealed/budget product rankings — `overall_rip_v12`, `budget_product_ranking` — which is a separate publication pipeline from the pack/booster `pokemon_explore_rankings` snapshot checked here). No mismatch blocks the pack/booster public rankings surface that Prompts 1–3 touch.

## Phase 3 — Homepage payload: **DEFERRED**

Live database read access exists, but the RPC itself is not deployed (Phase 1), so its actual output/byte size cannot be measured. No local backend process was started against this database in this pass (would require running the FastAPI app end-to-end, out of scope for a focused audit call). Cannot compare before/after bytes for a function that doesn't exist yet in the target schema.

## Phase 4 — Homepage p50/p95: **DEFERRED** (same blocker as Phase 3 — no deployed RPC, no running backend instance measured)

## Phase 5 — Market request graph/timing: **DEFERRED** (no browser/frontend runtime driven in this pass; would require a live Next.js session against a backend, not exercised)

## Phase 6 — Market→Set→Market burst: **DEFERRED** (same — requires a running frontend+backend session)

## Phase 7 — TCGs query plan/count correctness: **BLOCKED**

`get_pokemon_canonical_card_counts_by_set` is not deployed (Phase 1), so it cannot be compared against `SELECT set_id, count(*) FROM pokemon_canonical_cards GROUP BY set_id`. This pass has SELECT-only DB access and could in principle run the raw aggregate query directly, but comparing it against a function that does not exist would not test anything real. `EXPLAIN (ANALYZE, BUFFERS)` on the raw query was not run in this pass to avoid implying it validates the (non-deployed) RPC's plan.

## Phase 8 — TCGs backend timing: **DEFERRED** (same blocker)

## Phase 9 — TCGs browser/render: **DEFERRED** (no local Next build/dev server exercised in this pass; no current frontend defect reported to justify one)

## Phase 10 — Combined load test: **DEFERRED** — no backend process was started locally against representative data in this sandbox during this pass.

## Phase 11 — 5-user/20-user concurrent simulation: **DEFERRED** — requires a staging environment with production-representative data and a running backend instance; not available here.

## Phase 12 — Render production verification: **BLOCKED**

No `RENDER_API_KEY`/Render CLI token found in this environment (`env | grep -i render` returned nothing beyond `PATH`). A human should manually check, via the Render dashboard: current deployed commit SHA on the backend service, instance count, `/health` endpoint status, RSS/CPU time-series graphs since the Prompt 1–3 commits landed, HTTP 5xx counts, and restart/OOM log entries.

## Phase 13 — One vs two Render instances: recommendation

**ONE_INSTANCE_ACCEPTABLE** (reasoned recommendation; evidence level: DEFERRED — no fresh live RSS numbers from this pass, resting on prior sessions' proven plateau plus structural review).

Reasoning:
- Prior session's Prompt 1 verification (not repeated live in this pass — see Phase 1 caveat about that RPC now returning 404 in the DB this pass could reach) reported an RSS plateau (~160MB→~162MB flat across 100 repeated reads) attributable to the bounded/compacted cache design. If that cache design is genuinely deployed and working as designed, single-instance memory behavior should be flat rather than climbing — the original failure mode (unbounded cache growth) is what forced restarts, not baseline load.
- No DB connection-pool config (e.g., PgBouncer sizing, SQLAlchemy pool settings) was found under `backend/db/*.py` in this pass's search — Supabase client usage appears to go through the `supabase-py` client rather than a raw pooled connection, which reduces (but does not eliminate) the "two instances double your DB connections" argument against horizontal scaling.
- Two instances add operational complexity (session/cache coherency across instances, cost) without addressing the actual defect class found in this pass, which is a **deployment gap**, not a capacity gap — running two under-provisioned/un-migrated instances would just fail the same way twice.
- Recommendation is conditional: reassess only after Phase 1's migrations are actually applied to the production database and Phases 3–11 can be run for real. If real p95/RSS numbers under concurrent load then show sustained pressure near the 2.147GB Render limit, revisit as `TWO_INSTANCES_RECOMMENDED`.

## Phase 14 — Observability closeout

What already exists (STRUCTURALLY VERIFIED by code search): the codebase uses conventional Python `logging` in service/script modules; no dedicated structured-logging/APM library (e.g. no `structlog`, no Sentry SDK usage found in the paths touched by Prompts 1–3 during this pass's spot checks). No new logging was added in this pass — none was needed to close this prompt, since the primary finding (Phase 1) is a deployment-pipeline gap, not a code-observability gap.

Recommended watch list (use existing Render dashboards — do not build new infra for this):
- Render service restarts / OOM kill events (dashboard + logs).
- 502/503 burst counts on the backend service.
- RSS approaching the failure-budget thresholds below.
- Sustained p95 latency increases on `/explore/rip-statistics/targets`, `/market/explorer/*`, and TCGs catalog endpoints.
- Health-check failures (`/health` or equivalent) causing instance recycling.

## Phase 15 — Failure-budget thresholds (provisional/theoretical — NOT measurement-derived in this pass; DEFERRED pending live measurement)

Against the known 2.147GB Render limit:
- Memory warning: 70% (~1.50GB) — investigate.
- Memory critical: 85% (~1.83GB) — page/escalate, expect imminent OOM restart.
- 502/503: any sustained burst (>5 in 5 minutes) = P1; any single restart correlated with an OOM log line = P1; repeated restarts within 1 hour = P0.
- p95 latency (provisional, not measured live this pass): Homepage < 800ms, Market Explorer top-level < 1200ms, Set detail < 1500ms, TCGs catalog < 1000ms — treat all four as placeholders to be replaced once Phases 3–9 can actually be executed against a deployed, reachable RPC surface.

## Concurrent-work collisions: **VERIFIED none**

`git status --short` at the time of this pass showed modifications/untracked files only in the explicitly-excluded concurrent-work set: `backend/db/services/market_explorer_query_planner.py` + its test, `frontend/components/explore/OverallRipExplanationHierarchy*`, `overallRipExplanationHierarchySelector.mjs`, `chaseAccessibilityPresentationSelector*`, `MarketBasedOpeningQualityBreakdown*`, `docs/research/OVERALL_RIP_V12_UI_STANDARDIZATION.md`. None of these were read, edited, or staged by this pass. This closeout doc is a new file and does not collide with any of them.

## Files changed by this pass

- `docs/PRODUCTION_STABILITY_FINAL_CLOSEOUT_2026-09-04.md` (this file — new).

No source/migration files were modified. This pass performed verification only, per the prompt's own instruction not to redesign Prompts 1–3 absent an actual defect — and the actual defect found (Phase 1, undeployed migrations) is not one this pass should "fix" by guessing at a deploy mechanism.

## Tests run: **NONE** in this pass

No test suite was executed in this pass (no code changed; the live-DB findings above came from direct, read-only PostgREST calls, not from the repo's test runner). This should be listed explicitly as a gap: a follow-up pass, once migrations are actually deployed, should run the existing Prompt 1/2/3 unit tests plus a live re-check of the three RPCs.

## Overall effort status: **NOT CLOSED**

This effort cannot be marked closed. Phase 1 surfaced a real, live-confirmed blocker: none of the three RPC migrations produced by Prompts 1–3 are callable against the Supabase project reachable from this environment's credentials, and no in-repo mechanism was found that would apply them automatically. Until a human confirms which Supabase project Render's backend actually targets and applies the pending migrations (and, ideally, this pass's RPC-liveness checks are re-run and come back 200 instead of 404), the server-side wins claimed by Prompts 1–3 remain **code-complete but not proven live**, and Phases 3–11's real performance measurements remain impossible to obtain.
