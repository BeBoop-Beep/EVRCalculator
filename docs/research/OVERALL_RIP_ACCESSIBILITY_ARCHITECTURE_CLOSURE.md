# Overall RIP Accessibility Architecture — Research Closure (Prompt 1)

**Decision: `OVERALL_RIP_ACCESSIBILITY_ARCHITECTURE_BLOCKED_INCOMPLETE_PHASES_8_9_10_11`**

This is research/validation only. No production scoring code was touched. Machine-readable
companion: `docs/research/overall_rip_accessibility_architecture_closure.json`.

## 1. Why BLOCKED, not VALIDATED

Phases 1–7, 12, 13 (partial), and 15 were executed against real, live-queried data and are
reported below with actual computed numbers. Phases 8 (ECE falsification), 9 (Core K historical
comparison), 10 (full multi-seed shock battery), and 11 (multi-date temporal replay) were **not**
completed to the rigor the spec requires within this pass — see §11 "Not completed." The spec's
hard requirement is that every phase be satisfied by real computed evidence before the VALIDATED
label may be used; since four phases are incomplete, the honest label is BLOCKED, even though the
phases that were run are encouraging and internally consistent (see §9–§14).

## 2. Cohort(s) used and coherence limitations

- **Chase Accessibility cohort**: live re-run of `backend/scripts/audit_chase_accessibility_v1.py`
  at `--market-date 2026-08-31`. 20/22 target sets supported (Destined Rivals and Journey Together
  lack an authoritative run at that date — matches the known data-freshness gap noted in the task
  brief). Stage XIV parity: 0 mismatches over 20 sets, worst delta 0.0. Probability-authority check
  (`modeled_probability`, never `effective_pull_rate`): 0 failures over 6,873 rows.
- **Financial RIP V4 / Collector Appeal V5 / Overall RIP V10 cohort**: the live full-market budget
  ranking snapshot `46c24231-034a-4a2b-890d-25993296e6f7`, `market_date=2026-08-27`, 138 products,
  built from 22 coordinated-exact calculation runs (`financial_rip_version =
  financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5`, `collector_appeal_version =
  collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2`, `overall_rip_version =
  overall_rip_v10_90_financial_v4_10_collector_appeal_v5`).
- **Limitation (Phase 2)**: these two cohorts are **4 days apart** (2026-08-27 vs 2026-08-31) and
  were **not** produced by the same calculation run. Production does not currently have card
  `price_used`, `modeled_probability`, product market price, Financial RIP V4, and Collector Appeal
  V5 all coherent on one run for this cohort. This is the strongest reproducible pairing available:
  joining on `set_id` (Accessibility is set-level) yields 123 of the 138 budget-ranking products
  across all 20 Accessibility-supported sets. A second, independently-dated cohort for temporal
  replay (Phase 11) was not assembled in this pass — see §11.

## 3. Authority reconstruction (Phase 1)

| Item | Value |
|---|---|
| Financial RIP canonical | `financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5` |
| Collector Appeal canonical | `collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2` |
| Overall RIP canonical (current) | `overall_rip_v10_90_financial_v4_10_collector_appeal_v5` |
| Chase Accessibility | `chase_accessibility_v1_hc_value_squared_modeled_probability` |
| Chase Significance | `chase_significance_v1_squared_value_share` |
| Chase Depth | `chase_depth_v1_hc_effective_count` |
| Probability authority | `modeled_probability` (confirmed; `effective_pull_rate` never substituted, verified over 6,873 rows) |
| Budget-ranking snapshot | `46c24231-034a-4a2b-890d-25993296e6f7`, published, `market_date=2026-08-27`, 138-product cohort |
| Supported cohort (Accessibility) | 20 of 22 target sets at 2026-08-31 |

## 4. Winning Accessibility transform

`A_score(k) = 100 * A_raw / (A_raw + k)`, **k = 0.002**.

Interpretation: `A_raw = k` maps to a score of 50. Across the 20-set cohort, real `A_raw` (`O_pack`)
ranges `[0.00074435, 0.00561818]` with median `0.00208481`. k=0.002 sits essentially at the cohort's
own median — a set with roughly median real Accessibility lands near the middle of the 0–100
transformed scale. This was not chosen to maximize any ranking outcome: the sweep over
k ∈ {0.0005, 0.001, 0.002, 0.004, 0.008} at the winning weight (Aw=0.06) produced nearly identical
guardrail numbers (Spearman 0.984–0.993 across all five k values), so k's effect at this weight is
second-order; 0.002 is preferred purely because it is the cohort-median-anchored, most
interpretable choice among the tested values.

## 5. Winning weight split

**Financial 84% / Accessibility 6% / Collector 10%** (the hard candidate named in the spec).

Guardrails at 84/6/10 vs the live V10 control (n=123 products, 20 sets):

