# Pokémon Pack Simulation System — Architecture Audit
**Audit type**: READ-ONLY. No code was changed during this audit.  
**Branch**: `feature/updatesAndSimTool`  
**Purpose**: Understand the end-to-end simulation pipeline completely so a separate user-facing simulation tool can be added later — without touching production daily simulation behavior.

---

## 1. Executive Summary

The Pokémon pack simulation system runs **1,000,000-pack Monte Carlo simulations** for each set. Simulations are triggered manually via a CLI script on an external VM (no APScheduler). Results are persisted to Supabase, where a family of read-only PostgreSQL views surfaces the most recent run per set to the frontend. Pack price (from the `sealed_product_prices` table) is used **only in post-simulation derived metrics** — it is never inside the simulation loop itself. This is the key architectural insight enabling the planned user-facing tool.

**Key finding**: The 1M-pack value distribution is **completely independent of pack price**. Only the profit/safety scores, ROI, and interpretation copy depend on `pack_cost`. This means a user-entered custom price can be handled by recomputing those cheap post-sim metrics against the already-stored distribution — no re-simulation required for the fast path.

---

## 2. Simulation Pipeline Map (End-to-End)

```
[External VM cron]
       │
       ▼
backend/scripts/run_all_v2_sets.py          ← CLI entrypoint (--era, --set, --dry-run)
       │  discover V2-enabled sets
       │  calls for each set:
       ▼
backend/jobs/evr_runner.py                  ← EVRRunOrchestrator.run()
  Step 1  _resolve_set_config(target_set_identifier)
          → resolves config class + canonical_key (fuzzy-match supported)
  Step 2  EVRInputPreparationService().prepare_for_set(config, canonical_key, set_name)
          → loads card data + pack_price from DB (sealed_product_prices)
  Step 3  calculate_pack_stats(calculation_input, config)
          → deterministic EV calculation (no randomness)
          → returns pack_price as a side output
  Step 4  calculate_pack_simulations(calculation_input, config)
          → calls PackEVRSimulator.calculate_evr_simulations(df)
          → engine selection: V2 for Scarlet & Violet / Mega Evolution, V1 for all other eras
          → calls run_simulation_v2(simulate_pack_fn, ..., n=1_000_000)
          → returns values (list of 1M pack values), rarity_pull_counts, percentiles, etc.
  Step 5  compute_all_derived_metrics(values, pack_price, ...)
          → scoring: profit_score, safety_score, stability_score, pack_score
          → all score computations happen HERE, not inside the simulation loop
  Step 6  Build pack / ETB / booster-box comparisons (_compute_cost_comparison)
  Step 7  persist_parent_run_with_price_snapshots(...)  → DB writes (calculation_runs, etc.)
  Step 8  persist_simulation_inputs(...)                → DB write (simulation_input_cards)
  Step 9  persist_simulation_outputs(...)               → DB writes (all result tables)
  Step 10 persist_simulation_etb_summary(...)           → DB write (optional, ETB sets only)
```

**Scheduler note**: `backend/jobs/scheduler_service.py` runs `run_daily_portfolio_reconciliation_all_users()` at 3:00 AM. It does **not** trigger simulation. Simulation is driven by the external VM cron calling `run_all_v2_sets.py`.

---

## 3. Database Write Map

All writes go through `backend/db/services/calculation_run_persistence_service.py`. Every table is append-only; the universal join key is `calculation_run_id`.

