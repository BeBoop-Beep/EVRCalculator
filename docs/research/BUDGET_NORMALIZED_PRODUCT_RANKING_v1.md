# Budget-Constrained Whole-Unit Product Ranking — Internal Capability (V1, FROZEN)

**Date:** 2026-08-22 (methodology) / 2026-08-23 (V1 freeze + implementation)
**Status:** FROZEN. Internal infrastructure only. No customer-facing exposure.
**Extends** `OVERALL_PRODUCT_RANK_DECISION_2026-08-22_v2.md`.
**Validation detail:** `BUDGET_NORMALIZED_PRODUCT_RANKING_v1_VALIDATION_APPENDIX.md`.

---

# APPROVED METHOD

## `BUDGET_CONSTRAINED_WHOLE_UNIT_RANKING_V1_APPROVED`

### Exact semantics

For a budget ceiling `B` and product market price `P`:

```
quantity                = floor(B / P)          -- eligible only when quantity >= 1
actualCommittedCapital  = quantity * P
unusedCapital           = B - actualCommittedCapital
unusedCapitalPercent    = unusedCapital / B
capitalUtilization      = actualCommittedCapital / B
```

A strategy is: **buying and opening the maximum number of whole units of ONE sealed-product SKU
that fit within the selected spending ceiling.** No fractional purchases. A product priced above
the ceiling is recorded ineligible, never silently dropped.

### The question this answers

> **What should I OPEN with up to $X?**

Consumer statement: *"Ranks whole-product opening strategies that fit within your selected
spending limit."*

Fuller tooltip: *"Different sealed products cost different amounts. inDex compares how many whole
units of each product fit within your selected budget, then ranks the resulting modeled opening
strategies. Any money left over is not included in the opening score."*

### Unused cash

Recorded as metadata and disclosure. **Never** scored, invested, or folded into Financial RIP V4.

This is a real product limitation, deliberately preserved rather than papered over. The
retained-cash control (appendix §7) showed that adding leftover cash materially changes
terminal-wealth ordering (Spearman 0.67 on terminal median wealth) — because holding cash is a
guaranteed risk-free retention no pack-opening distribution can match. Ranked on terminal wealth,
the "best" strategy trends toward buying as little as possible, which does not answer "what should
I open?".

**Therefore:** this ranking evaluates *the opening strategy*, not *the optimal financial use of
the entire budget*. Copy must say "to open", never "the best use of your money".

### This is NOT equal committed capital

Two strategies at the same budget generally commit different amounts: a $1,339 product commits
$1,339 of a $1,350 ceiling; a $450 product commits $1,350 exactly. Never describe this as equal
spend, equal committed capital, identical spend, matched capital, best use of your money,
portfolio optimization, or total-wealth optimization.

### Why matched capital was rejected for production UX

1. **It excludes the most expensive SKU.** Under the preregistered pairwise bounds (5% tolerance,
   `MAX_PAIR_SPEND = $1,000`) the $1,339.19 SKU cannot be matched against anything, giving
   136/137 coverage. Restoring full coverage requires abandoning the bound the existing validated
   research rests on.
2. **It answers a different question** — "which format is fairer at comparable spend" — which is a
   researcher's question, not a shopper's.
3. **The two are not interchangeable.** They agree globally (Spearman ~0.95) but disagree on the
   podium (top-5 overlap 1–3 of 5), so the choice is substantive, not cosmetic.

Matched capital is retained as a **research control** in
`backend/scripts/research_budget_ranking_semantics.py`, not as production semantics.

### Why budget-constrained was approved

* **Negligible allocation bias.** Spearman(capital utilization, rank) = **−0.073**, Pearson
  **−0.028** — inside ±0.10, and the sign is the opposite of the feared bias. Utilization
  quartiles are non-monotonic (Q1 beats Q2).
* **Dominance-clean allocation.** Isolating the allocation from Collector Appeal (ranking on
  Financial RIP V4 alone): **2 inversions / 4,508 comparable pairs = 0.044%** at $1,350; worst
  observed 0.108% at $1,600. ~98–100% of the higher V10 inversion rate is Collector Appeal
  operating exactly as designed (0.90 financial + 0.10 appeal).
* **High Full Market stability.** Spearman ≥ 0.993 from $1,350 to $1,600, with Top-5, Top-10 and
  Top-20 perfectly preserved at every anchor; mean rank movement ≤ 2.
* **Replicated** on two independent cohorts (`price_as_of` 2026-08-17 and 2026-08-21).

### Full Market rule

```
full_market_budget = ceil(maxEligibleSkuPrice / 50) * 50
```

