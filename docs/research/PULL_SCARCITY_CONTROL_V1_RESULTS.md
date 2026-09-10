# Pull Scarcity role, redundancy, and validation-control research

Status: frozen research decision. Construction used no market-price field. The database
was read only, no production model was changed, and no Collector Appeal formula was
changed.

## Executive result

Exact card-variant pack-presence probability is a useful structural diagnostic and a
necessary common control for later price validation. It is not supported as intrinsic
Collector Appeal. Scarcity cannot create subject preference, simple multiplication has
already failed, and scoring the same probability again would overlap the F and Chase
paths in Overall RIP.

The reproducible snapshot covers 34 current calculation-run authorities and 7,620
modeled variant rows. All 7,620 rows satisfy both authority identities:
`p = pack_presence_count / simulation_count` and `p = 1 / effective_pull_rate`.
7,615 rows map to a canonical card; five retain exact variant/run identity but lack the
canonical bridge. Twenty-two sets have frozen generalized F and pass Chase
Accessibility coverage. The other 12 have exact variant probability rows but Chase is
unavailable because its value-weighted probability-coverage gate is not met.

Machine-readable evidence lives in
[`pull_scarcity_control_v1`](pull_scarcity_control_v1/analysis.json), with the builder at
[`build_pull_scarcity_control_research.py`](../../backend/scripts/build_pull_scarcity_control_research.py).

## 1. Pull Scarcity authority inventory

| Construct | Meaning/formula | Level | Authority | Probability role |
|---|---|---|---|---|
| Exact Pull Scarcity | `p_i`; packs `1/p_i`; nats `-ln(p_i)`; bits `-log2(p_i)` | card variant/run | `simulation_card_variant_pull_rates.modeled_probability` | derived pack-presence result |
| Simulation frequency | presence count and expected-copy count from 1,000,000 openings | card variant/run | same table and run | source observations; expected copies are not presence probability |
| Generalized F | slot-aware union probability of at least one eligible card with Appeal > 50 | set | frozen C4 `card_gt50` | consumes card probability, then collapses identity |
| Chase Accessibility | `sum(HC_i*p_i)`, with `HC_i=V_i^2/sum(V_j^2)`; effective depth `1/sum(HC_i^2)` | set | exact run variants | consumes the same `p_i`; value-weighted |
| Chase Opportunity/Pillar | production Chase input to Overall RIP | set/product | frozen Chase pipeline | downstream aggregation; do not duplicate |
| Chase Efficiency | `target value * p_i / verified pack-equivalent cost`, plus pull milestones | card/product route | exact run plus current value/cost | economic numerator input |
| EV realization | simulated distribution of pack/box value | set/product | calculation-run results | probability drives outcomes, not a scarcity score |
| Pull milestones | `ceil(log(1-q)/log(1-p_i))` packs for q in 50/75/90/95% | card/product route | Chase Efficiency | derived from `p_i` |

No alternate probability authority is introduced. `effective_pull_rate` is reciprocal
odds, and `pull_count/simulation_count` is expected copies; neither may replace pack
presence probability.

## 2. Rarity versus actual Scarcity

The full card table is
[`card_scarcity.csv`](pull_scarcity_control_v1/card_scarcity.csv); the grouped table is
[`rarity_distribution.csv`](pull_scarcity_control_v1/rarity_distribution.csv).
Rarity is not a safe scarcity substitute:

- Common spans p=.000626 to .113110 (181x); Uncommon .000647 to .143305
  (221x); Rare .000685 to .109735 (160x).
- Illustration Rare spans .001164 to .023904 (20.5x), SIR .000729 to .005311
  (7.3x), and Hyper Rare .000866 to .006675 (7.7x).
- Common and Uncommon median probabilities are nearly identical (.024079 and
  .024036). Other differently named labels also lie within 10% of one another.

The large within-label dispersion and cross-label overlap falsify label substitution.
Raw label casing also fragments nominally identical categories, another reason to keep
the exact probability as authority.

## 3. Treatment versus Scarcity

Results are in [`treatment_distribution.csv`](pull_scarcity_control_v1/treatment_distribution.csv)
and [`era_treatment_distribution.csv`](pull_scarcity_control_v1/era_treatment_distribution.csv).
Here “canonical treatment” is the existing normalized designation, augmented in the
card table by printing type, special type, and edition; it is not a new Treatment score.

Some premium labels are strong regime-local proxies, but none is deterministic at the
card level: SIR varies 7.3x, Hyper Rare 7.7x, Ultra Rare 5.7x, and Illustration Rare
20.5x. Common/uncommon/rare are especially weak proxies (160–223x). Era nesting is
mandatory: for example common/uncommon medians differ materially between Mega Evolution
and Scarlet & Violet. Treatment remains diagnostic-only, and exact p remains the common
axis.

## 4. F versus Scarcity redundancy

Across the 22 sets where frozen generalized F is available, Spearman(F, median p over
all modeled variants) is 0.412: related, not interchangeable. F is a slot-aware union
over eligible desirable cards; it answers whether a pack contains at least one desirable
outcome. Per-card scarcity retains which card is difficult and the distribution F
necessarily discards.

Archetypes A–F therefore separate cleanly: many accessible desirable cards can share F
with one jackpot; frequent desirable cards plus one jackpot can share F with a flatter
chase population; low F can arise from one or several scarce cards. Reported set rows in
`analysis.json` include F, desirable counts, raw probability distribution, rarest p,
and Chase effective depth. A public score is deliberately not selected.

## 5. Chase versus Scarcity redundancy

