# Pokémon market-date recovery runbook

This procedure is for an explicit date whose raw provider scrape must be run or
has already completed. It never bypasses registry parity, batch completeness,
Cards reconciliation, Market Quality, or the existing publication gate.

## Phase 1 — verify the deployed checkout

```bash
cd /home/ubuntu/repos/EVRCalculator
git branch --show-current
git rev-parse HEAD
git status --short
set -a; . backend/.env; set +a
python backend/scripts/create_daily_scrape_batch.py --market-date 2026-08-29 --preflight-only
```

The preflight must report `ok: true`, matching local/database cohort counts and
hashes. Stop on any mismatch.

## Phase 2 — repair the stale Aug. 28 canonical history

Preview, then commit through the canonical database refresh function:

```bash
python backend/scripts/repair_pokemon_set_value_history.py --start-date 2026-08-28 --end-date 2026-08-28 --all
python backend/scripts/repair_pokemon_set_value_history.py --start-date 2026-08-28 --end-date 2026-08-28 --all --commit
python backend/scripts/audit_pokemon_cards_market_reconciliation.py
```

Required result: reconciliation `failure_count` is zero. Stop otherwise.

## Phase 3 — acquire and recover Aug. 29

```bash
python backend/scripts/create_daily_scrape_batch.py --market-date 2026-08-29 --trigger-source manual --skip-new-set-detection
python backend/scripts/run_next_scrape_job.py --market-date 2026-08-29
python backend/scripts/recover_pokemon_market_date.py --market-date 2026-08-29 --commit
python backend/scripts/audit_pokemon_market_publication.py --market-date 2026-08-29 --phase post-scrape --json
```

The recovery command refuses a missing/incomplete batch. It refreshes canonical
Set Value, reconciles Cards, invokes the coordinated snapshot refresh (which
owns sealed, set dashboards, Market Quality, global index and Explore ordering),
then runs the canonical publication audit.

## Phase 4 — acquire and recover Aug. 30

Run only after every Aug. 29 command succeeds:

```bash
python backend/scripts/create_daily_scrape_batch.py --market-date 2026-08-30 --trigger-source manual --skip-new-set-detection
python backend/scripts/run_next_scrape_job.py --market-date 2026-08-30
python backend/scripts/recover_pokemon_market_date.py --market-date 2026-08-30 --commit
python backend/scripts/audit_pokemon_market_publication.py --market-date 2026-08-30 --phase post-scrape --json
```

If both raw batches are already complete, chronological downstream recovery may
instead be invoked as one fail-fast command. It still processes one date fully
before starting the next and uses no cross-date transaction:

```bash
python backend/scripts/recover_pokemon_market_date.py --start-date 2026-08-29 --end-date 2026-08-30 --commit
```

## Phase 5 — read-only verification

```bash
python backend/scripts/audit_pokemon_cards_market_reconciliation.py
python backend/scripts/audit_pokemon_market_publication.py --market-date 2026-08-30 --phase post-scrape --json
python -m backend.alerts.dispatcher --health
python -m backend.alerts.market_freshness_watchdog --health
```

Optional SQL inspection (read-only):

```sql
SELECT market_date,status,expected_set_count,succeeded_set_count,missing_set_count,promoted_at
FROM public.pokemon_scrape_batches ORDER BY market_date DESC LIMIT 5;

SELECT market_date,status FROM public.pokemon_market_date_quality
ORDER BY market_date DESC LIMIT 5;

SELECT max(captured_at) AS latest_card_observation
FROM public.card_variant_price_observations;

SELECT max(snapshot_date) AS latest_set_value
FROM public.pokemon_set_value_daily_history WHERE value_scope='standard';

SELECT max(market_date) AS latest_set_dashboard
FROM public.pokemon_set_market_dashboard_snapshot_latest;

SELECT max(market_date) AS latest_sealed
FROM public.pokemon_set_sealed_market_snapshot_latest;

SELECT max(market_date) AS latest_global_set_value
FROM public.pokemon_explore_set_value_snapshot_latest;

SELECT index_key,max(market_date) AS latest_index
FROM public.pokemon_market_index_daily_history
WHERE tcg='pokemon' GROUP BY index_key ORDER BY index_key;

SELECT sent,count(*) FROM public.alert_events
WHERE suppressed_at IS NULL GROUP BY sent ORDER BY sent;
```

For Prismatic, the publication audit and Cards reconciliation must show the
standard `$5,036.02` basket for 2026-08-28 and no `$2.40` Holiday Calendar promo
leak. Never edit the aggregate or snapshot dates manually.
