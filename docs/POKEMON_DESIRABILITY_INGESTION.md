# Pokemon Desirability Ingestion

This pipeline captures source data for a future Collector Demand / Pokemon Desirability Score. It stores source snapshots and normalized source scores only. It does not feed RIP Score, Opening Experience, Explore, Set pages, or simulations.

## Sources

`PokeAPI` is the canonical Pokemon reference source for National Pokedex number, canonical name, display name, generation, API URL, and sprite URL.

`favoritepokemon.vercel.app` is treated as a public community-favorite signal. The scraper only reads public rendered pages at:

- `https://favoritepokemon.vercel.app/#/pokedex`
- `https://favoritepokemon.vercel.app/#/stats`

It does not authenticate, submit forms, create votes, call private Supabase tables, or depend on undocumented database access.

`Google Trends` is treated as a relative search-interest signal for canonical Pokemon names. It does not measure direct fandom, card demand, total searches, or absolute search volume. Google Trends values are relative within query groups, so this pipeline queries batches anchored by `Pikachu` and normalizes Pokemon terms against that anchor before comparing them across batches.

The Trends source is split into separate concepts:

- `Search Popularity Score`: current/long-term relative search interest from `today 12-m` and/or `today 5-y`.
- `Recent Trend Score`: recent relative search interest from `today 1-m`; this is a component used for diagnostics and momentum.
- `Trend Momentum Score`: recent relative search interest compared with the longer-term baseline.

The script queries Pokemon names only. It does not query individual card names.

## Setup

Install backend dependencies and Playwright's Chromium browser:

```bash
pip install -r backend/requirements.txt
python -m playwright install chromium
```

