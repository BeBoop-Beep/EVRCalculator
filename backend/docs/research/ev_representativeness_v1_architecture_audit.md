# EV Representativeness — Architecture Audit & Proposed Research Data Model

Research method version: `ev_representativeness_v1`
Audit date: 2026-08-22 · Authoritative market date audited: 2026-08-22 (promoted, complete)

This document is the **pre-implementation deliverable**. It records what the
repository actually does today, what may be reused verbatim, what must NOT be
re-derived, the two genuine correctness problems the audit surfaced, and the
persistence/integration model proposed on top of those findings.

---

## A. Current simulation flow (verified, not assumed)

```
backend/jobs/evr_runner.py :: EVRRunOrchestrator.run(target_set_identifier, input_source="db")
  |
  1. _resolve_set_config()                      -> era set config class (210 sets across 17 eras)
  2. EVRInputPreparationService().prepare_for_set(...)
       -> DataFrame `calculation_input` with the FROZEN market prices for the day
          columns incl. "Card Name", "Card Number", "Rarity", "Price ($)",
          "Reverse Variant Price ($)", "Pull Rate (1/X)", "Pack Price"
  3. calculate_pack_stats(calculation_input, config)         [ANALYTIC model]
       initializeCalculations._calculate_ev_columns():
           Effective_Pull_Rate = f(rarity_group, Pull Rate (1/X), pattern_key)
           EV                  = Price ($) / Effective_Pull_Rate
       -> results["hit_ev_contributions"], results["total_manual_ev"]
  4. calculate_pack_simulations(calculation_input, config)   [MONTE CARLO — AUTHORITATIVE]
       simulations/evrSimulator.py :: PackEVRSimulator.calculate_evr_simulations
         extract_scarletandviolet_card_groups(config, df)
             -> pools: common / uncommon / rare / hit / reverse
                (each row tagged with `__source_row_index__` = source df index)
         validate_pack_state_model(config, card_groups)
         make_simulate_pack_fn_v2(...)   simulations/monteCarloSimV2.py
         run_simulation_v2(fn, ..., n=1_000_000)
  5. compute_all_derived_metrics(...)   calculations/evr/derived_metrics.py
  6. persist_parent_run_with_price_snapshots() -> calculation_runs row (run_id)
  7. persist_simulation_inputs(run_id, ...)    -> simulation_input_cards
  8. run_stage1_sealed_product_rip(sim_results, ...) -> simulation_sealed_product_results
  9. persist_simulation_outputs(run_id, sim_results, pack_metrics, derived)
       -> simulation_run_summary, simulation_percentiles, simulation_pull_summary,
          simulation_state_counts, simulation_derived_metrics,
          simulation_pack_outcome_artifacts   <-- THE RAW 1,000,000-PACK VECTOR
```

Daily cohort orchestration is `backend/scripts/run_daily_opening_publication.py ::
orchestrate()` — numbered steps, each recording a status string on
`PublicationSummary`, fail-closed on the publication gate.

### One-pack outcome generation (the actual model)

`make_simulate_pack_fn_v2` closes over precomputed `_ArrayPool`s and, per pack:

1. **god path** — `rng.random() < GOD_PACK_CONFIG.pull_rate`
2. **demi-god path** — `rng.random() < DEMI_GOD_PACK_CONFIG.pull_rate`
3. **normal path** — sample a *pack state* from `state_probabilities`
   (`resolve_pack_state_model(config)`), which fixes the token in each of the
   three variable slots (`rare`, `reverse_1`, `reverse_2`); then
   `_sample_cards_fast` draws `SLOTS_PER_RARITY["common"]` commons,
   `SLOTS_PER_RARITY["uncommon"]` uncommons uniformly with replacement, and one
   card per variable slot from that slot's token pool with a bounded
   without-replacement exclusion (`selected_source_rows`, 8 retries then a mask).

So: pull rates are represented as a **pack-state distribution over slot
outcomes**, not as independent per-card probabilities; rarity slots are the three
variable slots plus fixed base slots; a card contributes value by being drawn
into a slot at its frozen `Price ($)` (or `Reverse Variant Price ($)` for the
reverse pool).

