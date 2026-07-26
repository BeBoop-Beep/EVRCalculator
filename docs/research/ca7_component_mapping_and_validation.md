# CA7 Opening Desirability — Component Mapping & Five-Set Validation

**Purpose.** Prove exactly what CA7 (Collector Appeal, the 10% term of Overall
RIP) contains, that it is price-independent, that Universal Set Desirability is
applied to it exactly once, and how a missing CA7 degrades. Includes a five-set
deterministic validation computed from the production functions.

**Version identity (pinned constants).**

| Concept | Constant | Value |
|---|---|---|
| CA7 production version | `COLLECTOR_APPEAL_VERSION` | `collector_appeal_ca7_v1` |
| CA7 formula version | `CA7_FORMULA_VERSION` | `collector_appeal_ca7_bounded_bonus_v1` |
| CA7 lambda (pre-registered, not fitted) | `CA7_PRODUCTION_LAMBDA` | `0.50` |
| Dual-Path Depth version | `DUAL_PATH_DEPTH_VERSION` | `dual_path_depth_v1` |
| Universal Set Desirability version | `UNIVERSAL_SET_DESIRABILITY_VERSION` | `universal_set_desirability_v3` |
| Missing-data policy | `MISSING_DATA_POLICY_VERSION` | `collector_appeal_missing_data_v1_none_never_zero` |
| Overall RIP version | `OVERALL_RIP_V4_VERSION` | `overall_rip_v4_90_financial_10_ca7` |

**The formula.** `CA7 = D + λ·P·(1 − D)` on the 0–1 scale (stored ×100), with
`λ = 0.50`. Bounds hold for every `D, P ∈ [0,1]`:

- `P = 0 → CA7 = D` (absent dual-path structure costs nothing),
- `P = 1 → CA7 = D + 0.5·(1 − D)` (a bonus of at most half the remaining headroom),
- `∂CA7/∂D = 1 − λP > 0` (desirability always dominates structure).

Source: [`backend/desirability/collector_appeal.py`](../../backend/desirability/collector_appeal.py)
(`bounded_bonus_appeal`, `compute_collector_appeal`).

---

## 1. Component mapping

| CA7 concept | Source field / service | Formula or weight | Price-independent? | Simulation-dependent? | Coverage |
|---|---|---|---|---|---|
| Universal roster desirability (**D**) | `universal_set_desirability_service` → `universalSetDesirability.score`; consumed as `rosterDesirability.score` in `collector_appeal_service._build_set_payload` | Fan-popularity + roster depth, 0–100, fixed-anchor. Enters CA7 as the base term `D`. | **Yes** — excludes scarcity/treatment/price by construction | **No** — needs no pack simulation | All sets with `desirabilityCoverage = full` |
| Obtainable desirable cards / reachable-and-chaseable structure (**P**, Dual-Path Depth) | `collector_appeal.compute_dual_path_depth(subjects)` → `openingExperience.dualPathDepth.rawValue` | `P = Σ q_s · access(p_easiest_s) · scarcity(p_rarest_s)`; enters CA7 as `λ·P·(1−D)` | **Yes** — pull-probability transforms only, no price | **Yes** — needs the modeled pack/pull rate model | Sets with a modeled pull rate AND ≥1 desirable modeled subject |
| Chase intensity / elite scarcity (**M\***) | `factorized_opening_appeal.compute_m_star_m1(subjects)` → `openingExperience.chaseAppeal.eliteScarcity` | `M* = 1 − access(p_rarest)`, a scarcity anchor; surfaced as a **signal** and as the Chase Appeal metric `D·M`. **Not** a direct CA7 term | **Yes** — scarcity anchor, no price | **Yes** — needs the modeled pull rate model | Same as P |

**Accessible-path fields** (reachable printings): `access_transform(p)` anchors
(1-in-10 → 1.0, 1-in-1000 → 0.0), summarized in `P` via `reachable_access` per
subject.

**Elite chase / scarcity-intensity fields**: `scarcity_transform(p) = 1 −
access(p)`, summarized in `P` via `elite_scarcity` per subject and reported
standalone as `M*` / `chaseAppeal.eliteScarcity`.

**Why the compact `openingDesirability.components` uses D / P / M\*.** The merged
`openingExperience` object carries D (via `universalSetDesirability`), P (via
`dualPathDepth.rawValue`) and M\* (via `chaseAppeal.eliteScarcity`). A / M\* are
approximately one axis (`access = 1 − scarcity` at shared anchors), so the honest,
non-redundant three-way breakdown a card can render is **roster (D)**, **dual-path
reach (P)**, and **elite scarcity (M\*)**. The projection in
[`public_rip_contract_v4.py`](../../backend/desirability/public_rip_contract_v4.py)
maps them to `universalRoster` / `obtainableDesirableCards` / `chaseIntensity`.

---

## 2. Universal Set Desirability is applied exactly once

- `D` enters CA7 **once**, as the base term of `CA7 = D + λ·P·(1−D)`.
- Overall RIP = `0.90 · Financial RIP + 0.10 · CA7`. Financial RIP is
  Profit/Safety/Stability only — **no desirability term** — so D reaches Overall
  RIP solely through CA7. See `compute_overall_rip` and `compute_financial_rip`
  in [`weighted_rip.py`](../../backend/desirability/weighted_rip.py).
