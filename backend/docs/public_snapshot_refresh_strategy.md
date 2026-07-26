# Public Snapshot Refresh Strategy

Public Pokemon analytics snapshots are materialized read models. The frontend and public API routes read these prepared rows:

- `pokemon_set_cards_snapshot_latest`
- `pokemon_set_market_dashboard_snapshot_latest`
- `pokemon_explore_rankings_snapshot_latest`
- `pokemon_set_page_snapshot_latest`
- `pokemon_desirability_validation_snapshot_latest`

Route render must stay read-only. It should not repair missing sections, rerun simulations, derive card appeal payloads, or rebuild snapshot subcomponents during a page request.

## Source-Driven Refresh

Price scrapes, simulations, desirability jobs, and future vendor imports do not need exact timing coordination. Instead, run:

```powershell
python backend/scripts/refresh_stale_public_snapshots.py --commit
```

The script compares each snapshot's `updated_at` against the newest relevant source timestamp. A snapshot is stale when:

- a snapshot row is missing
- a dependency is newer than the snapshot
- a required completeness marker is missing
- known stale warnings remain even though source rows now exist

Use `--dry-run` to inspect the plan without writes:

```powershell
python backend/scripts/refresh_stale_public_snapshots.py --dry-run
```

Use `--strict` in scheduler or CI-style checks to exit non-zero when stale/problem snapshots remain:

```powershell
python backend/scripts/refresh_stale_public_snapshots.py --commit --strict
```

To refresh one set:

```powershell
python backend/scripts/refresh_stale_public_snapshots.py --commit --set-id twilightMasquerade
```

## Scheduler

The daily simulation job (`infra/local/run_simulations_task.bat` → `infra/local/run_simulations.sh`, Windows Task Scheduler task "Run Simulation Jobs Daily") now chains `refresh_stale_public_snapshots.py --commit --strict` immediately after `run_all_v2_sets.py` finishes, so set pages always rebuild after the day's simulations and market dashboard rebuilds — never before. The refresh step runs even when the simulation batch partially fails, logs to `logs/refresh_public_snapshots.log`, and Slack-notifies success/failure; `--strict` makes the task exit nonzero when any set page snapshot is still older than its simulation/market dependencies (see the post-run set page freshness audit in the script's summary output).

Running `refresh_stale_public_snapshots.py --commit` additionally (e.g. hourly) remains safe and idempotent: overnight scrapes, later simulations, and future sources such as additional price vendors, graded pricing, sealed pricing, or other TCG imports can land whenever they finish. The refresh job will rebuild only the stale snapshot families and sets it detects.

## Batch-Gated Promotion (scrape cohort contract)

Downstream promotion is gated on the day's scrape cohort being
observation-complete. The authority is `public.pokemon_scrape_batches`
(migrations 047–049): `complete_scrape_batch_if_ready()` stamps `promoted_at`
and flips `status='complete'` only when every expected set has a valid Near Mint
observation for the market date.

Every commit-capable public-snapshot entry point (the stale-refresh, the
coordinated Cards + Market Dashboard builder, the Explore rankings builder, the
set-page builder, and the full `build_pokemon_public_snapshots` orchestration)
routes through the shared
`backend/db/services/publication_gate.enforce_cli_publication_gate` before it
promotes anything in `--commit` mode. The gate is evaluated **once per
invocation** (never per set) and the decision is reused.

### Operating modes (fail-closed by default)

The gate is selected by `PUBLICATION_GATE_MODE`:

- **`required`** (default; used for every production command) — the gate
  **fails closed**. Publication is allowed only when a valid batch row satisfies
  the *complete promotion contract*:
  `status == "complete"`, `promoted_at is not null`, `missing_set_count == 0`,
  `expected_set_count > 0`, a valid id, a valid market date, and (when
  `--market-date` is given) an exact market-date match. Everything else blocks:
  a query timeout, an auth/permission failure, a PostgREST/network error, a
  missing batch table, a missing batch row, a malformed response, a contradictory
  `complete` row, a pending/running/incomplete/failed batch, or any unclassified
  exception. **A failed database operation is never permission to publish, and
  never disables the gate.**
- **`disabled`** — ungated. Permitted **only** for explicitly configured
  local/test environments. It must be set deliberately; it is never inferred
  from a failed query.

