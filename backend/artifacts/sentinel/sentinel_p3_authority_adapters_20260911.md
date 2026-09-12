# inDex Sentinel — Prompt 3 Existing Authority Adapters

Date: 2026-09-11  
Branch: `feature/sentinel-p3-authority-adapters-20260911`  
Parent: P2 kernel `874e34205fff05023a670fc6afbd1c9b72babcbb`

## Scope

Prompt 3 wires existing inDex authorities into the deterministic P2 Sentinel kernel.

It remains **observation-only**:

- no production DB writes,
- no recovery calls,
- no AI calls,
- no VM/crontab changes,
- no `main` or `develop` merge,
- no Render/Vercel deployment,
- no Sentinel schema deployment.

## Fast authority profile

`build_fast_registry()` registers five bounded checks:

### `alerts.delivery`

Reuses `backend.alerts.dispatcher.get_dispatcher_health()`.

It does not duplicate backlog/configuration calculations. It classifies the existing structured result into stable Sentinel failure codes such as:

- `alert_delivery_disabled`
- `alert_webhook_missing`
- `alert_schedules_unconfirmed`
- `alert_backlog_stalled`
- `alert_delivery_stalled`

The live P1 baseline already proves this check would currently fail production because delivery is disabled, schedules are absent, and 143 historical rows are pending.

### `market.freshness`

Calls the existing `run_watchdog(..., queue_failures=False)` only.

Sentinel never queues legacy watchdog alerts from this adapter. Existing watchdog failure classes remain the authority. A deterministic priority is used only to select one incident fingerprint when the watchdog reports multiple simultaneous failures; all failures remain in bounded evidence.

`market_watchdog_execution_failed` maps to `market_watchdog_state_load_failed`.

This check retains a two-observation confirmation window for future persistent Sentinel state because transient dependency failures are possible.

### `scrape.queue_leases`

Read-only observation of `scrape_jobs` rows with `status='running'`.

It mirrors the stale-running predicate already defined by the canonical DB lease watchdog:

- explicit `lease_expires_at < now()`, or
- legacy running row with no lease and `started_at` older than the canonical 7200-second grace.

The adapter test pins the 7200-second constant to migration `048_scrape_queue_batch_lease_orchestration.sql` so drift is visible.

No reconciliation RPC is called.

### `publication.batch_gate`

Reuses `backend.db.services.publication_gate.evaluate_publication_gate()` in read-only mode.

Responsibility is deliberately separated from freshness timing:

- missing batch or pending/running incomplete batch is a normal/not-yet-eligible gate state,
- freshness watchdog decides when that state becomes late,
- terminal `failed` / `incomplete`, invalid batch contract, authority unavailable, or gate bypass is a Sentinel failure.

This prevents duplicate alarms from two layers owning different semantics.

### `setpage.generation`

Reads the canonical generation pointer and generation row directly:

- `pokemon_set_page_snapshot_current_generation`
- `pokemon_set_page_snapshot_generations`
- `pokemon_set_page_snapshot_generation_rows`

Expected counts are always read dynamically from the generation row. No magic `210` is encoded.

The pointer is healthy only when its generation:

- exists,
- matches scope,
- is `published`,
- passed validation,
- has `published_at`,
- has positive expected count,
- completed count equals expected count,
- persisted generation-row count equals expected count.

## Heavy audit profile

`build_audit_registry()` registers only:

`publication.audit.post_scrape`

It calls the existing canonical `run_market_publication_audit(..., phase='post-scrape')` rather than restating public-surface rules.

The heavy audit is intentionally separate from the fast profile so it is not accidentally run every few minutes. Sentinel stores only a compact summary of failed sets/sections rather than the full audit payload.

## Operational runner

`python -m backend.sentinel.operational --profile fast|audit|all`

Prompt 3 hard-refuses:

- `SENTINEL_STATE_WRITES_ENABLED=true`
- `SENTINEL_RECOVERY_ENABLED=true`
- `SENTINEL_AI_ENABLED=true`

Therefore the operational runner cannot mutate Sentinel persistence yet even if someone misconfigures the shell.

`--list-checks` performs no external reads.

## Live read-only contract verification

Supabase was queried read-only during implementation:

- latest 2026-09-11 scrape batch: `complete`, 165 expected / 165 succeeded / 0 failed / 0 missing;
- running scrape jobs: 0;
- stale running jobs under the canonical lease predicate: 0;
- active `pokemon` set-page generation: published and validation-passed;
- expected set count: 210;
- completed set count: 210;
- persisted generation rows: 210.

These numbers are observations only. None are hardcoded into Sentinel.

P1 VM evidence remains authoritative for alert delivery: webhook configured, delivery disabled, dispatcher/watchdog schedules absent, 143 pending unsuppressed alerts, and the old production watchdog crashes on the already-fixed dashboard column defect.

## Test coverage authored

Prompt 3 adds 27 focused tests:

- 20 authority-adapter tests,
- 5 registry/profile tests,
- 2 operational safety tests.

They cover:

- dispatcher health classification,
- watchdog read-only invocation and deterministic failure selection,
- exact lease-expiry and legacy grace semantics,
- publication gate responsibility separation,
- dynamic generation counts and failure classes,
- compact heavy-audit evidence,
- profile isolation,
- observation-only runtime guardrails.

### Execution limitation

The ChatGPT execution container cannot resolve `github.com`, and this public branch cannot be cloned into that container. No PR was opened because that could trigger repository/preview automation and the project intentionally limits deployments.

Therefore Prompt 3 does **not** claim a test pass yet. The exact focused command to run in the normal local repository is:

```bash
pytest -q \
  backend/tests/unit/sentinel/test_kernel.py \
  backend/tests/unit/sentinel/test_runner.py \
  backend/tests/unit/sentinel/test_sql_contract.py \
  backend/tests/unit/sentinel/test_authority_adapters.py \
  backend/tests/unit/sentinel/test_authority_registry.py \
  backend/tests/unit/sentinel/test_operational.py
```

The three P2 files previously passed 29/29 before this phase; the new P3 files still require execution on the normal repo/runtime before P4 should be stacked.

## Production mutations

`NONE`

## Completion state

`SENTINEL_P3_CODE_COMPLETE_TEST_EXECUTION_PENDING`

Do not begin Prompt 4 public semantic monitoring until the focused P2+P3 Sentinel suite passes in the normal repository environment.