- When CA7 is missing, Overall RIP is **unavailable** and deliberately does **not**
  fall back to Universal Set Desirability — substituting it would both double-count
  D and mix two constructs in one column.
- Universal Set Desirability is *also* published as its own standalone metric
  (`universalSetDesirability`, all-set rank of ~135). That is a **separate
  surface**, not a second application inside the score.

## 3. Why no price / set value enters CA7

Every CA7 input is a fan-popularity score (D) or a pull-probability transform
(P, M\*). `collector_appeal_payload.excludedInputs` pins the exclusion list:
`market_price, set_value, expected_value, profit, treatment_prestige,
any_market_outcome`. A unit test walks the module AST to assert no weight-search
loop and no market field is referenced.

## 4. Missing-data behaviour & cohort eligibility

- **Missing input → `None`, never `0`** (`MISSING_DATA_POLICY`). A set with no
  pull model returns `dualPathDepth = None → CA7 = None`, not a zero that would
  sort it against real scores.
- **A set missing CA7 keeps Financial RIP and Universal Set Desirability**, but
  receives **no Overall RIP** (`overallRip.absoluteScore = null`,
  `status = unavailable_missing_input`). It is flagged out of the Overall ranked
  denominator (`cohort.overallRanked.missingCa7SetIds`), never silently dropped
  and never given a fabricated Overall RIP.
- **Mixed CA7 versions fail closed**: `audit_overall_ranked_cohort` sets the
  cohort `status = integrity_error` if two CA7 formula versions appear in one
  Overall ranking, because two Overall RIPs under different CA7 formulas are not
  comparable.

---

## 5. Five-set validation (deterministic, from production functions)

Computed directly from `compute_collector_appeal` (CA7 @ λ=0.50),
`compute_chase_appeal` (D·M\*), `compute_financial_rip` (60/25/15) and
`compute_overall_rip` (0.90/0.10). **These are formula outputs over
deterministic representative inputs — not live Supabase set data.** Inputs: D on
0–100, P and M\* on 0–1; the financial pillars are chosen per profile.

| Profile | D | P | M\* | Financial RIP (60/25/15) | **CA7** | Chase Appeal (D·M\*) | **Overall RIP** (0.9·Fin + 0.1·CA7) |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1. Elite roster + elite chase structure | 95 | 0.80 | 0.85 | 50.20 | **97.00** | 80.75 | **54.88** |
| 2. Elite roster + weak obtainability | 92 | 0.10 | 0.90 | 37.50 | **92.40** | 82.80 | **42.99** |
| 3. Moderate roster + strong accessibility | 60 | 0.55 | 0.20 | 45.80 | **71.00** | 12.00 | **48.32** |
| 4. One-chase concentrated | 70 | 0.25 | 0.95 | 46.60 | **73.75** | 66.50 | **49.32** |
| 5. Broad / deep roster | 80 | 0.70 | 0.50 | 39.50 | **87.00** | 40.00 | **44.25** |

**Reading the results.**

1. **Elite + elite chase** — high D with strong dual-path P lifts CA7 to 97.0
   (near ceiling); CA7 adds the full 10% headroom to Overall (54.88), and Chase
   Appeal is high because M\* is also high. The "both paths" set scores best on
   every desirability axis, as intended.
2. **Elite roster + weak obtainability** — D is high but P is low (0.10), so
   CA7 (92.40) barely exceeds D: the bonus term `λ·P·(1−D)` is small. Chase
   Appeal stays high (elite scarcity), but Overall RIP (42.99) is driven mostly
   by the weaker Financial RIP — structure cannot rescue thin obtainability.
3. **Moderate roster + strong accessibility** — mid D, decent P, low M\*.
   CA7 (71.0) sits well above D=60 because P is meaningful; Chase Appeal is low
   (12.0) precisely because elite scarcity is low. Confirms CA7 rewards reach
   while Chase Appeal separately penalizes the lack of scarcity.
4. **One-chase concentrated** — one elite chase (M\*=0.95) but shallow dual-path
   P=0.25. CA7 (73.75) reflects the modest structural bonus over D=70; Chase
   Appeal is high (66.5). Shows CA7 and Chase Appeal are distinct: the chase set
   is "chasey" but not deeply dual-path.
5. **Broad / deep roster** — high D, strong P, average M\*. CA7 (87.0) is high
   from roster + reach; Chase Appeal (40.0) is only moderate. A deep, reachable
   set reads as high Collector Appeal without needing extreme scarcity.

**Invariants demonstrated:** CA7 ≥ D in every row (bonus never subtracts);
CA7 = D exactly when P = 0 (not shown, holds by construction);
Overall RIP always between Financial RIP and a 10% pull toward CA7; Universal
roster desirability (D) appears once (inside CA7), never re-added.

---

## 6. Live re-validation (user-run; not executed here)

Numbers above are deterministic formula outputs. To validate the SAME quantities
on live production sets, run the targeted commands in the continuation summary
(Explore rankings + one Ascended Heroes set-page build) and inspect, per set:
`publicRipContractV4.openingDesirability.{absoluteScore, version, components}`,
`publicRipContractV4.overallRip.components.openingDesirability.contribution`,
and confirm `universalSetDesirability` is present and equal to
`openingDesirability.components.universalRoster`.
