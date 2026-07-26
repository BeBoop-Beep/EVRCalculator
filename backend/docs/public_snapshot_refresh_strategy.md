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

`refresh_stale_public_snapshots.py` consults
`backend/db/services/publication_gate.evaluate_publication_gate` before it
promotes anything in `--commit` mode:

- **Batch `complete`** → gate open, promote as normal.
- **Batch pending/running/incomplete/failed** → gate closed. The run prints
  `publication gate CLOSED`, promotes nothing, and **preserves the previous good
  public snapshots**. This is a success (exit 0), not a failure — the day simply
  is not ready to promote yet. Missing sets are requeued by the scrape pipeline
  (`requeue_missing_scrape_jobs_for_batch`, migration 049), not by this refresh.
- **No batch row / batch tables not applied** → gate is *ungated* (open) so
  environments without the batch system (local/dev, or prod before 047–049 is
  applied) keep working unchanged.

Flags:

```powershell
# Gate on a specific America/Phoenix market date's batch.
python backend/scripts/refresh_stale_public_snapshots.py --commit --market-date 2026-07-25

# Manual recovery ONLY: promote even if the cohort is incomplete (loudly logged).
python backend/scripts/refresh_stale_public_snapshots.py --commit --force-publish
```

`--force-publish` is never part of the normal schedule.

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
- A closed publication gate is not a failure (exit 0).

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
