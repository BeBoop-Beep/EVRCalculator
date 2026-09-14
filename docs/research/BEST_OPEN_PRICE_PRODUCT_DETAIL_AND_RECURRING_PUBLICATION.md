# Best-Open Price — Product Detail + Recurring Publication

## Decision

Best-Open Price is now a prepared product feature, not a one-off research artifact.

Two production requirements are coupled but remain conceptually separate:

1. Product Detail may show a Best-Open threshold while its live sealed-market price is newer than the threshold source. It must therefore display both authorities explicitly and never silently re-score the threshold against the newer price.
2. A new published Full Market Budget Ranking must cause a fresh Best-Open prepared snapshot to be built automatically by the existing daily Windows Task Scheduler chain.

## Product Detail contract

The private store remains service-role only. `load_best_open_price_product()` performs a bounded single-product read after verifying that the latest Best-Open snapshot is still bound to the exact current Budget Ranking snapshot (`id`, `published_at`, `market_date`, cohort fingerprint).

The paid Product Detail payload exposes only:

- threshold price/status/gap,
- threshold quantity,
- ranking-source unit price and rank,
- source Full Market budget/cohort size,
- source market date / snapshot identity / method version.

It does not expose raw benchmark rows or source-component evidence.

The frontend renders a separate **Best-Open Price · Full Market** card. It shows:

- Best-Open threshold,
- ranking-source price/date,
- current tracked price/date,
- published Full Market rank.

If the current tracked price is newer, the UI may say it is `$X above/below` the published threshold. That is explicitly a price comparison only. The threshold remains bound to its dated Full Market cohort until the next prepared publication completes.

Stale/missing/incomplete prepared data is shown as refreshing/unavailable; an old threshold is never served as current.

## Recurring publication contract

No second scheduler is introduced.

The existing Windows task runs:

`infra/local/run_simulations_task.bat`

which first runs the canonical daily publication wrapper:

`infra/local/run_simulations.sh`

Only after that exits `0` does the same task invoke:

`infra/local/run_best_open_price.sh`

which runs:

`python -m backend.scripts.publish_best_open_price_if_ready --commit --quantity-batch-size 24`

The task propagates a Best-Open failure as its final nonzero exit code.

## Exact-engine reuse

`research_best_open_price_bucket2.run()` remains the one exact search implementation. Its historical defaults remain pinned to the Sep-8 research authority, but the recurring wrapper supplies:

- the current published Budget Ranking snapshot ID,
- the authority fingerprint reconstructed from that snapshot's persisted Full Market rows,
- validated bitwise-exact quantity batch width `24`,
- `run_determinism=False` for recurring execution (the expensive deterministic replay was a research validation gate; each daily row still performs the exact P*/P*+1¢ check).

The current source cohort fingerprint is independently reconstructed from the exact simulation product/run/price identities and must equal the published Budget Ranking snapshot fingerprint before search begins.

## Publication gates

The recurring wrapper publishes only when all of the following are true:

- current Budget Ranking is V12-authoritative;
- no complete Best-Open snapshot already exists for the exact source authority;
- engine artifact is complete;
- attempted/resolved count equals the eligible Full Market cohort;
- unresolved count is zero;
- every row has an engine-supported resolved status;
- every row has a threshold price and threshold quantity;
- every row reports `thresholdWins=true`;
- every row reports `oneCentMaximal=true` and `nextPriceWins != true`;
- every persisted current/benchmark source-evidence field is present;
- source identity is unchanged after the long computation.

The final publish still uses `publish_budget_product_best_open_price_snapshot`, whose transaction revalidates the live source and row evidence and moves the latest pointer only after all checks pass.

After commit, the wrapper reads the prepared authority back and requires the returned snapshot/source/counts to match before reporting `PUBLISHED`.

## Runtime / operations

- source-specific checkpoints live under `logs/best_open_price_checkpoints/`;
- each checkpoint filename includes a short digest of `snapshot_id + published_at + market_date + cohort_fingerprint`, so a legal same-ID source replacement can never resume an older publication's partial work;
- report: `logs/best_open_price_publication.json`;
- log: `logs/best_open_price_publication.log`;
- the long-run singleton lock is an OS byte lock stored at `tempfile.gettempdir()/budget_product_best_open_price_daily.lock`;
- Windows uses `msvcrt.locking`; POSIX uses `fcntl.flock`; process death releases the lock automatically even if the lock file itself remains;
- `ALREADY_CURRENT` is a successful quiet no-op;
- failures send their own Slack alert and propagate a nonzero task exit;
- Slack delivery failure never changes DB publication success/failure.

## Explicit non-goals

- no request-time threshold search;
- no frontend recomputation of ranking scores or thresholds;
- no second cron/Task Scheduler entry;
- no change to the canonical Budget Ranking method or comparator;
- no stale fallback when the Budget Ranking source advances.