Rule version: `full_market_next_50_above_max_eligible_sku_v1`. **Dynamic — never hard-code the
dollar value.** Each publication persists `full_market_budget`, `max_eligible_sku_price`,
`full_market_rounding_increment` and `full_market_rounding_rule_version`.

$50 is evidence-backed: $25 resolves to the same anchor on the current cohort but churns twice as
often (4 boundary changes vs 2 across a price sweep); $100 inflates committed capital 4.54% above
the max SKU versus 0.81% for $50 — 5.6× the excess — and buys no measured stability, because ranks
are near-invariant from $1,350 to $1,600. Confirmed by real drift during validation: the max SKU
price moved $1,339.19 → $1,331.19 and the $50 anchor held at $1,350.

### Full Market's role

**Internal reference first.** It is the complete-cohort benchmark, methodology monitor,
regression/stability anchor and cross-format reference. The intended future customer experience is
*the user selecting their own budget* — Full Market is not assumed to be a customer-facing control
and is not mentioned on the locked UI.

---

## Why universal Overall Rank was rejected

Rank is budget-dependent: no single tested budget (or a practical full-cohort anchor at the raw
maximum price) gave 100% cohort coverage without either excluding the most expensive SKUs or
forcing absurd quantities on the cheapest ones. A context-free "#X / all products" claim cannot
honestly describe one stable population.

## Why budget-normalized ranking is supported

Budget-ceiling comparison, using whole purchasable retail units and the real multi-unit outcome
distribution (never `single-unit metric × quantity`), behaved coherently across every tested
budget. This is genuinely useful, auditable, and explainable in one sentence — it was simply never
a *universal* rank.

> **Corrected at the V1 freeze (2026-08-23).** This section originally read *"Equal-committed-capital
> comparison … zero dominance inversions, near-perfect (median Spearman ρ = 1.0) cross-budget rank
> stability."* The original wording is quoted here rather than quietly rewritten:
>
> * **"Equal-committed-capital"** was never what the implementation did — it has always been
>   floor-to-budget. See "This is NOT equal committed capital" above.
> * **"Zero dominance inversions"** was a measurement artifact, not a result. Raw metrics were read
>   from the Financial RIP V4 projection, whose `audit.normalizedInputs` is empty, so
>   `multi_metric_dominator` (which requires all four metrics present) could never fire and
>   reported zero *comparable pairs*. Measured correctly, the allocation inverts on **0.044%** of
>   comparable pairs at $1,350 — excellent, but not zero. Fixed in
>   `research_equal_spend_product_rip_v4.py`, which now raises rather than silently reporting a
>   vacuous pass.
> * **"median Spearman ρ = 1.0"** was computed *within* small per-set cohorts, not across the
>   cross-format population; it is not comparable to the ρ ≈ 0.93–0.99 figures reported elsewhere
>   and should not be read as contradicting them.

## Why Full Market exists

To give one budget point where every currently eligible modeled SKU can participate, so "what's
best across everything" has an actual, complete answer — while still being explicit that it is
one specific (large) budget, not an intrinsic property of the product. **Live-verified: Full
Market resolves to $1,350 for the pinned 2026-08-21 cohort (`ceil(1331.19 / 50) * 50`), and produces 137/137 (100%) coverage
across all 8 product families** — confirmed by actually running the builder against the live
authoritative cohort (`backend/scripts/build_budget_normalized_product_rankings.py --dry-run`).

## Why this is internal

Reserved for a future personalized/higher-tier "given my budget, what should I open" capability.
It is deliberately not wired into any current public payload, API, or entitlement.

## Why current users only see "Coming Soon"

This is a delivery/monetization sequencing decision, not an analytical limitation — the ranking
itself is validated and production-ready; only its public exposure is withheld.

---

## Canonical budget bands (Phase 1A/7)

Preserved from the already-validated equal-spend research: **$25, $50, $100, $150, $250, $500**,
plus the dynamic **Full Market** anchor. Live coverage was re-verified against the frozen pinned
cohort; counts can differ from earlier research when prices move:

Live coverage from the V1-freeze dry run (`--price-as-of 2026-08-21`, 137 SKUs / 22 runs):

| Budget | Eligible | Ranked | Families | Median util. | Min util. |
|---:|---:|---:|---:|---:|---:|
| $25 | 36 | 36 | 2 | 0.8460 | 0.5160 |
| $50 | 41 | 41 | 3 | 0.9080 | 0.5764 |
| $100 | 58 | 58 | 4 | 0.9200 | 0.5193 |
| $150 | 77 | 77 | 5 | 0.9429 | 0.5185 |
| $250 | 106 | 106 | 7 | 0.9164 | 0.5088 |
| $500 | 131 | 131 | 8 | 0.9164 | 0.5009 |
| **Full Market ($1,350)** | **137** | **137** | **8** | **0.9731** | **0.5151** |