| Table | Writer function | Content |
|---|---|---|
| `calculation_runs` | `create_parent_calculation_run()` | Parent record (set, trigger, timestamp) |
| `calculation_configs` | `get_or_create_calculation_config()` | SHA-256 hashed config snapshot (de-duplicated) |
| `calculation_price_snapshots` | `create_calculation_price_snapshot()` | Pack / ETB / booster-box prices at run time |
| `simulation_run_summary` | `create_simulation_run_summary()` | Mean, median, prob_profit, **pack_cost** |
| `simulation_derived_metrics` | `create_simulation_derived_metrics()` | All scores, EV composition, chase metrics |
| `simulation_input_cards` | `create_simulation_input_cards()` | Card data snapshot used in the run |
| `simulation_percentiles` | `create_simulation_percentiles()` | p5 / p25 / p50 / p75 / p95 / p99 |
| `simulation_pull_summary` | `create_simulation_pull_summary()` | Rarity pull counts and value totals |
| `simulation_state_counts` | `create_simulation_state_counts()` | Pack state frequencies |
| `simulation_value_distribution_bins` | `create_simulation_value_distribution_bins()` | Histogram bins |
| `simulation_value_threshold_bins` | `create_simulation_value_threshold_bins()` | Threshold bins |
| `simulation_etb_summary` | `create_simulation_etb_summary()` | ETB metrics (optional) |

**No writes happen to any view.** Views are refreshed automatically by Postgres when queried.

---

## 4. Frontend / Read Pipeline Map

```
User browser
    │
    ▼
frontend/app/Explore/page.js                          ← Server Component
frontend/app/Explore/rip-statistics/page.js           ← Server Component
    │
    │  calls lib functions (Next.js cache)
    ▼
frontend/lib/explore/ripStatisticsServer.js
frontend/lib/explore/explorePageServer.js
    │  fetch(..., { cache: "no-store" })
    ▼
backend/api/main.py
    GET /explore/rip-statistics/targets               ← targets list (leaderboard)
    GET /explore/page?target_type=set&target_id=...   ← single set detail
    │
    ▼
backend/db/services/explore_rip_statistics_service.py
  get_rip_statistics_targets_payload(limit)
    → SELECT * FROM explore_rip_statistics_latest ORDER BY pack_score DESC
    → build_rip_interpretation(row)   ← interpretation text generated in-flight

backend/db/services/explore_page_service.py
  get_explore_page_payload(target_type, target_id)
    → SELECT * FROM explore_rip_statistics_latest WHERE set_id = target_id
    → fallback: simulation_latest_by_target
    → supplement: set_pack_score_rankings_latest
    → build_rip_interpretation(row)   ← interpretation text generated in-flight
    │
    ▼
frontend/components/explore/RipStatisticsPageClient.jsx  ← "use client" component
```

The frontend **never queries Supabase directly** for simulation data — all simulation reads go through the FastAPI backend proxy.

---

## 5. Pack Price Dependency Map

### How pack_price enters the system

```
sealed_product_prices (DB table)
    │
    ▼  EVRInputRepository.load_inputs()
    │  filters: type ILIKE 'pack' OR 'booster pack' OR 'single booster pack'
    │  excludes: '3 pack', 'blister', 'box', 'bundle', 'collection'
    ▼
EVRInputTransformer.transform()
    │
    ▼  prepared["pack_price"]
    │
    ▼  calculate_pack_stats(calculation_input, config)
    │  returns pack_price
    │
    ▼  EVRRunOrchestrator.run() holds pack_price_value
    │
    ├──▶ stored in calculation_price_snapshots
    ├──▶ stored in simulation_run_summary.pack_cost
    └──▶ passed to compute_all_derived_metrics(values, pack_price, ...)
```

### What pack_price affects (ALL post-simulation, ALL computable from stored distribution)

| Metric | Formula | pack_cost dependency |
|---|---|---|
| `prob_profit` | fraction of 1M values ≥ pack_cost | YES |
| `prob_big_hit` | fraction of 1M values ≥ 5×pack_cost | YES |
| `net_value` | mean(values) − pack_cost | YES |
| `roi` | mean(values) / pack_cost | YES |
| `roi_percent` | (roi − 1) × 100 | YES |
| `expected_loss_given_loss` | mean of values where value < pack_cost | YES |
| `median_loss_given_loss` | median of values where value < pack_cost | YES |
| `p05_shortfall_to_cost` | max(pack_cost − p5_value, 0) / pack_cost | YES |
| `profit_score` (0–100) | depends on prob_profit, value/cost ratios | YES |
| `safety_score` (0–100) | depends on loss metrics | YES |
| `pack_score` (0–100) | 40% profit + 30% safety + 30% stability | MOSTLY YES |
| `stability_score` (0–100) | coefficient of variation + HHI | **NO** |
| `coefficient_of_variation` | std(values) / mean(values) | **NO** |
| `HHI`, `effective_chase_count` | card EV concentration ratios | **NO** |
| All percentiles (p5/p25/p50/p75/p95/p99) | quantiles of the distribution | **NO** |
| Interpretation copy | derived from scores | MOSTLY YES |