### What is persisted

| Table | Grain | Contents relevant here |
|---|---|---|
| `simulation_pack_outcome_artifacts` | 1 row / run | **zlib float64 vector of all 1,000,000 pack totals**, sha256-verified, `format_version=1` |
| `simulation_run_summary` | 1 row / run | `mean_value`, `median_value`, `std_dev`, `coefficient_of_variation`, `pack_cost`, `total_ev`, `simulation_count`, `tail_value_p05` |
| `simulation_percentiles` | 1 row / (run, pct) | 5/25/50/75/90/95/99 |
| `simulation_pull_summary` | 1 row / (run, rarity) | `pulled_count`, `total_sampled_value`, `avg_sampled_value` — **the simulator's own rarity decomposition** |
| `simulation_state_counts` | 1 row / (run, group, name) | `pack_path` (normal/god/demi_god) + `normal_pack_state` occurrence counts |
| `simulation_input_cards` | 1 row / (run, card) | `price_used`, `effective_pull_rate`, `ev_contribution` (**analytic**), `rarity_bucket` (coarse: hits/rare/common/uncommon) |
| `simulation_derived_metrics` | 1 row / run | Financial RIP V3 payload + scalars, `hhi_ev_concentration`, `top1/2/3/5_ev_share` (**analytic-card based**) |
| `simulation_sealed_product_results` | 1 row / (run, SKU) | `pack_count`, `product_market_cost`, `product_family`, Financial RIP V4, Overall RIP V10 |

**Yes — raw opening outcomes are retained.** That artifact is the substrate for
this entire research layer; nothing here needs to re-run the daily simulation to
answer Parts 1–5, 11–17 and 20–25.

### Authoritative run selection

`backend/db/services/opening_simulation_gate.py :: evaluate_opening_simulation_freshness(client, market_date=...)`
is the canonical authority: it returns one `OpeningSetSimulationStatus` per
supported opening set with the `calculation_run_id` whose
`calculation_history_trend.snapshot_date` equals the market date, cross-checked
against `simulation_run_summary`. `pokemon_rip_stats_service` already consumes it
exactly this way. **Verified live for 2026-08-22: `ok=True, eligible=22,
current=22, failed=0`. All 22 runs have a 1,000,000-outcome artifact and a
`financial_rip_v3_status='ready'` derived-metrics row.**

The published leaderboard (`pokemon_public_rip_leaderboard_snapshots`) is at
market_date **2026-08-17** — five days stale. The research layer will therefore
take Financial RIP from `simulation_derived_metrics` / `simulation_sealed_product_results`
**on the same runs it analyses**, not from the leaderboard, so H5 compares
same-day, same-run quantities.

### Market-date price freezing

Prices enter once, in `EVRInputPreparationService.prepare_for_set`, and are
snapshotted onto the run by `persist_parent_run_with_price_snapshots` and
`simulation_input_cards.price_used`. The research layer never re-prices; price
counterfactuals (Part 19) are computed **off** the frozen basis and never written
back.

---

## B. Two correctness findings that shape the design

### Finding 1 — the analytic card EV table is NOT the simulator's decomposition

Measured on `prismaticEvolutions`, run `25bf50bf…`:

```
sum(simulation_input_cards.ev_contribution) = $5.8005   (348 cards)
simulation_run_summary.mean_value           = $8.5328
```

A **47% divergence.** `simulation_input_cards.ev_contribution = Price / Effective_Pull_Rate`
is the analytic model that also produces `calculated_expected_value_per_pack`;
the repository already persists it *separately* from `actual_simulated_ev`
precisely because they are different quantities.

Consequence, and this is exactly what the brief warned about: **Part 6/7 must not
use `simulation_input_cards.ev_contribution`, and must not use
`P(card) × price`.** Card-level expected copies must come from the simulator.
The existing `simulation_derived_metrics.top1_ev_share` / `hhi_ev_concentration`
are built on the analytic contributions, so the research layer will compute
simulator-based card concentration under **new, distinctly-named fields** and
will report both side by side rather than redefining the published ones.

Cross-check that the simulator's own rarity decomposition *is* exhaustive
(same run):