Commit mode requires `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in `backend/.env`.

Apply the migration:

```bash
backend/db/migrations/023_add_pokemon_desirability_ingestion_tables.sql
backend/db/migrations/024_add_pokemon_google_trends_ingestion_tables.sql
```

## Commands

Dry-run PokeAPI canonical reference ingestion:

```bash
python backend/scripts/ingest_pokemon_desirability.py --source pokeapi --dry-run
```

Commit PokeAPI canonical references:

```bash
python backend/scripts/ingest_pokemon_desirability.py --source pokeapi --commit
```

Dry-run the public rendered favoritepokemon scrape:

```bash
python backend/scripts/ingest_pokemon_desirability.py --source favoritepokemon --dry-run
```

Run the full monthly/on-demand snapshot:

```bash
python backend/scripts/ingest_pokemon_desirability.py --all --commit
```

Dry-run a reference matching backfill for an existing snapshot:

```bash
python backend/scripts/ingest_pokemon_desirability.py --backfill-snapshot-id 1 --dry-run
```

Commit the backfill after the dry-run shows the expected match coverage:

```bash
python backend/scripts/ingest_pokemon_desirability.py --backfill-snapshot-id 1 --commit
```

Dry-run Google Trends relative search-interest ingestion with the default windows:

```bash
python backend/scripts/ingest_pokemon_trends.py --limit 25 --dry-run
```

Dry-run a single Google Trends window:

```bash
python backend/scripts/ingest_pokemon_trends.py --geo US --timeframe today 12-m --limit 25 --dry-run
```

Use deterministic fixture data to validate the ingestion flow without live Google Trends access:

```bash
python backend/scripts/ingest_pokemon_trends.py --provider fixture --limit 25 --dry-run
```

Commit a Google Trends snapshot after the dry-run diagnostics look healthy:

```bash
python backend/scripts/ingest_pokemon_trends.py --provider pytrends --timeframe today 12-m --pokedex-start 1 --pokedex-end 151 --commit --delay-seconds 60 --max-retries 1 --retry-backoff-seconds 300
```

Production Google Trends jobs should use one timeframe and a small Pokemon range. A full 1025-Pokemon multi-timeframe live run is not recommended because Google Trends/pytrends can return `429 TooManyRequestsError`.

Range controls:

```bash
python backend/scripts/ingest_pokemon_trends.py --provider pytrends --timeframe today 12-m --offset 0 --limit 25 --dry-run
python backend/scripts/ingest_pokemon_trends.py --provider pytrends --timeframe today 12-m --pokedex-start 152 --pokedex-end 251 --dry-run
```

Retry/fill missing rows into an existing Google Trends snapshot without rerunning the full source:

```bash
python backend/scripts/ingest_pokemon_trends.py --provider pytrends --append-to-snapshot-id 1 --timeframe today 1-m --pokedex-start 382 --pokedex-end 385 --dry-run --delay-seconds 60 --max-retries 1 --retry-backoff-seconds 300
python backend/scripts/ingest_pokemon_trends.py --provider pytrends --append-to-snapshot-id 1 --timeframe today 1-m --pokedex-start 382 --pokedex-end 385 --commit --delay-seconds 60 --max-retries 1 --retry-backoff-seconds 300
```

Append mode loads existing `pokemon_trend_source_rows` for the snapshot, skips Pokemon already present, inserts only missing rows into the same `snapshot_id`, and updates snapshot status to `captured_relative_search_interest` when all 1025 Pokemon are present or `captured_partial` otherwise.

After required source snapshots exist for `today 1-m`, `today 12-m`, and `today 5-y`, derive final trend scores from existing rows:

```bash
python backend/scripts/ingest_pokemon_trends.py --provider pytrends --derive-from-existing --dry-run
python backend/scripts/ingest_pokemon_trends.py --provider pytrends --derive-from-existing --commit
```

Derive mode selects the latest usable snapshots by source/provider/geo/timeframe, normalizes existing source rows by timeframe, calculates `search_popularity_score`, `recent_trend_score`, and `trend_momentum_score`, skips duplicate derived rows with the same scoring version and contributing snapshot IDs, then inserts missing rows into `pokemon_trend_scores`.

## Outputs

The migration adds:

- `pokemon_reference`
- `pokemon_desirability_source_snapshots`
- `pokemon_desirability_source_rows`
- `pokemon_desirability_scores`
- `pokemon_trend_source_snapshots`
- `pokemon_trend_source_rows`
- `pokemon_trend_scores`

Dry-run mode prints a JSON report and writes local diagnostics under `tmp/pokemon_desirability` when screenshots are enabled. Commit mode creates an immutable raw snapshot first, then source rows, then normalized scores when enough source data exists.

Google Trends dry-run mode prints diagnostics only. Commit mode stores each timeframe as its own `pokemon_trend_source_snapshots` row and stores each Pokemon's anchor-normalized relative search interest in `pokemon_trend_source_rows`. Derived scores are stored in `pokemon_trend_scores` with explicit `score_name` values: `search_popularity_score`, `recent_trend_score`, and `trend_momentum_score`.

Append/fill mode diagnostics include existing rows skipped, missing rows attempted, inserted rows, failed batches, rate-limited batches, final snapshot row count, and a missing Pokemon sample.

## Normalization

The scoring version is `pokemon_desirability_source_v1`.

When vote counts are visible:

```text
normalized_score = 100 * log(1 + vote_count) / log(1 + max_vote_count)
```

When only ranks are visible:

```text
normalized_score = 100 * (1 - ((rank - 1) / (total_ranked - 1)))
```

When only tier/status text is visible, the script maps recognizable tier/status values to broad score bands and marks confidence as low. If no usable aggregate data is visible, the snapshot is marked `insufficient_data` and no normalized scores are created.

Tiers:

- `S`: 90-100
- `A`: 75-89
- `B`: 55-74
- `C`: 35-54
- `D`: 15-34
- `F`: 0-14

## Caveats

favoritepokemon.vercel.app is a community signal, not official market truth. Use it as one input to future demand modeling, not as a standalone valuation source.

If the public rendered pages stop exposing aggregate data, the scraper records page title, loaded URL, visible text sample, detected table/card/list candidates, optional screenshots, and a clear `insufficient_data` status.

Google Trends caveats:

- Google Trends values are normalized relative search interest, not total searches.
- Scores become cross-Pokemon comparable only after anchor-based batching and normalization.
- `today 1-m`, `today 3-m`, `today 12-m`, and `today 5-y` are normalized separately before derived scores are calculated.
- Ambiguous search terms such as `Persian`, `Onix`, `Golem`, `Ditto`, `Muk`, `Abra`, `Haunter`, `Jynx`, `Type: Null`, `Mr. Mime`, and `Porygon-Z` are flagged as likely noisy in diagnostics.
- The official Google Trends API is preferred when stable access is available. The current provider layer is built so the implementation can be swapped without changing downstream modeling.
- Provider failures and rate limits are reported as graceful diagnostics and should not block the rest of the app.
- If repeated 429/rate-limit responses occur, the script stops the current run with `rate_limited_gracefully` instead of continuing through all remaining batches.

## Monthly Schedule

Recommended monthly staging:

- Run PokeAPI reference ingestion monthly or when the canonical Pokemon list changes.
- Run favoritepokemon monthly as one community-favorite snapshot.
- Run Google Trends as smaller pytrends jobs split by National Pokedex range.
- Prefer one Google Trends timeframe per job, with conservative delays.

Example staged Google Trends jobs:

```bash
python backend/scripts/ingest_pokemon_trends.py --provider pytrends --timeframe today 12-m --pokedex-start 1 --pokedex-end 151 --commit --delay-seconds 60 --max-retries 1 --retry-backoff-seconds 300
python backend/scripts/ingest_pokemon_trends.py --provider pytrends --timeframe today 5-y --pokedex-start 1 --pokedex-end 151 --commit --delay-seconds 60 --max-retries 1 --retry-backoff-seconds 300
python backend/scripts/ingest_pokemon_trends.py --provider pytrends --timeframe today 1-m --pokedex-start 1 --pokedex-end 151 --commit --delay-seconds 60 --max-retries 1 --retry-backoff-seconds 300
```