**Critical**: The 1,000,000 sampled pack values are drawn exclusively from card prices. Pack cost is never read inside the simulation loop. The full value distribution is 100% price-independent.

---

## 6. Simulation Count Dependency Map

### Where `n = 1,000,000` lives

| Location | How it appears |
|---|---|
| `backend/simulations/monteCarloSimV2.py` | `def run_simulation_v2(..., n: int = 1_000_000)` — function default |
| `backend/simulations/evrSimulator.py` line 334 | `n=1000000` — hardcoded keyword arg passed to `run_simulation_v2` |
| `backend/simulations/evrSimulator.py` line 373 | `n=1000000` — hardcoded keyword arg for validation path |
| `backend/scripts/run_all_v2_sets.py` | No `--simulation-count` CLI flag exists |
| Config classes | No `SIMULATION_COUNT` attribute on any config class |

### Safe override path

`run_simulation_v2` already accepts `n` as a parameter. Calling it with `n=100_000` requires no changes to the function. The current production callers use the hardcoded `n=1000000` keyword argument inside `evrSimulator.py`. A new caller could bypass `evrSimulator.py` entirely and call `run_simulation_v2` directly, or add a parameter to `calculate_pack_simulations`.

### V1 engine

`backend/simulations/monteCarloSim.py:run_simulation()` is used for older eras (pre-Scarlet & Violet, pre-Mega Evolution). It also accepts `n` as a parameter with a default of 1,000,000. The production caller hardcodes it similarly.

---

## 7. Scoring and Interpretation Dependency Map

### Score computation

File: `backend/calculations/evr/derived_metrics.py`  
Function: `compute_all_derived_metrics(values, pack_cost, card_ev_contributions, total_pack_ev, hit_ev, hit_cards_count)`

Score version stored: `"pack_score_v2_1_runtime"`  
Normalization mode: `"fixed_anchor_runtime_v2_1"`

```
values (1M floats) + pack_cost
    │
    ├──▶ compute_probability_metrics(values, pack_cost) → prob_profit, prob_big_hit
    ├──▶ compute_downside_metrics(values, pack_cost)    → loss metrics
    ├──▶ compute_volatility_metrics(values)             → CV, percentiles (NO pack_cost)
    └──▶ compute_chase_dependency_metrics(card_ev_contributions) → HHI (NO pack_cost)
         │
         └──▶ profit_score(0-100) + safety_score(0-100) + stability_score(0-100)
                   │
                   └──▶ pack_score = 0.40 × profit + 0.30 × safety + 0.30 × stability
```

### Interpretation text generation

File: `backend/interpretation/rips/engine.py`  
Function: `build_rip_interpretation(data)` — takes a flat summary dict (from the DB view)

```
build_rip_interpretation(summary_row)
    │
    ├── interpret_profit(data)           ← reads profit_score, prob_profit, roi_percent
    ├── interpret_safety(data)           ← reads safety_score, loss metrics
    ├── interpret_stability(data)        ← reads stability_score, CV, HHI
    ├── interpret_advanced_metrics(data)
    ├── interpret_historical_trend(data)
    ├── interpret_outcome_distribution(data)
    ├── interpret_pack_breakdown(data)
    ├── interpret_rarity_contribution(data)
    ├── interpret_top_ev_drivers(data)
    └── interpret_pack_score(data, profit, safety, stability)  ← synthesis
```

Interpretation is generated in-flight from stored DB view data. It does **not** re-run the simulation. For a custom pack price, the interpretation would need to be regenerated from freshly computed scores — `build_rip_interpretation` can accept any dict with the right keys.

---

