# inDex Sentinel — Prompt 6 Safe Self-Healing

Date: 2026-09-11  
Branch: `feature/sentinel-p6-safe-self-healing-20260911`  
Base / accepted P5 head: `77392935af326e7b62e801d41dd1d4b250af5f5f`  
P6 code/test head before this report: `f5cdf07ae513bd28097bc77cffe96d4e47a18fff`

## Scope

Prompt 6 adds a bounded deterministic recovery layer on top of the accepted P1-P5 observation stack.

It does **not** activate recovery in production, deploy the Sentinel persistence schema, modify VM cron, mutate production data, modify `main`, deploy Render/Vercel, or enable AI.

## Initial automatic recovery allowlist

Only these exact check/failure signatures are eligible:

1. `market.freshness / market_publication_stale`
   - runbook: `publish_post_scrape_if_needed_v1`
   - uses the existing canonical `publish_if_needed()` wrapper
   - requires the same live failure/authority to still exist immediately before recovery
   - requires the canonical publication gate to be `allowed_complete` with `override=False`
   - never force-publishes
   - verifies by rerunning the deterministic market freshness check

2. `scrape.queue_leases / scrape_job_lease_expired`
   - runbook: `reconcile_stale_scrape_leases_v1`
   - invokes only the existing narrow DB lease-reconciliation primitive
   - does **not** invoke the broader `reconcile_stale_scrape_jobs.py --commit` CLI
   - requires the same live lease failure/authority and stale-job evidence immediately before recovery
   - verifies by rerunning the deterministic lease check

Every other Sentinel failure remains observation/escalation only.

## Recovery activation gates

Recovery is disabled by default.

`SENTINEL_RECOVERY_ENABLED=true` is accepted only when all three explicit gates are also true:

```text
SENTINEL_STATE_WRITES_ENABLED=true
SENTINEL_PERSISTENCE_SCHEMA_READY=true
SENTINEL_RECOVERY_EXECUTION_READY=true
```

This separates persistence activation from mutation authorization.

AI remains unsupported/disabled in this phase.

## Recovery lifecycle

A recovery attempt is considered only after the normal Sentinel pass has produced a **confirmed** incident. A `SUSPECT` observation cannot trigger mutation.

Before mutation, the engine verifies:

- exact allowlist match,
- persistent Sentinel state store,
- registered check identity,
- incident status is `OPEN`,
- the incident is still the current `FAILING` incident for that check,
- no unfinished prior attempt exists,
- attempt limit has not been reached,
- cooldown is not active,
- runbook-specific live preconditions still pass.

The recovery attempt is persisted with status `started` **before** the mutation callback executes. The incident is then marked `recovering` and its attempt count incremented.

Initial P6 runbooks have a maximum of one automatic mutation attempt per incident.

## Crash / replay safety

An unfinished prior `started` recovery attempt blocks automatic replay with:

`recovery_prior_attempt_unfinished`

This is deliberate. If a process dies after the audit record is persisted but before it can record whether the mutation occurred, Sentinel refuses to guess and mutate again.

The proposed SQL contract already has:

`UNIQUE (incident_id, runbook, attempt_number)`

so concurrent attempt-number collisions fail before a second recovery can proceed.

## Verification contract

A recovery is successful only if its deterministic verifier returns:

- a `CheckResult`,
- for the same check key,
- for the same incident authority (when authority is present),
- with outcome `healthy`.

Only then is the normal `IncidentManager` used to resolve the incident/reset check state.

A failed verification escalates the original incident. It is intentionally **not** fed back through the normal incident-signature rollover path during the recovery transaction, preventing recovery loops or silent replacement incidents.

Callback contract defects fail closed:

- invalid precondition return -> block before attempt/mutation,
- invalid execute return -> escalate and conservatively record possible mutation,
- invalid verifier type/check/authority -> failed verification + escalation.

Arbitrary exception messages are not persisted by the recovery engine; only bounded safe metadata such as exception class is retained.

## Persistence additions

The existing persistence boundary now supports `sentinel_recovery_attempts` through:

- `RecoveryAttemptRecord`,
- `RecoveryAttemptStatus`,
- `get_latest_recovery_attempt(...)`,
- `save_recovery_attempt(...)`.

The existing proposal remains service-role only and non-deployed. Prompt 6 creates no migration and applies no DDL.

## Explicitly not auto-recovered in P6

Examples that remain report/escalation only include:

- auth/session regressions,
- Rankings disappearance,
- TCG disappearance,
- Market membership/root-authority changes,
- set-page generation pointer corruption,
- registry/runtime provenance mismatch,
- dirty production VM,
- Render/Vercel failures,
- publication audit failures other than the exact stale-publication signature,
- broad market-date reconciliation,
- database migrations/schema changes,
- git operations/deployments,
- force publication,
- historical backfills,
- billing/secrets/policy changes.

## Tests added

P6 adds focused coverage for:

- exact recovery allowlisting,
- persistent-state requirement,
- audit-before-mutation ordering,
- publication gate refusal,
- canonical publication wrapper + post-verification,
- narrow lease reconciliation + post-verification,
- one-attempt ceiling,
- cooldowns,
- precondition blocks consuming no attempts,
- recovery exception redaction,
- failed-verification escalation,
- no replacement incident during failed verification,
- triple activation gates,
- no recovery during `SUSPECT`,
- persistence serialization/readback shape,
- unfinished-attempt crash/replay protection,
- SQL uniqueness/security contract,
- invalid precondition/execute/verifier callback contracts,
- wrong-authority healthy verification refusal.

The accepted P1-P5 focused suite contains 95 tests. P6 adds 23 focused tests, for an expected acceptance total of **118 tests**.

Acceptance execution is intentionally left to the repository's Python 3.8-compatible local environment before P6 is accepted.

## Production mutation

`NONE`

No production recovery was executed. No production Sentinel table was created. No alert backlog was changed. No cron/environment configuration was changed. No deployment was triggered.

## Next phase

Do not begin P7 until the full focused P1-P6 acceptance command passes.

After P6 acceptance, Prompt 7 should add authentication/deployment canaries while keeping recovery allowlisting unchanged unless separately reviewed.

Completion state:

`SENTINEL_P6_CODE_COMPLETE_PRODUCTION_RECOVERY_DISABLED`