```
sum(simulation_pull_summary.total_sampled_value) / 1e6 = 8.532834580000712
simulation_run_summary.mean_value                      = 8.53283458
```

Exact to 10 significant figures. **`simulation_pull_summary` is therefore the
authoritative, already-persisted answer to Part 8** (rarity EV contribution and
expected copies per pack) and will be reused verbatim — no re-derivation.

### Finding 2 — the authoritative simulation is NOT seeded

`monteCarloSimV2._to_rng()` returns `np.random.default_rng()` when no generator
is passed, and `evrSimulator` passes none. The persisted 1M vector `X` is
therefore **not reproducible by re-running the simulator**. (The sealed-product
bootstrap is separately seeded and reproducible *given* `X` — see
`sealed_product_distribution.stage1_distribution_seed`, whose docstring already
states this gap.)

This forces an explicit two-tier provenance model rather than a silent mix:

| Tier | Source | Reproducible? | Used for |
|---|---|---|---|
| **A — exact** | the persisted authoritative artifact `X` + `pack_cost` | Yes, bit-exact forever (sha256-pinned) | Parts 1–5, 11–17, 20–25. Matches published EV/P50/RIP exactly. |
| **B — research re-simulation** | a **seeded** instrumented re-run of the same config + same frozen prices | Yes, from the seed | Parts 6, 7, 9, 10, 18, 19 (card attribution, per-pack decomposition, ablations, shocks) |

Tier B's own mean will differ from Tier A's by Monte Carlo error
(σ/√n ≈ $0.0998 ≈ 1.2% of EV for prismatic). Every Tier B result is therefore
reported **against Tier B's own baseline** (paired, common-random-numbers deltas
— which is the statistically correct way to state an ablation anyway), and the
Tier A↔B reconciliation gap is persisted with the row so no reader can mistake
one for the other. Seeding the production simulator is *not* proposed here: it
would change daily output and is out of scope for a research phase.

---

## C. What is reused verbatim (no parallel definitions)

| Need | Canonical thing being reused | Why it must not be re-derived |
|---|---|---|
| Top-1% EV share, top-1% conditional mean | `financial_rip_v3.TailBuckets` + `compute_base_economic_efficiency_raw().jackpotValueShare` / `compute_jackpot_upside_raw().jackpotTailMeanValue` | Already the canonical "jackpot" vocabulary. Part 4.3/4.4 **are** these metrics; 5% and 10% extend the *same rank-based rule* (`k = max(1, ceil(n·q))`) |
| Rank-based tail selection | `TailBuckets` docstring rule | These distributions are dense with ties (largest plateau ≈ 1.0% of mass). A `values >= np.percentile(v, 99)` mask can silently select far more than 1%. Rank buckets fix the *mass* |
| Session/product outcome vectors | `calculations/evr/sealed_product_distribution.build_stage1_product_distributions` + `stage1_distribution_seed` | Already the canonical i.i.d.-pack bootstrap with a stated independence assumption, chunked memory bound and a SHA-256 process-stable seed |
| Product → pack count | `simulation_sealed_product_results.pack_count` (per SKU, per run) and `domain/pokemon/sealed_product_composition` | Live cohort has 137 product rows / 8 families / pack counts **{1, 6, 9, 11, 18, 36}** — ETB=9 vs Pokémon Center ETB=11, confirming the brief's "do not hardcode ETB pack counts" |
| Rarity taxonomy | `packStateCoercion.normalize_rarity` + the rarity keys already in `simulation_pull_summary` | The simulator owns the mapping; no hardcoded rarity name lists |
| Collective hit probability | `simulation_state_counts` (`normal_pack_state`) × `resolve_pack_state_model(config).state_outcomes` | Gives P(any SIR) etc. **exactly** from the slot model — no independence approximation, which the brief explicitly forbids |
| Pearson / Spearman / Kendall / bootstrap CI / permutation p / BH / partial correlation | `backend/research/validation_stats.py` | Already exists, tie-corrected, research-grade |
| Percentile helpers, CV, downside | `calculations/evr/derived_metrics.compute_volatility_metrics` / `compute_downside_metrics` | Canonical P05/P25/P50/P75/P95/P99 + CV definitions |