An omitted or invalid mode resolves to `required`. Every decision carries a
structured `reason_code` (`allowed_complete`, `blocked_incomplete`,
`blocked_no_batch`, `blocked_authority_unavailable`,
`blocked_invalid_batch_contract`, `disabled_explicitly`, `manual_override`).

> **Deployment note:** because `required` fails closed, migrations 047–049 must
> be applied in production before the scheduled refresh will publish. Until they
> are applied the gate blocks (authority unavailable / no batch) and the refresh
> **defers** — set `PUBLICATION_GATE_MODE=disabled` deliberately only as a
> documented temporary bridge for an environment without the batch system.

### Behaviour

- **Batch `complete` (contract satisfied)** → gate open, promote as normal.
- **Anything else, in `--commit`** → gate closed. The run prints
  `publication gate CLOSED [reason_code]`, a machine-readable
  `PUBLICATION_DEFERRED …` line, promotes nothing, **preserves the previous good
  public snapshots**, and exits with the dedicated **deferred exit code `3`**
  (not `0`, not `1`). Missing sets are requeued by the scrape pipeline
  (`requeue_missing_scrape_jobs_for_batch`, migration 049), not by this refresh.
- **`--dry-run`** → read-only; reports what the gate decision *would* be and
  performs no writes.

Flags:

```powershell
# Gate on a specific America/Phoenix market date's batch.
python backend/scripts/refresh_stale_public_snapshots.py --commit --market-date 2026-07-25

# Manual recovery ONLY: promote even if the cohort is incomplete (loudly logged,
# recorded as reason_code=manual_override). Never part of the normal schedule.
python backend/scripts/refresh_stale_public_snapshots.py --commit --force-publish
```

`--force-publish` can never be activated implicitly and is never part of the
normal schedule.

## Exit Status and I/O-Safe Resumable Recovery

`refresh_stale_public_snapshots.py` plans work from **source freshness**, so it
only rebuilds the missing/stale/failed sets — not the full 166-set catalog.
A set that was rebuilt successfully becomes fresh and is skipped on the next
run, which is what makes reruns resumable (completion state is *derived*, not a
broad retry). This is the specific defense against the "full refresh caused high
Disk I/O and Supabase statement timeouts" incident: recovery is sequential (no
parallel DB-heavy snapshot generation) with bounded, transient-only retries and
exponential backoff per set (`_REBUILD_MAX_ATTEMPTS`, via
`snapshot_query_retry.run_snapshot_operation_with_retry`).

Exit status:

- The CLI returns **nonzero whenever any requested set (or global family) build
  fails** — even without `--strict`, and even when an inner builder catches its
  own exception and records it. A scheduler therefore never treats a partial
  recovery as success.
- `--strict` additionally fails the run on staleness/verification warnings and
  on the post-run set-page freshness audit.
- A closed publication gate is **deferred, not failed**: it exits with the
  dedicated code `3` (distinct from `0` success and `1` build failure) so the
  scheduler wrapper can send a "publication DEFERRED" warning instead of a
  success message, while staying visibly non-successful.

### Scheduler wrapper (`infra/local/run_simulations.sh`)

The wrapper captures the refresh exit code and branches:

- `0` → ✅ success message.
- `3` → ⏸️ "Public snapshot publication DEFERRED" warning (market date, batch
  status, missing-set count from the `PUBLICATION_DEFERRED` log line, and the
  operator action). It is **not** the success message and **not** the build-
  failure message, and the task stays non-successful (final `exit 1`).
- other nonzero → ❌ build-failure message.

The simulation-batch result is reported independently, so a simulation failure
and a publication deferral remain separately visible.

### Set-page strict verification is simulation-aware

`_verify_set_page` recognizes the `meta.simulationAvailability` contract. A page
explicitly labeled `available == false` may have empty `top_hits`,
`simulation_input_cards` source `NO_ROW`/`MISSING`/`NO_ROWS`, empty
simulation-derived sections, and no current OPvC / run id — and still passes
strict mode, provided it truthfully declares itself: valid identity,
`meta.snapshot`, `meta.snapshotCompleteness`, `meta.simulationAvailability`
with `available == false`, a `reason`, a non-empty `unavailableSections`
naming the simulation-derived sections, the simulation-unavailable warning, no
simulation-derived section falsely labeled fresh/current, and any carried-forward
section labeled `stale` with a source/data-as-of date. A page that claims
`available == true` keeps the stricter expectations; a malformed/identity-less
page still fails.