Among 22 Chase-ready sets, Spearman(Chase Accessibility, median p) is 0.329. The modest
association does not eliminate structural overlap: Chase consumes the identical `p_i`
authority but weights it by price-derived Chase Significance. Adding positive scarcity
to Collector Appeal would let one pull-difficulty fact affect Overall RIP through both
Collector and Chase. An elite scarce card, several elite scarce cards, and a frequent
roster plus scarce jackpot are explicit double-count cases. No Chase change is proposed.

## 6. Chase Efficiency conceptual boundary

- Intrinsic scarcity: `p_i`, `1/p_i`, or `-log(p_i)`; price-free.
- Desirability-conditioned accessibility: probability combined with independently
  defined desirability; a research interaction, not intrinsic scarcity.
- Product accessibility: pull milestones and route-specific packs; adds configuration.
- Economic Chase Efficiency: target value times probability divided by verified pack
  cost; necessarily price-bearing and outside Collector construction.

## 7. Prior demand × scarcity reconstruction

The Card Fair Value study used the price-free composite
`appeal_excess(subject_desirability) * scarcity_transform(p)` and grouped every split by
set. The target was log current market price. OOF R² was .137 for the composite versus
.475 for scarcity alone and .678 for rarity median. Multiplication collapses two axes:
a common/high-demand and scarce/low-demand card can have the same product, so the model
cannot recover which mechanism generated it. This directly falsifies shipping simple
multiplicative Appeal × Scarcity; it does not prohibit preregistering a separate
regression interaction after Appeal is frozen.

## 8. Synthetic falsification report

Cases 1–5 (Appeal 95/20/60 crossed with common/scarce) require Appeal to remain unchanged
by scarcity; an undesirable scarce card cannot become desirable. Cases 6–8 distinguish
many accessible desirable cards, one inaccessible elite, and several inaccessible
elites using F plus the scarcity distribution. Cases 9–11 cross high/low D with high/low
F and require neither to be inferred from the other. Cases 12–15 cross premium/ordinary
Treatment, Appeal, and scarcity and require all three axes to remain separable. Only the
diagnostic/control role passes every invariant without manufacturing appeal or counting
p twice.

## 9. Coverage and missingness

The snapshot has 34 run-authoritative sets across Scarlet & Violet (16), Sword & Shield
(12), and Mega Evolution (6); 7,620 modeled variants; 7,615 canonical mappings; 22 F and
Chase-ready sets. Missing canonical identity remains null. Missing probability remains
unavailable—never rarity-imputed. Trainer/Artist availability cohorts remain separate;
missing Artist evidence is never zero. Every future model reports its complete-case n,
set count, era count, and exclusion ledger.

## 10. Scarcity role recommendation

Retain exact p, expected packs, and log scarcity as read-only diagnostic fields and as
structural controls in later validation. Do not choose a production normalization or
weight. Do not add scarcity to Collector Appeal. Evidence supports acquisition friction
and possible market-expression interaction, not independent preference/prestige.

## 11. Frozen future Appeal → Price validation protocol

Freeze the final price-independent Collector model, its run/fingerprint, all predictors,
cohort rules, transforms, outcomes, splits, seed, and gates before joining price. Primary
outcome is `log(current NM market price)`; secondary outcomes are raw price and within-set
and within-era ranks. Price joins occur only in the validation layer.

Use leave-one-set-out and deterministic grouped K-fold by set; era-held-out analysis when
at least three usable eras exist. Never random-split cards. Cluster bootstrap by set
(minimum 1,999 draws, frozen seed), with coefficient intervals and paired OOS metric
deltas. Report Spearman, Pearson on log price, OOS R², MAE, RMSE, n, sets, eras, and
positive/negative set counts. No result may tune the frozen Appeal model.

Interpretation is multivariate: strong/partial/weak/not-supported depends on direction,
incremental OOS information, consistency, and robustness after controls—not a single
correlation cutoff.

## 12. Within-set specification

Primary: `log_price ~ set_FE + z_within_set(log_expected_packs) + era_nested_treatment +
structural_controls + z_within_set(CollectorAppeal)`. Fit controls-only then add Appeal;
also regress controls-only, retain cross-fitted residuals, and relate them to Appeal.
Report within-set Spearman, pooled standardized Appeal effect with set-clustered interval,
LOSO metrics, and signs by set. Comparable strata require same set and sufficiently
supported treatment/variant status; never discard discordant results silently.

## 13. Within-era specification

For each preregistered era:
`log_price ~ CollectorAppeal + log_expected_packs + treatment + set_FE + log1p(age_days)
+ promo + variant/edition controls`. Compare controls-only with +Appeal under held-out-set
CV. Report coefficient/partial relationship, held-out-set Spearman, incremental OOS R²,
MAE/RMSE deltas, and between-era sign consistency.

## 14. Cross-era scarcity-controlled specification

`log_price ~ CollectorAppeal + log_expected_packs + era_FE + treatment_nested_in_era +
log1p(age_days) + set_controls + promo/variant controls`. Named rarities are never pooled
as equivalent across eras. Exact probability is the shared structural axis; semantic
treatment attributes may be pooled only after an explicit frozen mapping. Evaluate
grouped-set CV and leave-one-era-out where estimable.

## 15. Interaction specifications

After centering continuous variables within the training fold, compare main-effects
models with exactly one added term at a time:

- `CollectorAppeal × log_expected_packs`: does scarcity change the market expression of
  intrinsic appeal?
- `CollectorAppeal × treatment_nested_in_era`: does presentation change that expression?

Interactions are research-only, evaluated by paired OOS deltas and clustered intervals.
No positive result feeds scarcity or Treatment back into Collector Appeal automatically.
Component analyses separately test Pokémon, Trainer, Artist-available, Playability,
final card Appeal, Treatment, Pull Scarcity, and interactions on explicit availability
cohorts.

## Frozen decision

SCARCITY_DIAGNOSTIC_ONLY