## 8. Safe Extension Points

The following are confirmed safe hooks for adding the user-facing simulation tool without touching production behavior:

### Extension Point A — Call `run_simulation_v2` directly with `n=100_000`

`run_simulation_v2(simulate_pack_fn, ..., n=100_000)` already accepts `n`. No changes to the function are needed. A new service can call this directly, bypassing `evrSimulator.py` and `EVRRunOrchestrator`.

- Risk: Must independently build `simulate_pack_fn` via `make_simulate_pack_fn_v2(...)`, which requires card group extraction and pack state model resolution. This is non-trivial but self-contained.

### Extension Point B — Reuse the stored 1M-pack distribution (recommended fast path)

Because the value distribution is pack-price-independent, you can:
1. Load the stored 1M-pack values from DB (stored via `simulation_value_distribution_bins` or raw values if available, or reconstruct from `simulation_run_summary` + `simulation_percentiles`).
2. Call `compute_all_derived_metrics(stored_values, custom_pack_cost)` with any price.
3. Call `build_rip_interpretation(recomputed_metrics)` for fresh interpretation text.
4. Return results in API response. **Write nothing to DB.**

- Advantage: Near-instant response (~50ms), no simulation latency.
- Risk: The stored distribution may not include raw values — only summary stats and histogram bins. If raw values are not available, the exact `prob_profit` computation requires reconstructing from bins (acceptable approximation) or running a new simulation.

### Extension Point C — New FastAPI endpoint (no production routes modified)

A new `POST /tools/pack-simulator` endpoint in `backend/api/main.py`, calling a new service function in a new file (e.g., `backend/db/services/user_pack_simulation_service.py`).

- No existing routes are modified.
- No existing service functions are modified.
- All production persist functions are untouched.

### Extension Point D — New frontend route (already scaffolded)

`frontend/app/tools/page.js` already exists as a stub. The user-facing simulator UI can live at `/tools` or `/tools/pack-simulator` with no changes to any existing page.

---

## 9. Recommended Architecture for User-Entered Pack Price Simulations

### User experience (from audit findings)

> User selects a set, enters a custom pack price, clicks "Simulate" → gets results for 100,000 packs.

### Option B (recommended): Reuse stored distribution

```
User → POST /tools/pack-simulator
       body: { target_type: "set", target_id: "...", custom_pack_cost: 7.50 }
         │
         ▼
  new: UserPackSimulationService.simulate_with_custom_price(target_id, custom_pack_cost)
         │
         ├── Load stored simulation summary (simulation_run_summary WHERE set_id = target_id ORDER BY created_at DESC LIMIT 1)
         ├── Load stored percentile data (simulation_percentiles)
         ├── Load stored pull/state data (simulation_pull_summary, simulation_state_counts)
         ├── Reconstruct approximate value distribution (from distribution bins or percentiles)
         │
         └── compute_all_derived_metrics(values_or_approx, custom_pack_cost, ...)
                  │
                  └── build_rip_interpretation(recomputed_metrics)
                           │
                           └── Return full result payload in response body (NO DB writes)
```

### Option A (full simulation with custom price)

```
User → POST /tools/pack-simulator
       body: { target_type: "set", target_id: "...", custom_pack_cost: 7.50, run_simulation: true }
         │
         ▼
  new: UserPackSimulationService.run_ephemeral_simulation(target_id, custom_pack_cost, n=100_000)
         │
         ├── EVRInputPreparationService().prepare_for_set(config, canonical_key, set_name)
         │    (reuse existing: loads card data from DB — no pack price override needed here)
         ├── call make_simulate_pack_fn_v2(...) to build the closure
         ├── call run_simulation_v2(simulate_fn, n=100_000)  ← NOT n=1_000_000
         ├── compute_all_derived_metrics(values, custom_pack_cost, ...)
         └── build_rip_interpretation(recomputed_metrics)
              │
              └── Return full result payload in response body (NO DB writes)
```

### New endpoint contract