586 ranking rows in one publication. $150 admits **77**, not the 78 recorded against the earlier
2026-08-17 cohort — a genuine price movement between cohorts, not a contract change. Coverage
counts are cohort-dependent by nature and must be re-read from the current dry run rather than
quoted from this table.

No band was dropped as redundant — each admits a materially different, monotonically growing
cohort and family set, so each remains a meaningful, distinct answer to "what's best at roughly
$X."

## Full Market definition (Phase 1B–1D)

- **Rule:** `full_market_budget = ceil(max_eligible_sku_price / 50) * 50` — round the current
  maximum eligible SKU price UP to the next $50 increment.
- **Why $50, not $25 or $100:** on the current cohort, $25 and $50 increments produce the
  identical anchor ($1,350 either way — no coverage or capital-inflation difference), but $50 is
  less sensitive to small price jitter (a product needs to move up to $50, not $25, before the
  anchor changes at all). $100 was rejected: it inflates committed capital ~4.5x more than
  necessary ($1,400 vs $1,350) with no measured stability benefit.
- **Dynamic, not hard-coded:** implemented as `resolve_full_market_budget()`, which reads the live
  maximum eligible price every time it runs and stores `max_eligible_sku_price` +
  `full_market_rounding_rule` alongside the resolved `budget` in every row, so a future price
  movement crossing $1,350/$1,400 is reproducible and auditable, not silently inconsistent.
- **Tested:** unit tests cover stability within one bucket (max price moving $1,301→$1,340 does
  not change the anchor) and deterministic change across a boundary ($1,349→$1,350 vs
  $1,351→$1,400).

## Allocation rule (Phase 2)

`quantity = floor(target_budget / product_market_price)`, whole retail units only. Chosen over a
nearest-whole-unit tolerance search (Phase 2C Candidate B) because: it's the SAME rule the
already-validated equal-spend research used for its bands (continuity), it needs no
tolerance-tuning parameter, and it is trivially explainable ("as many as $X buys"). A product
priced above the target is recorded as ineligible (`quantity=0`, reason
`price_exceeds_budget`), never silently dropped or forced into a fractional unit.
`actualCommittedCapital`, `unusedCapital`, and `unusedCapitalPercent` are recorded explicitly on
every allocation, including eligible ones — unused capital is never treated as spent, invested, or
folded into the scored outcome distribution.

## Cross-format ranking semantics (Phase 4/F)

One budget-qualified rank means: *"Ranks this product against every other eligible modeled sealed
product whose whole retail units fit within this same spending ceiling, using Financial RIP V4
(computed on the real multi-unit outcome distribution) and Overall RIP V10."*

`comparison_scope_version = budget_constrained_whole_unit_cross_format_v1`. The pre-freeze value
`equal_committed_capital_cross_format_v1` is retained UNMUTATED in the engine as
`LEGACY_BUDGET_COMPARISON_SCOPE_VERSION_PRE_FREEZE` so any artifact carrying it keeps its original
meaning; no publication ever used it (the storage migration was never applied). The rank,
its cohort size, and its tier are computed together from the exact same ranked set and can never
describe different cohorts. Comparator: Overall RIP V10 (desc) → Financial RIP V4 (desc) →
chance-to-recover (desc, when present) → committed-capital closeness to target (asc) →
`sealed_product_id` (deterministic final tie-break) — structurally the same shape as the validated
Family Rank comparator, adapted with a capital-closeness tie-break specific to budget matching.

## Scoring chain (Phase 3)

For quantity Q of one SKU: build the REAL Q-unit outcome vector via
`build_stage1_product_distributions` (the same machinery Stage 1/2 production scoring uses — no
`single-unit metric × Q` approximation), add guaranteed-component value once per unit purchased
(Stage 2 composition preserved), then `build_financial_rip_v3` →
`project_financial_rip_v4_from_v3_payload` (mirrors production exactly — this is the same chain
verified by exact reconstruction in the prior equal-spend V4 research), then
`compute_overall_rip_v10(financial_v4_score, collector_appeal_score)` using the SAME Collector
Appeal score the set already carries (never recomputed per quantity).

## Future custom budget (Phase 7A)

