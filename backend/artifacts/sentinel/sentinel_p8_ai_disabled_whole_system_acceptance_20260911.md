# inDex Sentinel — Prompt 8 AI-Disabled Whole-System Acceptance

Date: 2026-09-11  
Branch: `feature/sentinel-p8-ai-disabled-acceptance-20260911`  
Parent: accepted P7 head `aedb4739d71a1924de44452fe294f24456b33334`

## Status

`SENTINEL_P8_CODE_COMPLETE_TEST_EXECUTION_PENDING`

Prompt 8 does **not** activate production Sentinel.  It closes the architecture
with an explicit zero-AI operating mode, a hard future AI budget contract, and a
non-mutating whole-system activation preflight.

## Accepted foundation through P7

User-executed acceptance gates completed on the real local environment:

- P3 combined Sentinel suite: 56 passed.
- P4 public semantic suite: 75 passed.
- P5 independent-monitoring suite: 95 passed.
- P6 safe-recovery suite: 118 passed.
- P7 backend suite: 138 passed.
- P7 frontend Sentinel contract tests: 10 passed.
- P7 auth-canary syntax check: passed.
- P7 Next.js 15.5.15 production build: passed after loading the normal frontend
  `.env.local`; page-data collection, 78/78 static pages, traces, and final page
  optimization completed.

The live authenticated canary itself remains intentionally deferred until the
canary code is released and a dedicated non-human account is provisioned.

## P8 zero-AI contract

Sentinel's deterministic monitoring/recovery system is complete without AI.

Supported production default:

```text
SENTINEL_AI_ENABLED=false
SENTINEL_AI_PROVIDER=disabled
SENTINEL_AI_MONTHLY_BUDGET_CENTS=0
```

Properties:

1. `DisabledTriageProvider` performs no external I/O and always reports
   `request_made=false`.
2. The provider factory independently refuses an enabled AI path even if a
   caller bypasses ordinary configuration validation.
3. P8 ships no OpenAI, Anthropic, or other paid triage provider adapter.
4. Enabling AI requires explicit persistent-state, schema, execution-readiness,
   budget-ledger, provider, and positive-budget gates.
5. Even after all gates are populated, P8 still refuses AI because no paid
   provider implementation is installed.
6. Therefore the P8-supported operating mode has a hard AI spend of **$0**.

## Future AI budget ceiling

`backend/sentinel/ai_budget.py` defines:

```text
AI_HARD_MONTHLY_CAP_CENTS = 1000
```

The environment may configure a lower future budget (for example $5), but can
never raise the application policy above $10.

`backend/db/proposals/sentinel_ai_budget_v1.sql` is a **future proposal only**.
It is not a migration and was not applied.

The proposal adds a service-role-only monthly budget row and a `SECURITY
INVOKER` atomic reservation function.  A future provider must reserve its
conservative worst-case request cost *before* the provider request.  PostgreSQL
performs the increment and remaining-envelope predicate in one atomic UPDATE so
concurrent workers cannot both consume the same remaining budget.

Reservations are intentionally not refunded.  That can under-use the budget,
but cannot over-spend the reserved envelope when every future provider request
is forced through the gate.

No future provider should be approved until it demonstrates that its
worst-case reservation estimate is a true upper bound on provider cost.

## Whole-system activation preflight

`python -m backend.sentinel.acceptance` is non-mutating.  It distinguishes:

- **code ready** — deterministic Sentinel and zero-AI contract are valid,
- **production activation pending** — production infrastructure/manual gates
  still need explicit approval.

It never:

- applies SQL,
- edits cron,
- suppresses alerts,
- deploys code,
- changes the VM branch,
- enables recovery,
- sends an AI request.

The preflight exposes a dedicated `--assert-zero-ai` gate for release
verification.

## Activation order

No activation step is automatic.  Every stage requires explicit approval.

### 1. Deploy core persistence

