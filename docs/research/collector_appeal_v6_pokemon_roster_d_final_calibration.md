# Pokémon Roster Desirability — Final Calibration Research Pass

Status: **RESEARCH ONLY. No production writes, no pointer cutover, no model mutation.** Frozen control `pokemon_collector_appeal_v6_generalized_roster_frequency` / `0efa3c8f-918d-49d7-ad5e-3ae37278058f` untouched throughout. Cross-domain architecture (Candidate B1, λ_trainer=0.15) and rejection of the current C4 mass formula are treated as locked, not re-litigated.

## Summary of outcome

Four structurally distinct Strength candidates and a bounded-breadth combination were tested against the full pre-registered falsification battery. All of them hit the **same structural wall**: the frozen C3B percentile-based Subject Appeal input is itself compressed near the ceiling for the top handful-to-dozen Pokémon subjects in the overwhelming majority of real sets, leaving too little usable dynamic range for any fixed-anchor, cohort-independent Strength function to differentiate strong sets from each other — regardless of whether Strength is defined as a mean, a weighted sum, or a wider geometric-decay window. This is a property of the input data, not of the combination formula, and it cannot be fixed by adjusting λ within the pre-registered family (0.10–0.25).

**Decision: `V6_POKEMON_ROSTER_CALIBRATION_BLOCKED`** — see Section 9 for the exact unresolved issue.

## Phase 1 — Strength candidates tested

| Candidate | Definition | Median | p10 | p90 | Spread (p90-p10) | Issue |
|---|---|---|---|---|---|---|
| S1 top-3 mean | mean of 3 strongest subjects | 98.60 | 94.80 | 99.61 | 4.8 | severely ceiling-compressed |
| S2 top-5 mean | mean of 5 strongest | 97.20 | 92.80 | 99.20 | 6.4 | severely ceiling-compressed |
| S3 weighted headline (mean-form) | fixed weights [.35,.25,.20,.12,.08] over top-5, **as a weighted mean** | 97.94 | 94.20 | 99.42 | 5.2 | ceiling-compressed; **also failed monotonicity** (see below) |
| S4 threshold profile | top1 + bonus for 90+/80+/70+ counts | 100.00 | 100.00 | 100.00 | 0 | degenerate — saturates for every set in the cohort |

**Critical defect found and fixed in S3-style candidates**: a *mean*-based (or mean-like-normalized) top-K strength function is **not monotonic under addition of a new positive-but-weaker subject** whenever the set has fewer than K subjects already qualifying. Concretely: `strength([100]) = 100`, but `strength([100, 52]) = 76` under a plain top-K-mean — adding a fourth-string, barely-desirable Pokémon to a roster anchored by one iconic card *lowers* its score. This directly violates the "adding any positive subject cannot lower D" requirement and was caught only by the explicit Phase 4 archetype `1×100 + 4×52`, which the earlier calibration pass did not include. **This is the single most important defect this research pass found**, and it rules out every mean-based Strength definition in the pre-registered family (S1, S2, S3-as-mean) regardless of calibration constant.

**Fix applied**: reformulate Strength as an **additive, non-negative weighted sum** over the top-K positive subjects (`Σ w_i·(appeal_i−50)/50`, fixed descending weights, mapped through a saturating transform), never a division/average. This guarantees monotonic non-decrease under any addition of a positive subject (new terms can only add). Verified: `strength([100]) = 74.78`, `strength([100,52,52,52,52]) = 75.71` (higher, correctly monotonic) under this corrected form.

## Phase 1b — Why widening the Strength window does not solve differentiation

Having fixed monotonicity, the remaining problem is dynamic range. Widening the additive-strength window from top-5 to top-15 (geometric weight decay, still additive/monotonic) was tested to see if it recovers usable spread:

| Window | Raw-sum p10 | Raw-sum p90 | Spread as % of theoretical max |
|---|---|---|---|
| top-5, weights [1.0,.6,.4,.25,.15] | 2.14 | 2.39 (max possible: 2.40) | 90–99% of max |
| top-15, geometric decay 0.8 | 3.59 | 4.61 (max possible: 4.82) | 74–96% of max |

Both windows show the same pattern: **the large majority of real sets already achieve 75–99% of the theoretical maximum raw strength**, regardless of window width. This means the compression is not an artifact of using too small a K — it persists even when the window is tripled. The root cause: `final_card_collector_appeal` for Pokémon subjects is built on a **percentile rank** of desirability (`backend/desirability/composite.py`), and popular, frequently-reprinted Pokémon (Pikachu, Charizard, Mewtwo, Eevee, legendaries, etc.) recur across dozens of sets and reliably occupy the top percentiles wherever they appear. As a structural consequence, **most sets' top-5-to-20 subjects are already near the percentile ceiling**, because most sets happen to include several of these perennially-popular names. There is very little genuine cross-set variance left at the "how good is this set's headline roster" level once you're working from percentile-transformed inputs — the percentile transform itself has already consumed most of the discriminating signal by construction.

## Phase 1c — Why this can't be patched with λ alone