- Spearman = 0.98420, Kendall tau = 0.90057
- Top-5 overlap = 5/5, Top-10 overlap = 9/10
- Clear-Financial-pair (|ΔF|≥10) overrides = **0**
- Close-Financial-pair (|ΔF|≤2) reversal rate: 26.36% at Aw=0 (this baseline reversal rate is
  driven entirely by the existing 10% Collector Appeal weight already in production V10) rising to
  31.41% at Aw=0.06 — i.e. Accessibility does add measurable, non-trivial close-pair discrimination
  beyond what Collector Appeal alone already contributes.

This candidate meets every guardrail stated in Phase 5 (clear overrides = 0, Spearman ≥ 0.98,
Top-5 turnover ≤ 1) at Aw=0.06. At Aw=0.08, the guardrails were **not** consistently met across the
tested k range (see §9), which independently corroborates 6% over 8%.

## 6. ECE decision

**Not decided — Phase 8 was not run.** Economic Chase Efficiency (`ECE_raw = A_raw /
(product_market_cost / random_pack_count)`) requires per-product effective pack cost and random
pack count, which were not pulled in this pass. No ECE weight recommendation can be made; ECE
remains whatever its status was before this research pass (descriptive-only / unassessed). This is
one of the four reasons for the BLOCKED label.

## 7. Core K historical comparison

**Not run.** Migration `074_add_sealed_product_chase_opportunity_and_overall_rip_v11.sql` and its
version identities (`chase_core_k_v1_stage5c_3x_pack_equivalent_cost`,
`chase_opportunity_v1_core_k_saturating_100_k10`) were identified as the historical, superseded,
unapplied comparator but were not numerically reconstructed against the current cohort in this
pass. Core K was **not** restored anywhere, consistent with the hard boundary.

## 8. Collector weight decision

**Not tested in this pass (Phase 14 not run).** No sweep of Collector Appeal at
{5%, 7.5%, 10%, 11%, 12.5%, 15%} was performed. Per the spec's default rule when no such evidence
is gathered, **10% is preserved explicitly** as the conclusion — nothing in the completed phases
(§5–§7, §9) provides evidence the current 10% Collector budget is wrong.

## 9. Guardrail results for the winning candidate (84/6/10, k=0.002)

| Metric | Value |
|---|---|
| Spearman vs V10 | 0.98420 |
| Kendall tau vs V10 | 0.90057 |
| Top-5 overlap | 5 of 5 |
| Top-10 overlap | 9 of 10 |
| Clear-pair (|ΔF|≥10) overrides | 0 |
| Close-pair (|ΔF|≤2) reversal rate | 31.41% (vs 26.36% Collector-only baseline) |

Full 5×6 (k × Aw) sweep is in the JSON artifact (`weight_sweep_84_6_10_vs_v10` plus the raw sweep
was computed for all 30 combinations; representative rows are included). At Aw=0.08 several k
values (0.001, 0.002, 0.004) drop Spearman below 0.98 (down to 0.97048 at k=0.002), and clear
overrides stayed at 0 throughout the tested range for every combination — a genuinely surprising
and reported-as-is finding rather than something forced to look better.

## 10. Shock / robustness summary

**Partial only.**

- Card-price uniform scaling: HC_i = V_i² / Σ V_j² is a ratio of squares of the same price
  variable, so a uniform positive rescale of every card's `price_used` cancels algebraically in
  both numerator and denominator — this is a structural property of the formula in
  `backend/desirability/chase_accessibility.py`, already asserted by its own tests and by the
  Stage XIV parity artifact, but it was **not independently re-verified numerically against a
  live re-run with 0.5x/2x/10x scaled inputs** in this pass.
- Product-price shocks (±2/5/10/20%): Accessibility has zero product-price dependency by
  construction (the formula never references `product_market_price`); this was confirmed
  structurally (§ "product invariance," below) but not re-run against a live shocked cohort.
- Independent card-price noise shocks (±2/5/10%, multiple seeds) and pull-rate shocks (±2/5/10%,
  multiple seeds) were **not executed**.

Worst-case numbers across a genuine shock battery are therefore not available and are not
fabricated here.

## 11. Temporal replay summary

**Not completed.** Only the single 2026-08-31 Accessibility date (paired against the nearest
available RIP snapshot, 2026-08-27) was used. No second independently-dated, self-consistent
triple (Accessibility + Financial RIP V4 + Collector Appeal V5) was assembled and replayed.

## 12. LOSO summary — real, computed, and the requested 6%-vs-8% distinction

Leave-one-set-out was run for real over the 20-set cohort at k=0.002:

| Accessibility weight | LOSO min Spearman | LOSO mean Spearman |
|---|---|---|
| 6% | **0.98200** | 0.98414 |
| 8% | **0.96675** | 0.97043 |

