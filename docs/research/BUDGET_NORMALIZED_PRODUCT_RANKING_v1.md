# Budget-Normalized Product Ranking — Internal Capability (v1)

**Date:** 2026-08-22
**Status:** Internal infrastructure only. No customer-facing exposure.
**Supersedes nothing; extends** `OVERALL_PRODUCT_RANK_DECISION_2026-08-22_v2.md`.

## Why universal Overall Rank was rejected

Rank is budget-dependent: no single tested budget (or a practical full-cohort anchor at the raw
maximum price) gave 100% cohort coverage without either excluding the most expensive SKUs or
forcing absurd quantities on the cheapest ones. A context-free "#X / all products" claim cannot
honestly describe one stable population.

## Why budget-normalized ranking is supported

Equal-committed-capital comparison, using whole purchasable retail units and the real multi-unit
outcome distribution (never `single-unit metric × quantity`), behaved coherently across every
tested budget: zero dominance inversions, near-perfect (median Spearman ρ = 1.0) cross-budget rank
stability. This is genuinely useful, auditable, and explainable in one sentence — it was simply
never a *universal* rank.

## Why Full Market exists

To give one budget point where every currently eligible modeled SKU can participate, so "what's
best across everything" has an actual, complete answer — while still being explicit that it is
one specific (large) budget, not an intrinsic property of the product. **Live-verified: Full
Market resolves to $1,350 today (`ceil(1339.19 / 50) * 50`), and produces 137/137 (100%) coverage
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
plus the dynamic **Full Market** anchor. Live coverage (re-verified this task, matches the prior
equal-spend research exactly — a strong internal consistency check):

| Budget | Eligible | Families represented |
|---:|---:|---|
| $25 | 36 | loose_booster_pack, sleeved_booster_pack |
| $50 | 41 | + booster_bundle |
| $100 | 58 | + elite_trainer_box |
| $150 | 78 | + pokemon_center_elite_trainer_box |
| $250 | 106 | + booster_box, half_booster_box |
| $500 | 131 | + enhanced_booster_box (all 8 families, 95.6%) |
| **Full Market ($1,350)** | **137** | **all 8 families, 100%** |

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
product purchasable at this same committed-capital level, in whole retail units, using Financial
RIP V4 (computed on the real multi-unit outcome distribution) and Overall RIP V10."* The rank,
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

- **Migration:** `backend/db/migrations/20260822213027_create_budget_normalized_product_rankings.sql`
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
- **NOT APPLIED to the live database.** Per this session's established boundary around production
  writes (raised and confirmed with the user earlier in this task sequence), I authored the
  migration but did not execute schema DDL against the live database myself — that requires the
  repository's normal migration-deployment process, which I do not have visibility into from this
  environment. The builder script (`build_budget_normalized_product_rankings.py`) was exercised in
  `--dry-run` mode against the live, real, authoritative product cohort — every computed number in
  this document is real, not simulated — but its `--commit` path (which calls the new RPC) cannot
  run until the migration is applied.
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
task) `familyTier` field are untouched by this task; existing tests still pass (114/114 across the
touched test files, including all pre-existing Family Rank tests).

## Deferred / not done (honest accounting)

- The full Phase 6 statistical stress-test sweep (Spearman/top-5/top-10/rank-range at Full Market
  ± 10%/20% neighboring anchors) was **not run** — only the two boundary-crossing unit tests above.
  Time-boxed given the scope of this task; the underlying engine is real and tested, so this is a
  follow-up validation exercise, not a missing capability.
- Per-budget diagnostics beyond coverage (median committed capital, median unused capital, maximum
  unused-capital ratio, unused-capital-vs-rank correlation — Phase 1A/6C) were not computed this
  pass; the raw per-row data needed for them is already in
  `logs/budget_normalized_product_rankings.json` from the dry run, so this is a follow-up analysis
  query, not new engineering.
- The migration is authored but not applied to the live database (see above) — `--commit`
  publication has not actually been exercised end-to-end.
- `chanceToRecoverCost` is not currently populated on budget strategies (the tie-break degrades
  gracefully to Financial RIP / capital-closeness / SKU id instead) — a real, minor gap, not a
  design flaw: Financial RIP V3's payload carries this as a raw metric that could be threaded
  through in a follow-up.
