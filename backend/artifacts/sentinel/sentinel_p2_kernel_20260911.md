# inDex Sentinel — Prompt 2 Deterministic Kernel

Date: 2026-09-11  
Branch: `feature/sentinel-p2-kernel-20260911`  
Parent: Sentinel P1 head `19eb7cde47849c0d6a7038c1f94b4a71a97da615`

## Scope

Prompt 2 builds only the deterministic Sentinel control-plane kernel.

It does **not**:

- register production Market/Rankings/TCG/scraper checks,
- mutate production business data,
- enable automated recovery,
- call any AI provider,
- apply a Supabase schema change,
- change VM cron,
- change `main`,
- deploy Render or Vercel.

## Kernel contracts

Implemented:

- typed `CheckResult` outcomes and severity,
- bounded check registry with per-check confirmation thresholds,
- deterministic incident fingerprinting from `check_key + failure_code + authority_identity`,
- `HEALTHY → SUSPECT → FAILING` check-state transitions,
- active incident open/update/resolve behavior,
- same-failure deduplication,
- authority change closes the previous active incident and starts a fresh confirmation window,
- bounded/redacted evidence bundles,
- heartbeat persistence boundary,
- Noop, in-memory, and service-role Supabase state-store implementations,
- fail-closed runtime configuration,
- disabled triage provider,
- one-shot runner and inert `--self-test`.

## Safety defaults

```text
SENTINEL_STATE_WRITES_ENABLED=false
SENTINEL_RECOVERY_ENABLED=false
SENTINEL_AI_ENABLED=false
```

`recovery=true` or `ai=true` causes Prompt-2 runner startup to fail closed because those capabilities do not exist yet.

Normal Prompt-2 runner invocation has no production checks registered and therefore returns `no_checks_registered` rather than falsely claiming production is healthy.

`--self-test` always uses the Noop state store even if persistence is enabled in the shell.

## Persistence proposal

`backend/db/proposals/sentinel_kernel_v1.sql` defines the intended internal tables:

- `sentinel_check_state`
- `sentinel_incidents`
- `sentinel_recovery_attempts`
- `sentinel_component_heartbeats`

Security contract:

- RLS on every public-schema Sentinel table,
- all privileges revoked from `PUBLIC`, `anon`, and `authenticated`,
- service-role-only CRUD,
- no privileged helper RPC,
- no public RPC.

The SQL is a **proposal only**. No production SQL was executed and no migration filename was invented. A real migration must be generated with the repository's Supabase CLI workflow after explicit activation approval.

## VM provenance contract

Sentinel must not assume the scraper VM is byte-identical to remote `main`.

The production contract is:

1. VM branch remains `main`.
2. Runtime is based on an approved `main` release.
3. A small explicit VM-only overlay may be present.
4. Sentinel should compare observed drift against an approved overlay manifest/fingerprint.
5. Unrecognized drift is an incident; approved overlay differences are not.

The overlay manifest itself is not created by Prompt 2 because the canonical list of VM-only files must first be inventoried.

## Tests

Focused unit coverage added (**29 passed**) for:

- registry validation,
- confirmation thresholds,
- stable/authority-scoped fingerprints,
- evidence redaction and size bounds,
- no-op state behavior,
- incident open/update/resolve/dedup,
- authority rollover and fresh confirmation windows,
- execution-error handling,
- disabled AI triage,
- runner fail-closed behavior,
- heartbeat boundary,
- SQL/RLS/service-role security contract.

CLI smoke behavior was also verified locally:

- `python -m backend.sentinel.runner --self-test` → exit 0, healthy, nonpersistent,
- normal Prompt-2 runner with no registered checks → exit 2, `no_checks_registered`,
- `--list-checks` → empty list, as expected before Prompt 3.

## Production mutation

`NONE`

## Next phase

Prompt 3 should add adapters for existing authorities only:

- existing market freshness watchdog,
- scrape batch/heartbeat/lease state,
- publication gate,
- publication audit,
- alert dispatcher health,
- set-page generation state.

Those adapters should register checks into this kernel; they should not duplicate existing business logic.

Completion target:

`SENTINEL_P2_KERNEL_COMPLETE_SCHEMA_NOT_DEPLOYED`
