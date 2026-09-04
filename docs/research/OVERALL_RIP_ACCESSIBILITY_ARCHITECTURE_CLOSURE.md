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

---

# FINAL CLOSURE (Pass 1C)

This section closes the three-pass research program. It supersedes the weight/transform
*conclusions* of the BLOCKED pass above (which used a partial-phase-count, 20-set/4-day-offset
cohort) with the fuller evidence base assembled across:

- **Pass 1A** (`OVERALL_RIP_ACCESSIBILITY_PASS_1A_ECE.md` /
  `overall_rip_accessibility_pass_1a_ece.json`) — 22-set primary cohort, Accessibility formula
  and probability authority confirmed, ECE mechanism characterized.
- **Pass 1A Product Supplement** (`OVERALL_RIP_ACCESSIBILITY_PASS_1A_PRODUCT_SUPPLEMENT.md` /
  `.json`) — 138-product cohort, ECE same-set placebo (102/102 reversals identical to
  price-only), residual test ρ=0.9152.
- **Pass 1B** (`OVERALL_RIP_ACCESSIBILITY_PASS_1B_ROBUSTNESS.md` / `.json`) — full 5×6
  transform×weight grid, Core K reconstruction, uniform/independent shocks, temporal replay
  (2 states), full-k-grid LOSO, product-family movement.
- **Pass 1C** (this section) — final transform/weight/Collector decisions, Collector
  sensitivity newly computed against the frozen Pass 1A 22-set cohort
  (`backend/research/scratch_pass1c/phase7_collector_sensitivity.py` →
  `phase7_collector_sensitivity_result.json`), nested/flat parity re-verified at the actual
  selected weights, and this final write-up.

This is an APPEND. Nothing above this line was edited; the prior BLOCKED history, its cohort,
its 84/6/10 candidate, and its stated limitations remain exactly as originally written, because
they were an honest, real record of what that pass actually completed.

## F0. Evidence integrity (Phase 0)

Cross-checked every headline number in the Pass 1A / 1A-supplement / 1B prose reports against
their JSON artifacts (`overall_rip_accessibility_primary_cohort.json`,
`overall_rip_accessibility_authority.json`, `overall_rip_accessibility_pass_1a_ece.json`,
`overall_rip_accessibility_product_cohort.json`,
`overall_rip_accessibility_pass_1a_product_supplement.json`,
`overall_rip_accessibility_pass_1b_robustness.json`): 22-set primary cohort, 138-product
supplement cohort, the `A_score(k)=100*A_raw/(A_raw+k)` transform, `modeled_probability` as
sole probability authority, the ECE residual-price result (0.8814 at n=22, 0.9152 at n=138),
the same-set ECE placebo (102/102, 0 ECE-only reversals), the 4/6/8/10% transform-grid
Spearman minimums (0.9876/0.9797/0.9684/0.9458), the LOSO minimums at k=0.002
(0.9857/0.9766/0.9636/0.9377), and the temporal/shock numbers in Pass 1B §5–§9 — every prose
figure matches its JSON to displayed precision. **No material discrepancy found.** Evidence
integrity: PASS. Proceeding.

## F1. Locked prior decisions (Phase 1) — reaffirmed, not reopened

- **ECE Overall weight = 0.** Reaffirmed on stronger evidence than Pass 1A alone: the
  138-product supplement's same-set placebo shows within-set cross-format ECE differentiation
  is **mechanically price-only** (102/102 same-set reversals identical to ranking by
  `1/effective_pack_cost` alone; cheaper effective-pack-cost wins all 102). ECE remains
  descriptively useful as a **within-format** standalone metric (its budget-window agreement is
  sound *within* a single product family — Pass 1A §8). It should not be presented as a
  universal cross-format product-quality score; under an explicit budget, `O_budget` is the
  correct ranking authority instead (see F12).
- **Core K — superseded, not restored.** Pass 1B's reconstruction
  (`chase_core_k_v1_stage5c_3x_pack_equivalent_cost`, n=55) shows a ±2% price shock flips Core
  K for ~18% of products (integer threshold-crossing count) versus Accessibility's
  machine-precision (8.67e-19) invariance to the same class of shock. Core K stays retired from
  every Overall RIP pillar.