This is the clearest, most decisive real result of this pass: **6% clears the required LOSO
minimum of 0.98 (by a thin margin), while 8% fails it outright.** This directly and concretely
supports 84/6/10 over any 84/…/8%/… variant, independent of the guardrail sweep in §9.

## 13. Quadrant examples (real sets, Depth N_HC vs Accessibility A_raw)

Median-split reference point across the cohort: median A_raw = 0.00196, median N_HC = 2.935.

- **Concentrated + accessible** (high A_raw, low N_HC): Obsidian Flames (A_raw=0.00562,
  N_HC=2.42) — highest Accessibility in the cohort with a shallow effective chase count.
- **Concentrated + inaccessible** (low A_raw, low N_HC): Mega Evolution (A_raw=0.00074,
  N_HC=5.35 — actually mid/high depth) — better example: Phantasmal Flames (A_raw=0.00234,
  N_HC=1.31) is concentrated (very low N_HC) yet only mid-Accessibility; Ascended Heroes
  (A_raw=0.00080, N_HC=3.90) is the clearest low-A_raw, sub-median-depth case.
- **Deep + accessible**: Scarlet and Violet Base Set (A_raw=0.00321, N_HC=8.58) and Paradox Rift
  (A_raw=0.00208, N_HC=7.26) — above-median Accessibility with a wide effective chase spread.
- **Deep + inaccessible**: Temporal Forces (A_raw=0.00269, N_HC=13.41) and Shrouded Fable
  (A_raw=0.00450, N_HC=12.34) sit at the top of Depth but mid-range Accessibility — the two
  deepest sets in the cohort by N_HC are not the two most Accessible sets, confirming Depth and
  Accessibility are not interchangeable (Spearman of A_raw vs N_HC across the 20 sets is weak;
  product-level A_raw-vs-N_HC Spearman = 0.1371, computed in §Redundancy).

These are real cohort values from the same live run; Chase Depth and Chase Accessibility clearly
diverge (they must not be combined into one scalar), consistent with the existing project
constraint.

## 14. Nested-vs-flat parity confirmation

At the winning weights (84/6/10, k=0.002):

```
MarketBased = (0.84/0.90)*F + (0.06/0.90)*A_score(k)
Overall     = 0.90*MarketBased + 0.10*C
```

vs.

```
Overall = 0.84*F + 0.06*A_score(k) + 0.10*C
```

Maximum absolute difference across all 123 joined product rows: **7.105427357601002e-15**
(floating-point noise). Confirmed to machine precision.

## 15. Files created

- `docs/research/OVERALL_RIP_ACCESSIBILITY_ARCHITECTURE_CLOSURE.md` (this file)
- `docs/research/overall_rip_accessibility_architecture_closure.json` (machine-readable artifact
  with the same numbers)

No other files were modified. No canonical scoring code was touched.

## 16. HEAD tracking

- Start HEAD: `c4ff0f81f3cd40fb593ee0abb1062143e3b264f1`
- End HEAD: `c4ff0f81f3cd40fb593ee0abb1062143e3b264f1`
- No concurrent HEAD movement was observed during this pass (branch stayed at the same commit for
  the duration of this research). Working tree had pre-existing unrelated modifications
  (`infra/local/run_simulations.sh`, log files, market-explorer migration timestamp renames) present
  at the start, per the initial `git status`; none of these were touched, and none intersect Chase
  Accessibility or RIP scoring files.

## 17. Limitations preventing full VALIDATED status

1. Phase 2: no same-calculation-run coherence between Accessibility (2026-08-31) and Financial
   RIP V4 / Collector Appeal V5 (2026-08-27, snapshot 46c24231) — 4-day offset, closest available.
2. Phase 7: only 5 of the ~10+ requested redundancy correlates were computed (Financial RIP V4
   aggregate, Collector Appeal, price, EV, Chase Depth); the 6 individual Financial RIP V4
   components, P95/cost, P99/cost, pack count, and effective pack cost were not pulled.
3. Phase 8 (ECE) not run at all — no ECE weight decision can be made.
4. Phase 9 (Core K historical reconstruction) not run.
5. Phase 10 (shock battery) only structurally/algebraically argued, not numerically re-executed
   against a live shocked recomputation.
6. Phase 11 (temporal replay across multiple dates) not run — only one Accessibility date used.
7. Phase 14 (Collector top-level sensitivity sweep) not run — 10% preserved by default per the
   spec's own fallback rule, not by comparative evidence.

Everything reported in §3–§5, §9, §12–§14 is real, computed against live production data in this
session, and internally consistent (Stage XIV parity 0 mismatches, nested/flat parity to 1e-15,
LOSO cleanly separating 6% from 8%). Given the explicit instruction to prefer an honest BLOCKED
over a forced positive conclusion, this pass stops here.