**Not reused:** `simulations/value_threshold_bins.DEFAULT_VALUE_THRESHOLD_BUCKETS`
is an **absolute-dollar** bucket contract (0–0.5, …, ≥5000), so it cannot answer
Part 5's cost-normalized question. Return-ratio buckets are added as a *new,
separately-named research contract*; the dollar buckets stay untouched.

---

## D. Live evidence already in hand (a sanity check that the question is real)

22-set authoritative cohort, 2026-08-22, straight from `simulation_run_summary`:

| | EV | P50 | Typical Capture | CV |
|---|---|---|---|---|
| widest gap | $8.53 | $1.78 | **20.9 %** | 11.69 |
| … | $12.82 | $3.73 | 29.1 % | 2.62 |
| tightest gap | $3.44 | $1.89 | **54.9 %** | 1.97 |

Outcome-level tail concentration (rank buckets, exact, from the artifacts):

| Set | top-10 % EV share | top-5 % | top-1 % |
|---|---|---|---|
| prismaticEvolutions | 80.0 % | 76.1 % | **64.1 %** |
| scarletAndVioletBase | 54.3 % | 40.7 % | **14.6 %** |

Two sets, same simulator, and a 4.4× difference in how much of the economy lives
in the top 1% of openings. The cross-sectional spread (Typical Capture 20.9 % →
54.9 %, CV 1.9 → 11.7) is wide enough for the H1–H4 correlations to be
informative on n=22 — while still small enough that every correlation must be
reported with a bootstrap CI and a permutation p-value, not a bare r.

---

## E. Performance evidence (measured, this machine)

| Operation | Measured |
|---|---|
| Load + zlib-decode + sha256-verify one 1M artifact | **1.09 s** |
| Session-path kernel: N-grid `[1 … 10 000]`, 50 000 sessions, cumulative-sum with common random numbers | **3.51 s** (500 M draws, **142 M draws/s**) |
| Daily authoritative run, per set, end-to-end (from artifact `created_at` deltas) | **~70 s** |
| Artifact size | 1 M × float64 → ~2.1 MB compressed |

Implication: **Tier A (all horizons, all convergence curves, all 22 sets) costs
minutes, not hours.** The expensive part is Tier B, which re-runs the 1M-pack
Python simulation loop (~60–70 s/set, ~25 min cohort-wide with instrumentation
overhead) — which is precisely why Tier B is a separate, opt-in job.

---

## F. Simulation strategy for the finite-sample layer (Parts 11–14, 23–25)

**Resample with replacement from the persisted `X`.** Justification: `X` is
itself 1,000,000 i.i.d. draws from the pack model, so `X̄_N` built from
with-replacement draws is an unbiased bootstrap of the true finite-sample
distribution. The finite-population artifact is negligible: even at N = 25 000
the sampling fraction is 2.5 %, and *with* replacement there is no
without-replacement variance deflation at all. The alternative — generating fresh
packs from the simulator — costs ~70 s per set *per N-grid point* and would not
be reproducible (Finding 2). This is also exactly what
`build_stage1_product_distributions` already does for sealed products, so the
research layer inherits a contract the repository has already reasoned about.

**Kernel:** maintain a running `float64` sum vector of shape `(n_sessions,)` and
add `(N_{i+1} − N_i)` fresh draws at each grid step (chunked to bound the index
block). Memory is `O(n_sessions)`, not `O(n_sessions × N_max)`; total work is
`n_sessions × N_max` draws. This is the "cumulative sums over independent
simulated paths" option, and it gives **common random numbers across the N-grid**
for free.