The engine is not hard-wired to the six bands: `whole_unit_allocation(target_budget, price)` and
every downstream function accept an arbitrary positive `target_budget` — verified by a dedicated
test asserting a non-canonical budget ($180) resolves correctly. Precomputed snapshots cover the
standard bands + Full Market; the calculator itself is budget-agnostic and ready for a future
"user enters $X" flow without new scoring architecture.

## Internal production architecture (Phase 8)

- **Migration:** `backend/db/migrations/20260823193538_20260822213027_create_budget_normalized_product_rankings.sql`
  — `budget_product_ranking_snapshots`, `budget_product_ranking_rows`,
  `budget_product_ranking_latest`, and `publish_budget_product_ranking_snapshot(...)`. Mirrors the
  existing `pokemon_rip_stats_snapshots` publication pattern (one coherent snapshot, atomic
  publish, `ON CONFLICT` replace, row-count reconciliation check) with one deliberate difference:
  **no grant to `anon`/`authenticated` on any object** — only `service_role`. This is the opposite
  of the public `pokemon_rip_stats_snapshot_latest` table, which explicitly grants `SELECT` to
  `anon, authenticated`.
- **Authority coherence:** the publish RPC requires every row in one publication to share the same
  `market_date`/version triple as its snapshot, rejects duplicate `(product, budget, type)` keys,
  and rejects any ranked row missing its Financial/Overall score — failing the whole publish rather
  than constructing a partially-mixed snapshot.
- **Production migration identity:** the SQL was originally authored under version
  `20260822213027`. The authorized production apply occurred through the connected Supabase
  migration API, which recorded version `20260823193538` with the name
  `20260822213027_create_budget_normalized_product_rankings`. The repository migration was
  therefore renamed to
  `20260823193538_20260822213027_create_budget_normalized_product_rankings.sql` so local history
  matches production. The SQL content is unchanged. No ranking snapshot was published as part of
  that schema apply or this history-alignment change.
- **Builder:** `backend/scripts/build_budget_normalized_product_rankings.py`. Idempotent (same
  input → same output, verified by the engine's determinism tests); `--dry-run` (default-safe,
  writes only a local JSON) vs `--commit` (additionally publishes, pending migration application).

## Public leakage audit (Phase 8B / J)

Grep-verified: no reference to `budget_product_ranking_*` or
`backend.calculations.evr.budget_normalized_product_ranking` exists anywhere in
`frontend/lib/explore`, any `app/api/**/route.js`, or the existing public
`productFamilyRankings` contract (`product_family_rankings_service.py`, unmodified by this task).
The only frontend change is the locked "Overall" tab (below), which renders zero ranking data.

## Locked "Overall" UI (Phase 11)

`frontend/components/explore/ProductFamilyRankingsClient.jsx` — added a third nav pill ("Overall")
alongside the existing "Sets"/"Individual Products" toggle, and a new `OverallRankingLockedPanel`
component that renders exactly: **"Overall Product Rankings" / "Compare sealed products across
formats at a common spending level." / "Coming Soon"**. No sample data, no budget selector, no
mention of Index Plus/Premium/pricing/release date/methodology. Verified by a new contract test
asserting the absence of `budgetRank`, `budgetTier`, every dollar-band literal, and every
entitlement-name string. This file is confirmed untouched by the concurrent Codex/UI branch
(`feature/set-market-page-redesign`) — `git diff main --stat` for this file against that branch
shows no changes, so there is no integration conflict.

## Family Rank (Phase 12)

Unchanged. `product_family_rankings_service.py`'s comparator, population, and (from the prior
task) `familyTier` field are untouched by this task; the focused Family Rank regression modules
remain green.

## Deferred / not done (honest accounting)

- The post-implementation semantics audit was completed for the pinned 2026-08-21 cohort. It
  includes neighboring-anchor rank stability, utilization/rank correlation, dominance, retained
  cash, matched-capital, and Full Market diagnostics. Future cohorts still require monitoring;
  validation of one frozen cohort is not a promise that market drift can never change the result.
- The builder now records per-budget utilization diagnostics and timings in its local dry-run
  artifact. These diagnostics remain internal and are not part of any public payload.
- The migration is applied to the live database under production version `20260823193538`, but
  `--commit` publication has not yet been exercised end-to-end.
- `chanceToRecoverCapital` is populated from Financial RIP V3's canonical
  `true_win_probability` raw input and persisted in the internal ranking row. It is computed for
  the actual whole-unit strategy; unused cash is not passed into that metric.


---

# FINAL DATA CONTRACT (V1 FROZEN)