## Fail-Graceful Set Pages

`build_set_page_snapshot_row` no longer rejects a whole set page when simulation
data is missing. If the simulation/RIP aggregate is unavailable
(`get_explore_page_payload` raises `TARGET_NOT_FOUND` / "no simulation data"),
the builder publishes a **partial page**: identity, title, Cards, set value,
market, desirability, and RIP fields are published independently when their
sources exist, while simulation-dependent sections (Opening Profit vs Cost, RIP
metrics, pull rates, Simulation Drivers) are exposed as unavailable with a
warning and `meta.simulationAvailability` coverage metadata
(`available`, `unavailableSections`, `carryForward`, `carriedForwardSections`).
Genuine backend 5xx failures still propagate — only the missing-data case
degrades gracefully. Previous good simulation sections are only carried forward
under the existing, clearly-labeled `sectionFreshness` (stale) contract.

## Coordinated Movement Snapshots

Cards and Market Dashboard are one movement snapshot family. Rebuilding either
one rebuilds both from a single captured
`pokemon_canonical_card_market_prices_latest` context, UUID `generationId`, and
`builtAt` timestamp. Before any Market Dashboard write, the builder compares
all overlapping Cards, Market Movers, and Top Chase movement contracts and
aborts the write if identity, price, date, amount, percentage, coverage, or
window convention differs.

To rebuild one set explicitly:

```powershell
python backend/scripts/build_pokemon_set_market_snapshots.py --set-id ascendedHeroes --commit
```

The legacy `build_pokemon_market_dashboard_snapshots.py` entrypoint uses the
same coordinated implementation.

## Refresh Order

The dependency order is:

1. Coordinated Cards + Market Dashboard snapshots
2. Explore rankings snapshot
3. Set page snapshots
4. Desirability validation snapshot

Set page snapshots are built after rankings, cards, and market dashboards so they can embed fresh rank context, Simulation Drivers, card appeal validation payloads, and snapshot-completeness diagnostics.

## Full Rebuild

For a deliberate full rebuild, use:

```powershell
python backend/scripts/build_pokemon_public_snapshots.py --commit
```

That script uses the same high-level order above, but rebuilds everything rather than checking source freshness first.

## Route Contract

Public route render remains read-only:

- read prepared snapshot rows
- expose diagnostics from the snapshot payload
- return fast fallback shells only when the snapshot row is missing
- never perform live repair during route render

When a page shows stale warnings, fix the source snapshot by running the refresh or full rebuild script. Do not hide stale data in the frontend.

## Section-Level Freshness (one latest_market_date must not imply uniform currency)

The market dashboard's single `latest_market_date` describes the newest market
date available, not the freshness of every embedded section. The dashboard meta
now carries per-section source dates and a status for each:

- `setValueSourceDate` — newest set-value history date.
- `topChaseSourceDate` — newest genuinely **observed** Top Chase date. Forward-
  fill carry points are excluded, so a July-25 dashboard carrying July-16
  observed Top Chase reports `2026-07-16`, not the carried `2026-07-25`.
- `cardsSnapshotSourceDate` — the canonical selected-price date the coordinated
  Cards build used.
- `simulationSourceDate` — the Opening Profit vs Cost simulation date.
- `pageSourceDate` — the publication (build) date.

`meta.sectionFreshness` marks each section `current` / `stale` / `unavailable`
against the newest market date, `meta.sectionsUniformlyCurrent` is false whenever
any section lags, `meta.openingProfitVsCost` exposes the simulation date and its
stale/unavailable status, and a human-readable warning is appended for every
stale/unavailable section. The movement-parity guard is unchanged; this makes a
stale Cards/Top Chase section explicitly visible rather than silently uniform.

## Publish-time cache invalidation and client hydration guard

Two frontend-facing protections keep a newer published source from being
shadowed by an older cached/seeded response:

- **Invalidate on publish.** After a successful coordinated Cards/Market or set-
  page rebuild, `refresh_stale_public_snapshots.py` calls
  `notify_set_snapshot_published(...)`
  (`backend/db/services/set_publication_revalidation.py`), which POSTs to the
  Next.js route `app/api/internal/revalidate-set` to `revalidateTag` the
  `pokemon-set-shell:<setId>` and `pokemon-set-overview:<setId>:<window>` cache
  tags. It is best-effort and a no-op unless `SET_REVALIDATION_URL` and
  `SET_REVALIDATION_SECRET` are set (the route also requires the secret via the
  `x-revalidate-secret` header). Configure both on the sim host `.env` and set
  the same secret on the frontend deployment.
- **Client hydration guard.** `chooseFresherMarketPayload` (in
  `components/explore/marketAsOfDate.mjs`) compares the server seed and the live
  client/API response by market as-of date; the set-detail client displays the
  fresher-dated payload, so a stale server seed can never override a newer live
  response (and a stale-while-revalidate live response never overrides a newer
  seed).

## Simulation Recovery (canonical command, scheduler, and the 2026-07-17 stop)

### Canonical command and scheduler entry

The daily simulation is `backend/scripts/run_all_v2_sets.py`. It is not a cron
job — it runs on the **Windows** host via **Task Scheduler task "Run Simulation
Jobs Daily"**, which launches `infra/local/run_simulations_task.bat` →
Git Bash → `infra/local/run_simulations.sh`. That shell script chains, in order:

1. `python backend/scripts/run_all_v2_sets.py` (the simulation batch)
2. `python backend/scripts/refresh_stale_public_snapshots.py --commit --strict`
   (public snapshot promotion — runs even if the batch partially failed)

The scrape pipeline that feeds simulation inputs is a **separate** host: the
Oracle Ubuntu VM crontab (see `scraper_vm_operations.md` §8 — batch creation
03:00 America/Phoenix, per-minute worker dispatch, batch-missing monitor).

### Per-set isolation and exit status (already correct — verified)

`run_all_v2_sets.py` runs each set in `run_single_set`, which wraps
`orchestrator.run(...)` in its own `try/except`; a set that raises is recorded
as failed and the batch continues to the next set. The process returns nonzero
iff any set failed (`return 0 if all(success) else 1`) and prints a failed-set
summary. No code change was needed here; the isolation and exit contract are
covered by the batch-summary logic.

### Why simulations stopped producing runs after 2026-07-17 (diagnosis)

Two compounding causes, both now addressed:

1. **Scrape-queue stale-job exclusion (root, upstream).** A stale prior-day
   `running` `scrape_jobs` row satisfied the partial unique index
   `idx_scrape_jobs_one_active_per_set`, so the daily enqueue's
   `ON CONFLICT DO NOTHING` silently excluded that set from the next cohort
   (documented in migration `047`). Fresh Near Mint observations stopped landing
   for excluded sets, starving the simulation inputs. Fixed by migrations
   047–049 (lease-based, batch-aware queue: reconcile-first batch creation,
   crash-safe leases, cohort completeness, bounded requeue) — **implemented in
   repo, still pending application to production.**
2. **Unbounded full refresh (amplifier, downstream).** After any gap, *every*
   set is stale, so the old `refresh_stale_public_snapshots.py --commit` step
   rebuilt all 166 sets' coordinated snapshots in a single sequential pass →
   "high Disk I/O and Supabase statement timeouts," which failed the strict
   refresh step and left the scheduled task exiting nonzero. Addressed by the
   I/O-safe resumable recovery above (missing/stale/failed-only planning,
   bounded per-set retries) and the batch gate (does not attempt promotion for
   an incomplete cohort).

### Recovery / deployment procedure

1. Apply migrations `047`, `048`, `049` in the Supabase SQL editor (in order).
2. On the scraper VM, confirm the batch cron from `scraper_vm_operations.md` §8.
3. On the Windows sim host, run once manually to recover, watching I/O:
   ```bash
   ./.venv/Scripts/python.exe backend/scripts/run_all_v2_sets.py
   ./.venv/Scripts/python.exe backend/scripts/refresh_stale_public_snapshots.py --commit --strict
   ```
   The refresh now only rebuilds stale/failed sets, sequentially, with backoff,
   and preserves the previous good snapshots if the day's batch is incomplete.
4. Re-enable / confirm the "Run Simulation Jobs Daily" Task Scheduler task.

Do not run production simulations as part of code changes; the above is the
operator deployment step.