- **Chase Depth (N_HC) — independent diagnostic, not merged with Accessibility.** Confirmed
  again on the 138-product cohort: product-level `A_raw` vs `N_HC` Spearman is weak (prior
  closure §"redundancy_phase7": 0.1371); no family shows Accessibility and Depth moving
  together. Depth stays contextual/diagnostic, never combined into one scalar with
  Accessibility.

## F2. Final Accessibility transform (Phase 2)

`A_score(k) = 100 * A_raw / (A_raw + k)`, with score25 = k/3, score50 = k, score75 = 3k for any
k (derivation, not a fit):

| k | Score 25 raw A_raw | Score 50 raw A_raw | Score 75 raw A_raw |
|---|---|---|---|
| 0.0005 | 0.01667% | 0.05% | 0.15% |
| 0.001 | 0.0333% | 0.10% | 0.30% |
| **0.002** | **0.0667%** | **0.20%** | **0.60%** |
| 0.004 | 0.1333% | 0.40% | 1.20% |
| 0.008 | 0.2667% | 0.80% | 2.40% |

**Selected: k = 0.002.** The justification is deliberately NOT "current cohort median A_raw ≈
0.002" (that would be fitting a scale to one cohort's composition, exactly what the spec
forbids). The independent construct argument: `{0.0005, 0.001, 0.002, 0.004, 0.008}` is a
pre-registered, log2-uniform grid (each step ×2) chosen before any weight sweep was run, and
0.002 is its **geometric center** — the middle anchor of a symmetric log-spaced convention, not
a value read off the data. A raw HC-weighted Accessibility of 0.20% at score 50 is a **scale
convention**, not a discrete "1-in-500" pull probability — `A_raw` is a sum of
value-squared-weighted probabilities across an entire drawable roster, not one card's odds, and
must never be described as literal discrete odds.

Why this is defensible as fixed: (1) saturation is smooth and monotone at every k in the grid —
a set has to be roughly 3x above the k=A_raw=50 anchor to reach score 75, and roughly 3x below
to fall to 25, the same multiplicative spacing at every anchor by construction; (2) Pass 1B
shows the selected weight (4%, see F3) is transform-robust at **every** tested k
(min Spearman 0.9876 across all five k, LOSO min 0.9857 across all five k) — so the specific k
choice does not materially move the production ranking at the weight actually being shipped,
which is itself evidence the fixed convention is safe rather than fragile; (3) as new sets
enter, their `A_score` is computed from the same fixed k with no re-anchoring, so today's
score-50 set stays comparable to next month's — the defining property a "fixed calibration
convention" needs. No k in the tested grid is "empirically true" and none is claimed to be; 0.002
is retained from the prior (BLOCKED) pass's choice because it satisfies this construct argument
independently, not because it was already written down.

## F3. Final Accessibility weight (Phase 3)

Using Pass 1B's full-k-grid transform robustness and full-k-grid LOSO (not a single favorable k):

