# Collector V7 automatic refresh

Status: `COLLECTOR_V7_AUTOMATIC_REFRESH_READY`

Collector V7 remains `pokemon_collector_appeal_v7_expanded_price_blind_v1`; evidence refreshes create new append-only runs, not a new formula version. The frozen formula fingerprint is `06f5660047b9b8a4d7349d04b79547b1314c2be3720c245ba8780890db1c114b`.

## Execution graph

The existing daily opening-publication process calls `operationalize_historical_rip.py` as its final step. That command reads `plan_collector_appeal_refresh.freshness_plan`, using 7-day cadence for Pokemon, Trainer 12m, and Artist 12m and 31-day cadence for Trainer 5y and Artist 5y.

When all sources are fresh, it makes no provider call and only confirms/appends the idempotent daily history row when commit mode is enabled. When one or more sources are due, it refreshes exactly those sources through the existing Pokemon V2 anchor-ladder capture/ingest or accepted Trainer/Artist ingestion commands. Each resulting append-only run must pass the source health view plus source name, capture version, timeframe, fingerprint, observation-date, usability, and price-exclusion checks.

The V7 builder receives all six authorities explicitly: Pokemon Trends, Trainer 12m, Trainer 5y, playability, Artist 12m, and Artist 5y. It never selects latest evidence. The explicit IDs enter source lineage and the input fingerprint; the independent formula fingerprint must equal the frozen control or processing stops with `V7_FROZEN_FORMULA_DRIFT_BLOCKER`.

Before persistence, the orchestrator compares card and set scores, set ranks, availability, F deltas/membership, Artist coverage, and Trainer/Pokemon card coverage against current V7, rejecting set loss or a massive availability collapse. It then appends and validates the model run, stages and validates a complete Set-page generation, and calls `promote_pokemon_collector_v7_with_set_page_generation`. That service-role-only, security-definer RPC verifies generation/model affinity and performs the sanctioned Collector promotion and Set-page activation in one database transaction. Only after promotion does history append idempotently.

No Overall rankings publication is called. Overall remains insulated on `overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5`. No second scheduler was added.

## Failure and audit behavior

Refresh, validation, rebuild, persistence, generation, or promotion failure returns `COLLECTOR_SOURCE_REFRESH_BLOCKED`, retains the current public authority, and does not append a READY history observation. Source captures completed before a later failure remain immutable evidence and are reported as `sourceRunsCreated`; they are never overwritten. Dry-run reports due sources and planned provider-call groups but performs zero mutations and zero provider requests.

The JSON report contains the date, stale sources, old/new source and model IDs, validation and delta reports, Set-page generation, planned provider groups, history result, mutations, and error state. Credentials are never logged.

## Readiness locks and backlog

Forward V7 collection is ready. Historical Quality remains `HISTORICAL_QUALITY_RESEARCH_NOT_READY`; the 7/30/60/90 observation gates are unchanged. Chase reconstruction remains blocked because historical probability authority is not date-bound and historical desirability/selection lineage is absent.