Given a saturated Strength (typically landing 85–95 after correction), remaining headroom `(100−S)` for Breadth to act within is only 5–15 points. Testing the full pre-registered λ family (0.10, 0.15, 0.20, 0.25) against the archetype battery confirms this: the 5-elite(95) archetype only moves from D=88.63 (λ=0.10) to D=89.34 (λ=0.25) — a 0.7-point range across the *entire* pre-registered λ family. No choice of λ within the locked, non-grid-searched range can meaningfully restore differentiation once Strength itself has consumed nearly all the available headroom via ceiling compression.

## Phase 4 — Synthetic falsification (corrected additive Strength + bounded Breadth, λ=0.15)

`backend/artifacts/collector_v6_redesign_research/` — all 16 archetypes computed. Representative results:

| Test | Result |
|---|---|
| `1×100` vs `1×100+4×52` | 74.78 → 75.71 (monotonic ✅, fixed) |
| `5×80` vs `5×80+60×50` (neutral-add) | 81.39 → 81.39 (exactly equal ✅) |
| `5×95` vs `5×95+1×60` | monotonic non-decrease ✅ |
| `3×98` vs `4×98` (genuinely new elite) | 86.71 → 88.81 (correctly rewarded ✅) |
| `60×55` vs `3×98` (broad-weak vs narrow-elite) | 57.39 vs 86.71 — **broad weak does NOT beat narrow elite** ✅ |
| n mediocre(65) needed to reach 5×elite(95)=88.87 | **no n up to 600 reaches it** — breadth can no longer overpower a genuinely elite narrow roster at any tested scale ✅ |

**All hard falsification requirements from the prior audit are satisfied** by the corrected additive-Strength + bounded-Breadth formula. This is real progress: the basket-size-dominance defect and the mean-dilution defect are both fixed. The blocker is differentiation, not falsification.

## Phase 5 — Differentiation / compression (the actual blocker)

Population run at λ=0.15, corrected additive Strength (top-5, weights [1.0,.6,.4,.25,.15], saturation constant C=1.5), Breadth (threshold 65, exponent 1.3, saturation 8):

| Metric | Corrected formula | Rejected old C4 model | Target/concern |
|---|---|---|---|
| D range | 78.91 – 91.31 | ~0 – 100 | too narrow |
| SD | 1.45 | 11.86 | 8× less spread |
| unique values @ 1dp | 35 / 128 | (not measured, but old model spans full range) | too many ties |
| sets ≥99 | 0 | — | — |
| sets ≥90 | 89 / 128 | — | 70% of the cohort within 1.31 points of the max |

This fails the Phase 5 requirement directly: **"strong sets retain useful differentiation"** and **"scores do not collapse against the upper bound."** 89 of 128 sets (70%) land within a 1.3-point band near the top. This is not a minor tuning gap — it means the corrected formula, as calibrated, cannot meaningfully rank the majority of the cohort against each other, even though it correctly passes every pairwise falsification test.

## Phase 6 — Matched-count / matched-appeal retest

Re-running the decisive matched-appeal test from the prior audit with the corrected formula shows the extreme swings (Ascended Heroes vs. Celebrations, 56-point gap; Paldean Fates vs. Emerging Powers, 75-point gap) are eliminated — but only because *everything* is compressed into a narrow band, not because the formula now discriminates real quality differences well. `Spearman(D_new, groupCount) = 0.9967` — barely different from the old model's 0.9989 — because within the compressed 79–91 band, tiny residual variation still happens to correlate with count (the same population-level confound flagged in the prior audit persists; it was never fully resolved by any tested architecture).

## Phase 9 (partial) — F parity proof

`F` (generalized desirable frequency) is defined entirely over **card-level** `final_card_collector_appeal` (unchanged — C3B was never touched by this research) and modeled pull probability; it does not consume set-level `D`. Verified directly against the frozen C4 artifact: all 22 modeled sets retain their existing `F` values unconditionally, since nothing in this research pass alters any card-level score. **0 differences, 0 membership changes** — this holds regardless of how the D_pokemon calibration question is ultimately resolved, and does not need to be revisited once a Strength+Breadth formula is eventually accepted.

## Phases 9 (Trainer shadow) / 11 (C5 reconstruction)

**Not run.** Both require an accepted `D_pokemon` to build on top of (`D_final = D_pokemon + (100-D_pokemon)*0.15*(D_trainer/100)`, then C5's D/F combination). Since no calibration in this pass reached an acceptable differentiation profile, running these against a rejected `D_pokemon` would not produce a meaningful result and was skipped per the task's own gating logic (Phase 9's instruction to proceed only "after selecting the best corrected D_pokemon").

## Files produced

- `docs/research/collector_appeal_v6_pokemon_roster_d_final_calibration.md` (this file)
- `docs/research/collector_appeal_v6_pokemon_roster_d_final_recommendation.md` (decision + path forward)
- `backend/artifacts/collector_v6_redesign_research/pokemon_D_corrected_128set.json` (corrected-formula 128-set results)