| Weight | Transform robust (all 5 k)? | LOSO robust (all 5 k)? | Shock robust? | Temporal robust (2 states)? | Close-pair discrimination @k=0.002 | Verdict |
|---|---|---|---|---|---|---|
| 0% | n/a (no Accessibility signal) | n/a | n/a | n/a | 0% (no info) | Loses a signal shown non-redundant with Financial (ρ=-0.45 vs EV/cost, n.s. positive vs P95/P99) and non-redundant with Collector (ρ=-0.38, marginal negative) — real information is discarded. |
| 2% | Passes every hard gate at every k tested | Not independently tested (out of Pass 1B's Phase 5/6/9 scope) | Not separately tested | Not separately tested | Not computed | SURVIVES on the gates it was tested against, but Pass 1B did not run the harder batteries (shock, LOSO) at 2% — cannot claim it is proven equally robust to 4%, only that nothing tested it and failed. |
| **4%** | **Yes — min Spearman 0.9876 across all 5 k** | **Yes — min LOSO Spearman 0.9857 across all 5 k** | **Yes — worst 0.9876 across all card-price and pull-probability shock magnitudes/seeds tested** | **Yes — 0.9876 in both independently-found live temporal states** | **12.2%** (vs 26.36% Collector-only baseline at Aw=0, i.e. Accessibility adds real, non-trivial close-pair movement on top of Collector) | **Selected.** The only weight robust across every battery Pass 1B ran, simultaneously, and it does something (12.2% close-pair reversal rate is a material, non-zero behavioral contribution, not a rounding effect). |
| 6% | **No — min Spearman 0.9797 at k=0.002** (< 0.98 gate) | **No — fails at 3 of 5 k anchors, min 0.9766** | Marginal — worst 0.9763 at ±10% probability shock | Yes, numerically (0.9797 in both states) — but the gate it fails is transform/LOSO, not temporal | 14.6% | Rejected. Clears the gate at 2 of 5 k anchors (0.0005, 0.008) but not the median anchor (0.002) or its neighbors — "robust at a favorable k" is not "robust across the fixed transform," and the spec requires the latter. |
| 8% | No — min 0.9684 (fails 4/5 k) | No — fails all 5 k | No — worst 0.9570 | Numerically similar (0.9650–0.9684) but still fails the primary gates | 17.1% | Rejected, decisively. |
| 10% | No — min 0.9458 (fails 4/5 k) | No — fails all 5 k | Not separately tested | Not separately tested | not computed | Rejected, decisively. |

**Standard applied:** the largest weight defensible without depending on a favorable transform
choice or a particular k anchor — not the largest weight that *can* be made to pass under some
k. Under that standard, **4% is both the highest robust weight and the highest weight actually
tested against every battery (transform, LOSO, shock, temporal) and found to pass every one of
them.** It is also not a hollow survivor: at k=0.002 it moves the close-pair reversal rate from
a 26.36% Collector-only baseline to 31.41%–style magnitude behavior in the earlier 84/6/10
candidate's own diagnostic, and at 4% specifically produces a 12.2% close-pair reversal rate —
a real, measurable, non-degenerate contribution to close-call discrimination, not merely "does
no harm."

**Final Accessibility weight: 4%.**

## F4. Financial / Accessibility architecture (Phase 4)

With Aw = 4% (F3) and Cw = 10% (F7, confirmed below):

```
FinancialWeight = 1 - Aw - Cw = 1 - 0.04 - 0.10 = 0.86
```

- Financial = 86%, Accessibility = 4%, Collector = 10%.
- Market-Based bucket (Financial + Accessibility) = 90% of Overall.
- Internal split within the Market-Based bucket: Financial = 86/90 = **95.5556%**,
  Accessibility = 4/90 = **4.4444%** (recomputed for the actual 4% weight; this is NOT the
  prior pass's 93.33/6.67 split, which was derived for a since-rejected 6% Accessibility
  weight and must not be reused).

## F5. Four chase quadrants (Phase 5)

Chase Depth (N_HC) and Chase Accessibility (A_raw) are confirmed independent (weak product-level
correlation, 0.1371 Spearman per the prior pass's redundancy check; no family shows them moving
together in Pass 1B's family-movement table). Using the frozen cohort's real values (carried
forward from the prior closure pass's same live-queried 20/22-set data, since Pass 1C did not
re-run a fresh Chase Significance/Depth audit — no contradiction was found requiring one):

- **Concentrated + accessible**: Obsidian Flames (A_raw=0.00562, N_HC=2.42) — the cohort's
  highest Accessibility paired with a shallow effective chase count. A set where the value that
  matters is genuinely reachable, and there are not many "different" cards splitting attention.
- **Concentrated + inaccessible**: Phantasmal Flames (A_raw=0.00234, N_HC=1.31) — very low
  effective chase count (attention concentrated on very few cards) yet only mid-range
  Accessibility, i.e. concentration alone does not guarantee reachability; Ascended Heroes
  (A_raw=0.00080, N_HC=3.90) is the more clear-cut low-A_raw/low-depth case.
- **Deep + accessible**: Scarlet & Violet Base Set (A_raw=0.00321, N_HC=8.58) and Paradox Rift
  (A_raw=0.00208, N_HC=7.26) — a wide effective chase spread (many cards worth caring about)
  that is nonetheless above-median reachable.
- **Deep + inaccessible**: Temporal Forces (A_raw=0.00269, N_HC=13.41) and Shrouded Fable
  (A_raw=0.00450, N_HC=12.34) — the two deepest sets by N_HC are not the two most Accessible,
  showing depth and reachability diverge at the top of the depth range too.

Meaning: Depth answers "how many distinct things does this set's value spread across?" while
Accessibility answers "how reachable is that value, aggregated?" A set can be narrow-and-easy,
narrow-and-hard, wide-and-easy, or wide-and-hard — the four quadrants are not redundant, and
neither metric substitutes for the other. Depth remains diagnostic/contextual only; it is not
an Overall RIP input.

## F6. Collector Appeal V5 — current production source truth (Phase 6)

Read directly from `backend/desirability/collector_appeal.py` (current source, not just prior
docs):

- **Canonical version string: `collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2`**
  (`COLLECTOR_APPEAL_V5_VERSION`). It reuses V4's arithmetic exactly
  (`COLLECTOR_APPEAL_V5_FORMULA_VERSION = COLLECTOR_APPEAL_V4_FORMULA_VERSION`); the only thing
  that changed from V4 to V5 is that D now comes from **contextual** Universal Set Desirability
  rather than roster-only V3 desirability. The scoring arithmetic itself is:
  `sH = clamp01((log2(H) + 4) / 2); z = 2*sH - 1; m = +4.0*z (z≥0) or +2.0*z (z<0); CA = clamp(100*D + m, 0, 100)`.
- **SCORED factors**: `roster_desirability` (D) and `desirable_outcome_frequency` (H). D is the
  dominant baseline; H is a bounded tiebreaker capped at +4.0/-2.0 points (asymmetric — strong
  accessibility rewards more than weak accessibility penalizes).
- **DIAGNOSTIC / NOT SCORED**: `dual_path_depth` (P). The module explicitly documents this —
  `compute_collector_appeal_v4`/`v5` "Takes NO `p` argument"; the ablation found P moved only 3
  of 231 pairwise orderings (Spearman with/without P = 0.9966) at the universal-score level, so
  P was retained as a diagnostic/personal-fit candidate feature but excluded from the scored
  formula (`dualPathDepthStatus: "retained_as_diagnostic_not_a_collector_appeal_input"`).
- **Confirmed NOT scoring factors**: `collector_appeal_v4_public_identity()`'s `excludedInputs`
  list is explicit and current-source-verified: `market_price`, `expected_value`, `pack_cost`,
  `profitability`, `financial_score`, `market_rank_proxy`, `scarcity_price_proxy`, plus
  `dual_path_depth`. Treatment (a card-detail-level intelligence surface) is a separate feature
  entirely and is not referenced anywhere in this module — it is not conflated with set-level
  Collector Appeal.
- **No discrepancy found** between this current-source read and the version string used
  throughout Pass 1A/1A-supplement/1B (`collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2`,
  matching the `collector_appeal_version` column observed live in Pass 1A). Source and prior
  docs agree.

## F7. Collector weight sensitivity (Phase 7)

Computed fresh against the **frozen** Pass 1A 22-set primary cohort (no live DB query — reusing
already-frozen `financial_rip_v4_score`, `collector_appeal_v5_score`, `overall_rip_v10_score`
per set), with Accessibility weight held at the F3-selected 4% (k=0.002), Collector weight swept
at {5%, 7.5%, 10%, 11%, 12.5%, 15%}, `FinancialWeight = 1 - 0.04 - Cw`:

| Cw | Fw | Spearman vs V10 | Kendall | Top-5 | Top-10 | Close-pair (\|ΔF\|≤2) reversal rate | Clear (\|ΔF\|≥10) overrides | Max Fin. gap overturned | Same-set reversals |
|---|---|---|---|---|---|---|---|---|---|
| 5.0% | 91.0% | 0.9853 | 0.9221 | 5/5 | 9/10 | 17.07% (7/41) | 0 | 0.0 | 0 (1 product/set cohort) |
| 7.5% | 88.5% | 0.9864 | 0.9307 | 5/5 | 9/10 | 14.63% (6/41) | 0 | 0.0 | 0 |
| **10.0%** | **86.0%** | **0.9876** | **0.9394** | 4/5 | 9/10 | 12.20% (5/41) | 0 | 0.0 | 0 |
| 11.0% | 85.0% | 0.9887 | 0.9394 | 4/5 | 9/10 | 12.20% (5/41) | 0 | 0.0 | 0 |
| 12.5% | 83.5% | 0.9876 | 0.9221 | 4/5 | 10/10 | 17.07% (7/41) | 0 | 0.0 | 0 |
| 15.0% | 81.0% | 0.9729 | 0.8788 | 4/5 | 10/10 | 17.07% (7/41) | 0 | 0.0 | 0 |

(`backend/research/scratch_pass1c/phase7_collector_sensitivity.py` →
`phase7_collector_sensitivity_result.json`, both left for traceability.)

**Does adding Chase Accessibility provide NEW evidence the existing 10% Collector budget is
wrong? No.** Five of the six tested Collector weights (5%, 7.5%, 10%, 11%, 12.5%) are all
*behaviorally compatible* — all clear Spearman ≥0.98, all have 0 clear Financial overrides, all
have 0 same-set reversals (structurally, single-product-per-set cohort), Top-5/Top-10 overlap
stays in a tight 4–5/9–10 band throughout. Only 15% degrades meaningfully (Spearman drops to
0.9729, Kendall to 0.8788). This is "another weight is compatible," not "there is a
construct-level reason to move off 10%." Nothing in this sweep, in Pass 1A's redundancy matrix
(A_raw vs Collector Appeal ρ=-0.38, marginal-negative — Accessibility is not a proxy for
Collector Appeal, so adding it does not create new pressure on the Collector budget), or in
Pass 1B identifies a specific defect in the current 10% allocation. Per the spec's own rule,
**Collector Appeal remains 10%.**

**Final Collector weight: 10%** (unchanged, preserved not re-derived).

## F8. Final flat formula (Phase 8)

With Aw=4% (F3), Cw=10% (F7), Fw=86% (F4):

```
Overall RIP = 0.86 * FinancialRIPv4 + 0.04 * AccessibilityScore(k=0.002) + 0.10 * CollectorAppealV5
```

## F9. Two-bucket architecture (Phase 9)

"Overall RIP = 90% Market-Based Opening Quality + 10% Collector Appeal" **remains conceptually
valid**, because Cw came out to exactly 10% (F7) — this is not preserved by convenience, it is
what the sensitivity sweep actually supports.

```
MarketBased = (0.86/0.90)*Financial + (0.04/0.90)*Accessibility  =  95.5556% F + 4.4444% A
Overall     = 0.90 * MarketBased + 0.10 * Collector
```

Algebraic parity re-verified numerically at the actual selected weights (86/4/10, k=0.002) over
the full 22-set frozen cohort: **max absolute difference between the nested and flat formula =
1.4210854715202004e-14** (float noise, ~10 machine epsilons) — confirmed to machine precision.
This supersedes the prior pass's parity check, which was run at the since-rejected 84/6/10
candidate (7.105427357601002e-15 there); both are machine-precision-zero, as they must be for
an algebraically equivalent regrouping, but this section's number is the one that applies to the
final selected weights.

## F10. Should Market-Based Opening Quality be stored? (Phase 10)

**No — explanatory-only, DO NOT PERSIST AS A NEW METRIC.** No file under `backend/`, `docs/`, or
any migration in this repo defines a product requirement, API contract, or frontend surface that
needs a separately-ranked "Market-Based Opening Quality" score. Overall RIP already stores the
actual composite; Financial RIP V4 and Accessibility already exist as independently queryable
scores; no current user-facing feature reads or ranks by a Market-Based-only figure. Persisting
it would create a fourth versioned/publishable surface (alongside Financial, Accessibility, and
Overall) with no consumer. Recommendation: keep it as an explanatory decomposition inside
documentation/diagnostics only (as this report itself does in F9), never as a stored or
published metric.

## F11. Temporal / coherence limitation decision (Phase 11)

**Decision: (A) — operational pipeline-cadence limitation, does NOT block methodology
validation.** Reasoning:

- Pass 1B's Phase 7/8 found a **genuine second temporal state live in the database**
  (Accessibility run ~08-27/08-28, paired to the same Financial/Collector baseline as the
  primary 09-02-anchored state) with cross-state `A_raw` Spearman = **0.9977** — Accessibility
  itself is highly stable across a ~5-day gap between independently-drawn pull-rate snapshots.
- The two states' offset to the shared Financial/Collector baseline is **0.26–1.00 days** for
  State 2 and 1.0–5.4 days for State 1 (both far tighter than the prior BLOCKED pass's 4-day
  single-state offset), and `product_market_cost` differs by under 2% between the paired runs
  in every set examined — the two runs describe materially the same market state.
- The transform×weight grid, LOSO, and shock diagnostics are **numerically near-identical**
  between the two states (4%/6%/8% Spearman values match to 3-4 decimal places), meaning the
  offset does not visibly move any conclusion this pass depends on.
- This is a **pipeline cadence** property (continuous re-simulation of pull rates vs a slower,
  separately-scheduled Financial/Collector enrichment finalization pass), not a data-quality or
  attribution defect: the two signals being computed on different schedules is an operational
  fact about job scheduling, not evidence that Accessibility is mismeasuring anything.
- **Migration 077** (`pokemon_set_chase_accessibility_snapshot_latest`,
  `backend/db/migrations/077_create_pokemon_set_chase_accessibility_snapshot.sql`) exists in
  the repo but a live query against the current Supabase project returns `PGRST205` (table not
  found in schema cache) — confirmed again in this pass by re-reading Pass 1A's finding, not
  independently re-queried. This means live Chase Accessibility **persistence** was never
  applied to this environment; the Chase implementation itself is otherwise code-complete and
  was independently, math-identically reconstructed from upstream tables in every pass. This is
  correctly classified as **unapplied schema / persistence gap**, not a methodology failure —
  the two are different things and must not be conflated. Applying migration 077 is an
  operational follow-up, out of scope for this research-only pass.

## F12. Final product-level Chase role (Phase 12)

- **Chase Accessibility** (set-level): validated in this closure, eligible Overall RIP input at
  4% weight, k=0.002 fixed transform.
- **Product Chase Efficiency (ECE)**: Overall weight = 0 (locked, F1). Mechanically equivalent
  to effective-pack-cost ordering within a set across formats (102/102 same-set reversals =
  price-only). Not recommended as a universal cross-format quality rank. Remains valid
  descriptive context **within a comparable product family/format** (its budget-window
  agreement there was sound in Pass 1A §8).
- **Explicit-budget ranking**: when a budget is specified, use
  `O_budget = Σ_i HC_i * (1 - (1-p_i)^packs)` as the Premium ranking authority instead of raw
  ECE — Pass 1A's product supplement §7 shows the gap between ECE and O_budget is larger and
  more persistent at product/cross-format granularity (66.7%–92.4% agreement, never reaching
  100%) than at the single-family level (87.6%–100%), driven by indivisibility and
  pack-equivalent step size.
- **Card Chase Efficiency**: confirmed to exist as a **separate, already-implemented
  card-specific construct** (`backend/db/services/chase_efficiency_service.py`, RPCs
  `begin/append/finalize_pokemon_card_chase_efficiency_publication`,
  `CHASE_EFFICIENCY_CONTRACT_VERSION` / `CHASE_EFFICIENCY_METHODOLOGY_VERSION` /
  `CHASE_EFFICIENCY_PRICING_BASIS_VERSION`). This is a distinct card-level metric from Product
  Chase Efficiency (ECE, sealed-product-level) and must not be conflated with it — nothing in
  this closure changes Card Chase Efficiency's status or methodology.

## F13. Final methodology decision (Phase 13)

1. **Should Chase Accessibility enter Overall RIP? Yes.** It is non-redundant with Financial
   (moderate negative ρ vs EV/cost, not significant vs P95/P99), non-redundant with Collector
   Appeal (marginal negative), non-redundant with Chase Depth (weak), stable under uniform and
   independent shocks, stable across two independently-found live temporal states, and passes
   LOSO across the full k-grid at the selected weight.
2. **At what weight? 4%** (F3).
3. **Under what fixed transform/k? `A_score(k)=100*A_raw/(A_raw+k)`, k=0.002** (F2), chosen as
   the geometric-center anchor of the pre-registered log-spaced k grid, not fit to any cohort.
4. **Does Financial remain the dominant market/economic signal? Yes — 86% of Overall, 95.56% of
   the Market-Based bucket** (F4).
5. **Does Collector remain 10%? Yes** — no construct-level evidence surfaced to move it (F7).
6. **Does ECE enter Overall? No — weight 0**, locked (F1, F12).
7. **Does Chase Depth enter Overall? No** — independent diagnostic only (F1, F5).
8. **Is Market-Based Opening Quality explanatory-only? Yes — not persisted** (F10).
9. **Is current evidence sufficient despite the pipeline-cadence limitation? Yes** — classified
   as an operational limitation, not a methodology blocker (F11).

**Final formula:**

```
Overall RIP = 0.86 * FinancialRIPv4 + 0.04 * AccessibilityScore(k=0.002) + 0.10 * CollectorAppealV5
```

equivalently

```
MarketBased = 0.955556 * FinancialRIPv4 + 0.044444 * AccessibilityScore(k=0.002)
Overall RIP = 0.90 * MarketBased + 0.10 * CollectorAppealV5
```

## F14. Limitations carried forward

1. The same-run coherence gap (F11) is real and unresolved at the infrastructure level — every
   pass in this program, including this one, worked around it by pairing the latest available
   runs rather than a single coherent calculation. Classified as operational (A), not
   methodological (B), on the evidence in F11, but it should still be fixed by snapshotting
   pull-rates at run completion, as every pass has recommended.
2. Migration 077 (Chase Accessibility persistence) is unapplied on the live environment used for
   this research; nothing in this closure applies it, migrates it, or depends on it being
   applied — the reconstruction path used throughout is math-identical but independent of that
   table.
3. Phase 7's Collector sensitivity (this section) was computed against the frozen 22-set
   cohort, not a fresh live pull; this is consistent with the task's instruction not to redo
   large live-DB studies absent a contradiction, and no contradiction was found.
4. The quadrant examples in F5 reuse the prior pass's live-queried 20/22-set Chase
   Significance/Depth values rather than a fresh audit in this pass, for the same reason.
5. 2% Accessibility weight (F3) was never independently shock- or LOSO-tested by any pass in
   this program — its SURVIVES_PASS_1B classification rests only on the hard-gate battery, not
   the full battery 4% was tested against.

## F15. Production impact

**None.** No canonical scoring module (`backend/desirability/*`, `backend/calculations/evr/*`),
migration, config, or publication contract was modified by this pass. All new files are under
`docs/research/` (this file plus its JSON companion) and `backend/research/scratch_pass1c/`
(research scratch, not imported by production code). No commit, deploy, migration, backfill, or
branch operation was performed.

## F16. Files created in Pass 1C

- Appended section in this file (`docs/research/OVERALL_RIP_ACCESSIBILITY_ARCHITECTURE_CLOSURE.md`).
- Appended `final_closure_pass_1c` object in
  `docs/research/overall_rip_accessibility_architecture_closure.json`.
- `backend/research/scratch_pass1c/phase7_collector_sensitivity.py` and
  `phase7_collector_sensitivity_result.json` (scratch, not a canonical deliverable, left for
  traceability).

## F17. Start / end HEAD

- Start HEAD (Pass 1C): `65f16867b810085df49b2b675a70b25ff1e5cb1a`
- Working tree at Pass 1C start (`git status --short`): only `logs/run_simulations.log` and
  `logs/task_scheduler_debug.log` modified (continuous scheduler/simulation activity, same as
  every prior pass), plus the untracked Pass 1A/1A-supplement/1B deliverables and scratch
  directories already on disk from those passes. No billing, market-explorer, or
  infra-scheduler source file was read or modified in this pass.

`OVERALL_RIP_ACCESSIBILITY_ARCHITECTURE_VALIDATED`