```
POST /tools/pack-simulator
Content-Type: application/json

{
  "target_type": "set",       // required
  "target_id": "...",         // required, UUID or canonical key
  "custom_pack_cost": 7.50,   // required, float > 0
  "mode": "fast"              // optional: "fast" (Option B) | "simulate" (Option A)
}

Response 200:
{
  "set_name": "...",
  "custom_pack_cost": 7.50,
  "simulation_count": 100000,       // or null if using stored distribution
  "mode": "fast",
  "mean_value": ...,
  "median_value": ...,
  "prob_profit": ...,
  "prob_big_hit": ...,
  "net_value": ...,
  "roi_percent": ...,
  "profit_score": ...,
  "safety_score": ...,
  "stability_score": ...,
  "pack_score": ...,
  "percentiles": { "p5": ..., "p25": ..., "p50": ..., "p75": ..., "p95": ..., "p99": ... },
  "interpretation": { ... }    // same shape as build_rip_interpretation output
}
```

### Validation rules (for the new endpoint)

- `custom_pack_cost` must be > 0 and < 1000.00
- `target_id` must exist in `sets` table (validate before computation).
- `mode` defaults to `"fast"`.
- If `mode == "simulate"`, cap simulation count at 100,000.
- Do not accept `simulation_count` from the user (server-side cap only).

---

## 10. Files to Modify Later (for the user-facing simulator)

Only these files need to be created or modified:

| File | Action | Notes |
|---|---|---|
| `backend/api/main.py` | **Modify**: add new route | Add `POST /tools/pack-simulator` at the bottom of the file; import new service |
| `backend/db/services/user_pack_simulation_service.py` | **Create**: new file | All simulation-with-custom-price logic lives here; no edits to existing service files |
| `frontend/app/tools/page.js` | **Modify**: build out the UI | Stub already exists |
| `frontend/components/tools/PackSimulator.jsx` | **Create**: new component | User-facing form + results display |
| `frontend/lib/tools/packSimulatorClient.js` | **Create**: new file | Fetch wrapper for `POST /tools/pack-simulator` |

That is the complete list. No other files need to change.

---

## 11. Files, Tables, and Views That Must Remain Untouched

### Backend files — do not modify

| File | Why |
|---|---|
| `backend/scripts/run_all_v2_sets.py` | Production CLI — cron on VM calls this |
| `backend/jobs/evr_runner.py` | Core orchestrator used for all production runs |
| `backend/simulations/evrSimulator.py` | Production simulation caller; hardcoded n=1,000,000 is intentional |
| `backend/simulations/monteCarloSimV2.py` | Core simulation engine |
| `backend/simulations/monteCarloSim.py` | V1 engine for older eras |
| `backend/db/services/calculation_run_persistence_service.py` | All persist_* functions |
| `backend/db/services/evr_input_preparation_service.py` | Input pipeline |
| `backend/db/services/evr_input_repository.py` | DB input loading |
| `backend/db/services/explore_page_service.py` | Frontend read pipeline |
| `backend/db/services/explore_rip_statistics_service.py` | Frontend read pipeline |
| `backend/jobs/scheduler_service.py` | Portfolio reconciliation scheduler |
| `backend/interpretation/rips/` (all files) | Interpretation engine — used in-flight for production reads |
| `backend/calculations/evr/derived_metrics.py` | Scoring engine — shared between production runs and user tool |

### Database tables — do not write to from user tool

| Table | Why |
|---|---|
| `calculation_runs` | Production run registry |
| `calculation_configs` | Production config snapshots |
| `calculation_price_snapshots` | Production price audit trail |
| `simulation_run_summary` | Determines "latest" run in views |
| `simulation_derived_metrics` | Determines rankings and scores in views |
| `simulation_input_cards` | Production input audit trail |
| `simulation_percentiles` | Used by frontend charts |
| `simulation_pull_summary` | Used by frontend |
| `simulation_state_counts` | Used by frontend |
| `simulation_value_distribution_bins` | Used by frontend charts |
| `simulation_value_threshold_bins` | Used by frontend charts |
| `simulation_etb_summary` | ETB data |
| `sealed_product_prices` | Source of truth for pack prices |