Migration `20260823193538_20260822213027_create_budget_normalized_product_rankings.sql`.

## `budget_product_ranking_snapshots`

`id`, `market_date`, `built_at`, `published_at`, `publication_status`, `ranking_method_version`,
`allocation_method_version`, `comparison_scope_version`, `financial_rip_version`,
`overall_rip_version`, `collector_appeal_version`, `eligible_cohort_count`, `cohort_fingerprint`,
**`pinned_price_as_of`**, **`full_market_budget`**, **`max_eligible_sku_price`**,
**`full_market_rounding_increment`**, **`full_market_rounding_rule_version`**, `diagnostics_json`,
`created_at`.

Unique on `(market_date, ranking_method_version, allocation_method_version)` — republishing the
same date/method REPLACES the row set rather than coexisting as ambiguous authority.

## `budget_product_ranking_rows`

`snapshot_id`, `sealed_product_id`, `set_id`, `product_family`, `target_budget`, `budget_type`,
`quantity`, `actual_committed_capital`, `unused_capital`, `unused_capital_percent`,
**`capital_utilization`**, `budget_rank`, `budget_cohort_size`, `budget_tier`,
**`financial_only_rank`**, `financial_rip_v4_score`, `overall_rip_v10_score`,
`collector_appeal_score`, **`chance_to_recover_capital`**, `product_market_price`, `price_as_of`,
`full_market_anchor`, `max_eligible_sku_price`, `full_market_rounding_rule`,
**`full_market_rounding_increment`**, **`full_market_rounding_rule_version`**,
`source_calculation_run_id`, `created_at`.

Primary key `(snapshot_id, sealed_product_id, target_budget, budget_type)` — the budget is part of
the identity, so a context-free product rank cannot be represented.

Enforced at the storage layer: `capital_utilization + unused_capital_percent = 1`,
`actual_committed_capital + unused_capital = target_budget` (within currency rounding),
`financial_only_rank <= budget_cohort_size`, Full Market anchor provenance is all-or-nothing, and
every row's `price_as_of` must equal the snapshot's `pinned_price_as_of`.

### Field mapping notes

* `source_publication_id` is not a separate column: the ranking's own publication identity is
  `snapshot_id`, and the *source* authority is `source_calculation_run_id` plus the snapshot's
  `pinned_price_as_of`. No duplicate field was added.
* `pinned_price_as_of` lives on the snapshot (authority is per publication) while `price_as_of`
  stays per row; the RPC asserts they agree, so the row-level value is a verifiable projection
  rather than a redundant copy.

---

# RANK AND TIER SEMANTICS

| Concept | Population | Ordered by | Public today |
|---|---|---|---|
| **Budget Rank** (primary) | All eligible SKUs at one budget ceiling, cross-format | Overall RIP V10 → Financial RIP V4 → chance-to-recover → budget utilisation → id | No (internal) |
| **Financial-only Rank** | The same budget cohort | Financial RIP V4 → id | No (internal audit only) |
| **Family Rank** | One canonical product family, all budgets irrelevant | Existing validated family comparator | Yes (unchanged) |

## Tier semantics — score tiers, not rank percentiles

Both **Family Tier** and **Budget Tier** are derived from a *score* via `assign_composite_tier()`.
They are **not** rank percentiles.

```
Family Rank: #7/22        <- position within the family
RIP Tier:    B            <- earned by the SCORE, independent of that position
```

`#7/22` does **not** imply `B`, and `B` does not imply any particular rank. A cohort in which every
product scores poorly still has a rank #1, and that row's tier is whatever its own score earns. The
two ideas must never be merged into a single "tier" meaning, and UI copy must not imply that one
determines the other.

## Why Budget Rank uses Overall RIP V10

The product proposition being ranked is the whole opening proposition — financial opening quality
*and* collector appeal. V10 (0.90 financial + 0.10 appeal) expresses that. A consequence, measured
and accepted: a financially dominated SKU can outrank its dominator on desirability. That is the
design, not a defect — which is exactly why `financial_only_rank` exists as the clean allocation
diagnostic.

## Dominance interpretation

**Do not block publication on V10 dominance inversions.** They are explained by Collector Appeal
(~98–100% of them at the freeze). Monitor **financial-only dominance** instead — the validated
baseline is 2 / 4,508 comparable pairs ≈ **0.044%**, worst observed 0.108%. The builder carries
`FINANCIAL_DOMINANCE_WARN_RATE = 1%` as an audit warning threshold, deliberately not a hard gate:
a small residual is expected because the four-metric dominance test is not a monotone function of
V4's six scored components.
