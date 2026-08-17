# Simulation persistence reliability

How the unattended set-simulation batch behaves when Supabase is temporarily
unreachable, and why a retry here cannot corrupt a run.

## The failure this addresses

An unattended `prismaticEvolutions` run died ~1.8s after it started:

```
Simulation input-card insert (card:10ac8163-…) failed for table 'simulation_input_cards'
APIError: {'message': 'JSON could not be generated', 'code': 502,
           'details': '<html>… 502 Bad Gateway … cloudflare …'}
```

That is a Cloudflare/PostgREST edge failure, not a data fault: the payload was
valid and the same request succeeds seconds later. Before this change, the
single `.execute()` in `_insert_required_payload` had no retry, so the first
blip failed the set — and every following set walked into the same outage.

## Layer 1 — per-operation retry

`backend/db/services/supabase_persistence_retry.py` provides
`run_with_transient_retry`: 5 attempts, 1s/2s/4s/8s backoff with 10% jitter, no
sleep after the final attempt. Classification is delegated to
`backend/db/services/data_service_health.py`.

Retryable: HTTP 429/500/502/503/504/520/521/522, PostgREST `PGRST002`, Postgres
`57014`, httpx/httpcore timeout and network errors, `ConnectionError`,
`TimeoutError`, and a narrow set of transport phrases (`connection reset`,
`read timeout`, `connect timeout`, `gateway timeout`, …).

**Never retryable**, regardless of the HTTP status attached at the edge: any
exception in the chain carrying a real SQLSTATE (`23505`, `23503`, `22P02`,
`42703`, `42501`, …) or a `PGRST1xx`/`PGRST2xx` code. The database understood
the request and rejected it; repeating it repeats the rejection. Application
validation (`ValueError` from the `_require_*` helpers) never reaches the
database at all.

## Layer 2 — idempotency

A network failure can arrive **after** Postgres committed. Retrying an `INSERT`
blindly would therefore duplicate rows. `_insert_required_payload` takes an
`identity_columns` argument: on attempt ≥ 2 it reads the row back by that
identity first and returns it if the previous attempt actually landed.

| Table | Identity | Basis |
|---|---|---|
| `calculation_configs` | `config_hash` | UNIQUE |
| `calculation_runs` | `id` | client-generated UUID (see below) |
| `calculation_price_snapshots` | run + `price_type` + `price_source` | natural |
| `simulation_run_summary` | `calculation_run_id` | UNIQUE |
| `simulation_derived_metrics` | `calculation_run_id` | UNIQUE |
| `simulation_etb_summary` | `calculation_run_id` | UNIQUE |
| `simulation_percentiles` | run + `percentile` | natural |
| `simulation_pull_summary` | run + `rarity_bucket` | natural |
| `simulation_state_counts` | run + `state_group` + `state_name` | natural |
| `simulation_value_distribution_bins` | run + floor + ceiling | UNIQUE |
| `simulation_value_threshold_bins` | run + floor + ceiling | UNIQUE (NULL ceiling → `IS NULL`) |
| `simulation_input_cards` | run + `card_id` + `card_variant_id` + `condition_id` | natural (no DB constraint) |
| `simulation_sealed_product_results` | already an UPSERT on (run, product) | UNIQUE |
| `simulation_pack_outcome_artifacts` | `calculation_run_id` is the PRIMARY KEY | select-then-insert is retried whole |

A table with **no** identity is not retried at all: it cannot distinguish "the
insert never landed" from "the response was lost", so fail-fast is correct.

`calculation_runs.id` is now chosen client-side rather than by
`gen_random_uuid()`. Without an id in the payload, a lost response would have
created a second parent run for the same simulation.

No uniqueness constraint was added, removed or weakened.
`simulation_input_cards` has none; its identity is the one the data already
obeys (zero duplicate `(run, card, variant, condition)` groups exist in the
table).

## The exact pack-outcome artifact

Unchanged in contract. `persist_pack_outcomes` is retried as a whole
select-then-insert, so a retried attempt re-reads first and verifies the
existing row's `raw_sha256` and `outcome_count` against the vector in hand
(returning `matched`). A checksum mismatch raises `PackOutcomeArtifactCorrupt`,
which is deterministic and never retried. If retries are exhausted the exception
propagates and the run fails. **There is no histogram-replay fallback and this
change does not create one.**

## Partial runs

Persistence order is: parent run → price snapshots → input cards → artifact →
run summary → percentiles → pull summary → state counts → derived metrics →
bins → ETB → sealed products. There is no wrapping transaction, so a mid-way
failure leaves a `calculation_runs` row with some children and not others.

**An incomplete run cannot become canonical or public.** The read path that
feeds every downstream consumer is `simulation_latest_by_target__base`:

```sql
FROM calculation_runs cr
  JOIN simulation_run_summary srs ON srs.calculation_run_id = cr.id
  JOIN simulation_derived_metrics sdm ON sdm.calculation_run_id = cr.id
… row_number() OVER (PARTITION BY cr.target_type, cr.target_id ORDER BY cr.created_at DESC) … WHERE rn = 1
```

Both joins are INNER and the `row_number()` is computed **after** them, so a run
missing its summary or derived metrics is not merely deprioritised — it is
invisible, and the previous complete run remains "latest". A run that dies
during input-card persistence has neither child row.

Downstream of that, `publish_pokemon_public_rip_leaderboard` (migration 067)
additionally requires a ready, rankable Financial RIP V3 per target and rejects
the whole publication if the cohort is incomplete. A partial run therefore
either changes nothing or fails the publication loudly. Failed runs are left in
place; no cleanup behaviour is introduced here.

## Queue behaviour

`backend/scripts/run_all_v2_sets.py` runs sets sequentially, catching per-set
exceptions and continuing. It has no circuit breaker. It now classifies each set
failure and, after **consecutive transient** failures, sleeps 30s / 60s / 120s
before starting the next set. One success — or any deterministic failure —
resets the ladder, so a set failing for its own reasons never slows the queue.
The batch still attempts every set; nothing is skipped or abandoned.