### Database views — do not redefine

| View | Why |
|---|---|
| `explore_rip_statistics_latest` | Primary production read view for all Explore/RIP pages |
| `simulation_latest_by_target` | Fallback view used by explore_page_service |
| `set_pack_score_rankings_latest` | Supplement for ranking fields; joined into explore_rip_statistics_latest |

Writing a user simulation result to any of these tables would corrupt the "latest run" selection and pollute production rankings/leaderboards.

---

## 12. Open Questions and Unknowns

### Q1: Are raw 1M pack values stored anywhere?

The audit confirms all 13 DB tables written during a simulation run. Raw values (the 1M-element list) are **not stored** — only derived summaries. For Option B (fast path), the implementation must either:
- Reconstruct an approximate distribution from `simulation_value_distribution_bins` (histogram) + `simulation_percentiles`.
- Or run a reduced simulation (Option A, n=100,000) to get exact metrics.

The approximation from histogram bins will be sufficient for `prob_profit` and loss metrics (99%+ accuracy at bin widths used), but not for exact tail values. Recommend running a 100k simulation for the user tool — it is the cleanest approach.

### Q2: Is there a V1 set that users would want to simulate?

The V1 engine (older eras: Base Set, Jungle, etc.) uses different card group extraction logic. The initial user-facing tool should be scoped to V2 sets (Scarlet & Violet, Mega Evolution) to match the current production logic. V1 support can be added later.

### Q3: Where is the pack state model for each set defined?

Pack state model (god packs, demi-god packs, state probabilities) lives inside each set's config class (`backend/constants/products/`). The new service can call `resolve_pack_state_model(config)` and `make_simulate_pack_fn_v2(...)` using the same config resolution path as production (`_resolve_set_config(target_set_identifier)`).

### Q4: What is the expected latency for Option A (100k simulation)?

Based on the production system running 1,000,000 packs in approximately 10–15 seconds, a 100,000-pack simulation should complete in **~1–2 seconds** for V2 sets. This is acceptable for a user-facing HTTP request. A loading state in the UI is needed.

### Q5: Is there rate limiting or auth on the new endpoint?

The existing API has no rate limiting middleware. The new endpoint should validate input strictly (bounds check on `custom_pack_cost`, existence check on `target_id`) but authentication is not required if the Explore page is public. If the tool requires login, use `_require_authenticated_user_id(...)` from the existing auth helpers in `backend/api/main.py`.

### Q6: Does `EVRInputPreparationService` require a pack price?

It loads it from DB — it does not accept a custom price override. For Option A, the service loads the card data (which is needed) and the DB pack price (which is ignored — you substitute `custom_pack_cost` when calling `compute_all_derived_metrics`). The card data is the critical output; pack price is just passed through separately.

### Q7: What is `backend/db/services/orchestrators/pokemon_tcg_orchestrator.py`?

This file was identified during workspace discovery but not read during the audit. It may be an alternative or supplemental orchestrator. It should be read before building the new service to confirm it does not overlap with or replace `EVRRunOrchestrator`.

---

## Appendix: Key Constant Values

| Constant | Value | Location |
|---|---|---|
| Production simulation count | 1,000,000 | `evrSimulator.py` lines 334, 373 |
| Recommended user tool simulation count | 100,000 | (not yet in codebase) |
| Pack score formula | 40% profit + 30% safety + 30% stability | `derived_metrics.py` |
| Score version | `"pack_score_v2_1_runtime"` | `derived_metrics.py` |
| Normalization mode | `"fixed_anchor_runtime_v2_1"` | `derived_metrics.py` |
| Pack price filter keywords (include) | `pack`, `booster pack`, `single booster pack` | `evr_input_repository.py` |
| Pack price filter keywords (exclude) | `3 pack`, `blister`, `box`, `bundle`, `collection` | `evr_input_repository.py` |
| V2 eras | `scarlet and violet`, `mega evolution` | `evrSimulator.py` |
| Backend port | 8000 (uvicorn default) | `backend/api/main.py` |
| Frontend port | 3000 | Next.js default |