Generate the real migration using the repository's canonical Supabase migration
workflow from `sentinel_kernel_v1.sql`, review it, then apply it.

Do **not** apply `sentinel_ai_budget_v1.sql`; AI remains disabled.

Keep:

```text
SENTINEL_RECOVERY_ENABLED=false
SENTINEL_AI_ENABLED=false
```

### 2. Clean the historical alert backlog

Before enabling delivery:

1. snapshot the pending backlog,
2. choose an explicit historical cutoff,
3. run `suppress_historical_alert_backlog.py` in dry-run mode,
4. human-review the exact affected rows/counts,
5. only then run the approved commit suppression,
6. verify post-cutoff alerts remain deliverable.

Do not simply enable the dispatcher against the existing historical backlog.

### 3. Activate alert delivery

Enable alert configuration and install/validate the canonical dispatcher and
freshness-watchdog schedules.

Send one controlled test and verify dispatcher health.

### 4. Start observation profiles

Run fast/public/audit profiles with persistent Sentinel state while recovery is
still disabled.

This establishes real incident fingerprints, evidence quality, and alert-noise
behavior before mutation is allowed.

### 5. Start the independent watcher

Run heartbeat/dead-man observation outside the scraper VM failure domain.

A dead scraper VM must remain detectable when the VM itself cannot execute any
Sentinel code.

### 6. Activate deployment/runtime canaries

After a real release:

- set the expected release SHA explicitly,
- inventory legitimate VM-only differences,
- create the approved VM overlay manifest,
- keep the VM on `main`,
- verify the approved release is an ancestor of the VM runtime,
- fail only on unapproved overlay drift.

Never require raw VM HEAD equality to remote `main`.

### 7. Activate the auth synthetic

Provision a dedicated non-human canary account, store its credentials only in a
server-side/scheduler secret surface, and run the P7 Playwright navigation
synthetic against the released frontend.

The synthetic validates both the cookie-backed `/api/auth/me` identity and the
rendered authenticated header after route-triggered reconciliation.

### 8. Observation burn-in

Run detection-only long enough to review:

- incident volume,
- false positives,
- evidence quality,
- independent watcher behavior,
- deployment/runtime canary behavior,
- authenticated-navigation synthetic results.

No recovery activation should occur merely because the code exists.

### 9. Optional bounded recovery

Only after separate approval, enable all three recovery gates and retain the P6
exact allowlist:

- `market.freshness / market_publication_stale`
- `scrape.queue_leases / scrape_job_lease_expired`

Keep one mutation attempt per incident, audit-before-mutation, crash-replay
blocking, and deterministic post-verification.

### 10. Keep AI disabled

AI is not required for the Sentinel launch.  Unknown failures still produce
bounded evidence and incidents for human review.

A future AI project is a separate approval decision, not a dependency of this
system.

## P8 acceptance tests

P8 adds 26 backend tests:

- 12 zero-AI/budget/config/provider tests,
- 6 future budget SQL contract tests,
- 8 whole-system acceptance/preflight tests.

Accepted P7 backend baseline: 138 tests.  Expected P8 combined backend total:

```text
164 passed
```

Additional CLI acceptance:

```text
python -m backend.sentinel.acceptance --assert-zero-ai
```

Expected exit code: `0` with:

```text
status = code_ready_activation_pending
ai.zero_ai_spend_mode = true
ai.enabled = false
ai.provider = disabled
ai.hard_monthly_cap_cents = 1000
```

`production_activation_ready=false` is expected before the manual activation
sequence above.

## Production mutation

`NONE`

Prompt 8 performed no:

- `main` merge/push,
- VM branch/worktree mutation,
- Supabase DDL/DML,
- alert suppression/send,
- cron/env activation,
- Render/Vercel deployment,
- recovery execution,
- AI/model request.

## Completion target

After the 164-test combined suite and zero-AI CLI assertion pass:

`SENTINEL_P1_P8_CODE_ACCEPTED_PRODUCTION_ACTIVATION_PENDING`