**CRN caveat, stated rather than hidden:** CRN smooths the *shape* of
`P̂(N)` in N (each session's path is nested), which materially reduces spurious
local oscillation — but it means `P̂(N)` and `P̂(N+1)` are positively correlated,
so a "held for k consecutive checkpoints" rule is weaker evidence than k
independent checks would be. Each individual `P̂(N)` is still a clean binomial
proportion over `n_sessions` independent sessions, so its **Wilson** interval is
valid marginally. Wilson is chosen over Wald because the horizon question lives
near p ≈ 0.8–0.95 where Wald's symmetric interval misbehaves and can even exceed 1.

**Horizon rule (the brief's monotonicity warning):** two distinct quantities are
persisted, never one.
- `first_crossing_N` — smallest grid N with `P̂ ≥ c`. Recorded, explicitly labelled noisy.
- `stable_horizon_N` — smallest grid N such that the **Wilson lower bound** ≥ c
  *and* that holds at every subsequent checkpoint in a validation band, re-estimated
  at the confirmation session count with an independent seed stream.
Monotonicity is **measured, not assumed**: the per-set count of local decreases in
`P̂(N)` and their maximum magnitude are persisted so the assumption can be audited
after the fact. No binary search is used anywhere.

**Adaptive precision (Part 24):** coarse grid at `n_sessions = 50 000` → refine
around the candidate crossing on a dense integer sub-grid → confirm the reported
horizon at `n_sessions = 250 000` with an independent seed. Reported horizons
carry the confirmation-stage estimate, its Wilson interval, and the stage that
produced them.

**CLT comparison (Part 25):** `N ≈ (z_c·σ / ((1−r)·μ))²` computed from the
Tier A σ and μ, persisted alongside the empirical horizon plus their ratio, so
"at what N does the asymptotic approximation become usable for these
distributions" is answerable directly. It is never used as the reported horizon.

---

## G. Instrumentation seam for Tier B (Parts 6, 7, 9, 10, 18, 19)

Verified: `_build_array_pool`, `_sample_pool_total`, `_sample_single_from_array_pool`,
`_sample_cards_fast`, `_sample_rows_with_rarity` and
`_resolved_rows_to_rarities_and_values` have **zero references outside
`monteCarloSimV2.py`** (no tests, no other modules). Every pool row already
carries `__source_row_index__` (set in `extractScarletAndVioletCardGroups`).

Proposed change — **additive and opt-in**: one new keyword-only
`research_recorder=None` on `make_simulate_pack_fn_v2`, threaded to
`_sample_cards_fast` and `_sample_special_pack_details`. When `None` (the
production default) the code path and RNG consumption are **bit-identical to
today**; a guardrail test will assert that a seeded run with and without a
recorder produces the same vector.

When present, the recorder records per pack the **sampled entity ids**, where an
"entity" is a `(source_row_index, price_column)` pair registered once up-front —
because a card appears in the normal pool at `Price ($)` and in the reverse pool
at `Reverse Variant Price ($)`, and those are economically different draws.
Storing ids rather than values is what makes counterfactuals exact and cheap:

```
X'[p] = price'[ entity_ids[p, :] ].sum()
```

so a rarity ablation, a top-card ablation, a top-1 % winsorization and a −10 %/
−25 %/−50 % chase shock are all **one gather and one sum over the same sampled
paths** — perfectly paired against the Tier B baseline, no re-simulation per
counterfactual, and no independence assumption anywhere.

Footprint per set: 1 M packs × (4 commons + 3 uncommons + 3 slots) × int32 ≈
**40 MB transient**, plus a small variable-length overflow list for god/demi packs
(measured at 0.19 % of packs: 502 god + 1 412 demi per million on prismatic).
`_sample_rows_with_rarity` / `_resolved_rows_to_rarities_and_values` gain a third
return element so god/demi pulls are attributed to real source rows too — they
are private to this module, so the special-pack path gets **full card attribution
rather than a documented blind spot**. Nothing is persisted at pack grain.

Self-validation: Σ(card EV contributions) must equal the Tier B simulated mean to
float tolerance, the same identity that `simulation_pull_summary` already
satisfies at rarity grain. That check gates the write.

---

## H. Integration decision — **Option B**, with a Tier A / Tier B split

> Research results should remain attached to the exact authoritative simulation
> inputs/results but should not destabilize the core publication gate.

**Chosen: Option B — a separate post-simulation research builder keyed to the
authoritative `calculation_run_id`.** Not A, not C.

- **Not A (inline, right after each set's simulation).** The per-set EVR run is a
  *subprocess per set* (`run_simulations_for_sets`) and it is the publication
  critical path. Adding minutes of research computation inside it directly
  lengthens the gate, and any research exception would surface as a simulation
  failure. The repository already learned this shape once: sealed-product
  Collector Appeal was deliberately **moved out** of the per-set subprocess into a
  single-process finalization step because the per-set cost was unacceptable
  (see `sealed_product_rip_service.deferred_collector_appeal`'s docstring).
- **Not C (share lower-level artifacts, publish async).** Nothing needs sharing:
  the lower-level artifact is *already persisted and sha256-pinned*. C would add
  coupling for no gain.
- **B works because the artifact exists.** The builder re-opens the exact
  authoritative run by `calculation_run_id`, verifies the artifact's
  `raw_sha256`, and is therefore attached to the identical inputs the published
  numbers came from — while running in its own process, at its own cadence, with
  its own failure surface.

Wiring: one new **non-blocking** step in `run_daily_opening_publication.orchestrate()`,
placed *after* Step 3 verification and *after* RIP Stats, recording
`summary.ev_representativeness_status`. It can never set `summary.exit_code`.
Tier B (`--with-research-resimulation`) is **off by default** and is intended to
be run manually or on a separate schedule. Failure is loud in logs and in the
status string, and is distinguishable from a simulation failure by its own
status vocabulary (`research_*` prefixes) and its own exception type.

---

## I. Proposed research data model

Four tables — the smallest set that keeps the four genuinely different grains
apart without fragmenting into a table per metric. All prefixed
`ev_representativeness_` and versioned by `research_method_version`.

### 1. `ev_representativeness_run_summary` — grain: (calculation_run_id, research_method_version)

The scalar layer: Parts 1, 2, 3, 4, 7, 22, 25.

```
calculation_run_id          UUID   REFERENCES calculation_runs(id) ON DELETE CASCADE
research_method_version     TEXT   -- 'ev_representativeness_v1'
PRIMARY KEY (calculation_run_id, research_method_version)

set_id UUID REFERENCES sets(id), set_canonical_key TEXT, market_date DATE

-- provenance (Part 26)
source_artifact_sha256 TEXT NOT NULL, source_outcome_count INT NOT NULL,
pack_cost NUMERIC NOT NULL CHECK (pack_cost > 0),
simulation_engine_version TEXT, session_seed BIGINT, session_count_coarse INT,
session_count_confirm INT, metric_config JSONB NOT NULL,

-- Part 1
sample_size INT, ev NUMERIC, variance, std_dev, coefficient_of_variation,
p10, p25, p50, p75, p90, p95, p99 NUMERIC,

-- Part 2
ev_typical_gap_absolute, ev_typical_gap_cost_normalized,
typical_capture, relative_gap NUMERIC,      -- relative_gap = 1 - typical_capture, both exposed

-- Part 3 (research diagnostics only)
pearson_skew_2, groeneveld_meeden_skew, mean_abs_dev_about_median NUMERIC,

-- Part 4 — rank-bucket contract, reusing TailBuckets' rule
top10_outcome_ev_share, top5_outcome_ev_share, top1_outcome_ev_share,
top10_conditional_tail_mean, top5_conditional_tail_mean, top1_conditional_tail_mean NUMERIC,
tail_selection_method TEXT,                 -- stamped from FINANCIAL_RIP_V3_TAIL_CONTRACT_VERSION

-- Part 7 (Tier B; NULL until the re-simulation runs — never faked)
sim_top_card_ev_share, sim_top5_card_ev_share, sim_top10_card_ev_share,
sim_card_hhi, sim_effective_card_count NUMERIC,
sim_baseline_mean NUMERIC, sim_baseline_reconciliation_gap NUMERIC,  -- Tier B vs Tier A, disclosed
sim_pack_count INT, sim_seed BIGINT,

-- Part 25
clt_horizon_n_by_target JSONB,              -- {r: {c: N}}
clt_vs_empirical_ratio  JSONB,

-- Part 13/14 headline horizons, promoted to columns for ranking
horizon_r80_c80_first_crossing INT, horizon_r80_c80_stable INT,
horizon_tau20_c80_first_crossing INT, horizon_tau20_c80_stable INT,
horizon_status TEXT,                        -- 'resolved' | 'exceeds_search_cap' | 'degenerate'
horizon_search_cap INT,
monotonicity_violation_count INT, monotonicity_max_decrease NUMERIC,

diagnostics_json JSONB, built_at TIMESTAMPTZ NOT NULL DEFAULT now()
```

Distribution-bucket percentages (Part 5) and rarity-layer contributions (Part 8)
live in `diagnostics_json`/a JSONB column rather than their own tables: they are
small, always read whole, and never filtered on — a table per bucket would be
fragmentation for its own sake. The **underlying percentiles are columns**, so
nothing depends on a bucket definition we may revise.

### 2. `ev_representativeness_curve` — grain: (calculation_run_id, version, scope, pack_count, metric_key)

The finite-sample layer: Parts 11, 12, 17, 22 — one row per evaluated N per
threshold. This is the only genuinely high-cardinality table (~22 sets × ~35 grid
points × ~15 metric keys ≈ 11 k rows/day), and it must be a table rather than
JSONB because the cross-sectional analysis filters and joins on
`(pack_count, metric_key)`.

```
calculation_run_id UUID, research_method_version TEXT,
scope_kind TEXT,          -- 'pack_grid' | 'product'
sealed_product_id UUID NULL REFERENCES sealed_products(id),  -- set for scope_kind='product'
pack_count INT NOT NULL CHECK (pack_count >= 1),
metric_key TEXT NOT NULL,  -- 'realization_ge_0.80' | 'within_tau_0.20' | 'session_p50' | ...
PRIMARY KEY (calculation_run_id, research_method_version, scope_kind,
             COALESCE(sealed_product_id,'000…'::uuid), pack_count, metric_key)

estimate NUMERIC NOT NULL,
session_count INT, successes INT NULL,          -- NULL for non-probability metrics
monte_carlo_standard_error NUMERIC NULL,
ci_lower NUMERIC NULL, ci_upper NUMERIC NULL, ci_method TEXT NULL,  -- 'wilson_95'
stage TEXT NOT NULL,                             -- 'coarse' | 'refine' | 'confirm'
seed BIGINT
```

Part 17's session distribution (`mean/median/P10…P99` of `X̄_N`, plus
session-return-vs-session-cost percentages) is carried as additional
`metric_key`s on this same table — same grain, same provenance, no fifth table.

### 3. `ev_representativeness_card_contribution` — grain: (calculation_run_id, version, entity)

Part 6: *"Persist or make queryable the contribution for every card."* Tier B only.
~350 rows per set. Written **only** when the identity
Σ`ev_contribution_per_pack` = `sim_baseline_mean` holds.

```
calculation_run_id UUID, research_method_version TEXT,
source_row_index INT, price_column TEXT,     -- the entity: normal vs reverse draw
PRIMARY KEY (calculation_run_id, research_method_version, source_row_index, price_column)
card_name TEXT, card_number TEXT, rarity_key TEXT,
price_used NUMERIC, expected_copies_per_pack NUMERIC,
ev_contribution_per_pack NUMERIC, ev_share NUMERIC, ev_rank INT,
observed_pull_count BIGINT, sim_pack_count INT
```

### 4. `ev_representativeness_counterfactual` — grain: (calculation_run_id, version, scenario_key)

Parts 18 + 19, one row per scenario, each carrying the same metric block as the
baseline so deltas are read off directly.

```
calculation_run_id UUID, research_method_version TEXT, scenario_key TEXT,
PRIMARY KEY (calculation_run_id, research_method_version, scenario_key)
scenario_family TEXT,   -- 'rarity_ablation' | 'top_card_ablation' | 'winsorization' | 'price_shock'
scenario_params JSONB,
ev, p50, p95, ev_typical_gap_absolute, typical_capture,
top1_outcome_ev_share, top5_outcome_ev_share, top10_outcome_ev_share NUMERIC,
horizon_r80_c80_stable INT, horizon_tau20_c80_stable INT, horizon_status TEXT,
delta_vs_baseline JSONB, baseline_kind TEXT   -- always 'tier_b_paired'
```

### Cross-cutting requirements

- **Idempotent / no duplicate snapshots on rerun** — every write is an upsert on
  the natural key above; a rerun with the same `(run, version)` overwrites in
  place. `ON CONFLICT DO UPDATE`, never blind insert.
- **No cross-run contamination** — `calculation_run_id` is in every primary key
  and every FK is `ON DELETE CASCADE` from `calculation_runs`.
- **Versioned** — `research_method_version` is in every primary key, so
  `ev_representativeness_v2` coexists with v1 rather than overwriting it.
- **Market-date aware** — `market_date` denormalized onto the summary for
  cross-sectional queries; the run FK remains the authority.
- **RLS** — mirrors migration 065/069/070 posture exactly: RLS enabled, **no**
  read policy, `REVOKE ALL FROM PUBLIC, anon, authenticated`,
  `GRANT SELECT, INSERT, UPDATE, DELETE TO service_role`. Nothing public.
- **Safe retry** — writes are per-run and ordered summary-last, so a partial
  failure leaves the summary row absent and the run visibly un-built rather than
  half-claimed; `supabase_persistence_retry` is reused for transient faults.
- **Not a publication dependency** — no publication gate, contract audit or
  snapshot builder reads these tables in this phase.

Migrations follow the repository's manual convention (`BEGIN; CREATE TABLE IF NOT
EXISTS …; COMMIT;`, idempotent, safe to re-run, **not** applied by any automated
process).

---

## J. Proposed module layout

```
backend/research/ev_representativeness/
    __init__.py
    version.py              # EV_REPRESENTATIVENESS_VERSION = 'ev_representativeness_v1' + config constants
    distribution.py         # Parts 1-5: baseline stats, gaps, skew diagnostics, rank tail buckets, ratio buckets
    finite_sample.py        # Parts 11-14, 17, 22-24: session kernel, Wilson, horizon rules, monotonicity audit
    clt.py                  # Part 25
    contribution.py         # Parts 6-10: card/rarity contribution + collective & economic hit frequency
    counterfactual.py       # Parts 18-19
    recorder.py             # Tier B recorder object handed to the simulator
backend/db/services/ev_representativeness_service.py     # cohort resolution + persistence (Option B builder)
backend/db/migrations/2026…_create_ev_representativeness_research_tables.sql
backend/scripts/build_ev_representativeness_research.py  # CLI: --market-date, --with-research-resimulation, --dry-run, --export
backend/scripts/report_ev_representativeness_research.py # Parts 20-21, 30-33: cross-sectional analysis + Markdown/CSV/JSON
backend/tests/unit/research/test_ev_representativeness_*.py   # Part 34 fixtures
```

Simulator change is confined to `simulations/monteCarloSimV2.py`: one optional
keyword, default `None`, plus a third return element on two module-private
helpers.

---

## K. Explicitly out of scope this phase (Part 29)

No frontend. No change to Financial RIP V3/V4, Overall RIP V9/V10, Collector
Appeal, `compute_pack_scores_for_set_records`, or any published metric name or
weight. No paywalling. No public naming: `horizon_r80_c80_stable` and
`horizon_tau20_c80_stable` stay parametric column names, and "Packs to 80 % EV"
stays an internal working label until the report says whether it is defensible.

---

## L. Known limitations to carry into the report

1. **n = 22 sets.** Correlations get bootstrap CIs and permutation p-values; no
   causal language.
2. **137 product rows are NOT 137 independent observations** — they are 22
   underlying pack distributions re-expressed at 6 pack counts. Product-level
   analysis will be reported with set-clustered handling and the effective sample
   size stated as 22, never 137.
3. **Pack independence** — inherited from
   `empirical_independent_pack_bootstrap_v1`; real collation/box guarantees are
   not modeled, and the disclosure travels with every row.
4. **Tier B ≠ Tier A** by Monte Carlo error (~1.2 % of EV at n = 1 M for the
   highest-CV set); the gap is persisted, not smoothed away.
5. **Gross card value only** — `X` is gross market value, no fees, no
   condition/grading, no accessory value. Consistent with `pokemon_rip_stats`'
   `recoveryModel = gross_market_value`.
