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

## Refresh Order

The dependency order is:

1. Set cards snapshots
2. Market dashboard snapshots
3. Explore rankings snapshot
4. Set page snapshots
5. Desirability validation snapshot

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
