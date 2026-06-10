# Pokemon Desirability Ingestion

This pipeline captures source data for a future Collector Demand / Pokemon Desirability Score. It stores source snapshots and normalized source scores only. It does not feed RIP Score, Opening Experience, Explore, Set pages, or simulations.

## Sources

`PokeAPI` is the canonical Pokemon reference source for National Pokedex number, canonical name, display name, generation, API URL, and sprite URL.

`favoritepokemon.vercel.app` is treated as a public community-favorite signal. The scraper only reads public rendered pages at:

- `https://favoritepokemon.vercel.app/#/pokedex`
- `https://favoritepokemon.vercel.app/#/stats`

It does not authenticate, submit forms, create votes, call private Supabase tables, or depend on undocumented database access.

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

## Outputs

The migration adds:

- `pokemon_reference`
- `pokemon_desirability_source_snapshots`
- `pokemon_desirability_source_rows`
- `pokemon_desirability_scores`

Dry-run mode prints a JSON report and writes local diagnostics under `tmp/pokemon_desirability` when screenshots are enabled. Commit mode creates an immutable raw snapshot first, then source rows, then normalized scores when enough source data exists.

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
