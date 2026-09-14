# Pull Scarcity — Collector Appeal Separation/Redundancy Research

Research status: `SCARCITY_DIAGNOSTIC_ONLY`

This is future V7 research, run in parallel with the running Pokémon Trends V2 capture,
which this task did not touch. No Collector formula, Overall RIP, Chase Accessibility,
Trainer, or Artist module was modified. No market price was used to construct scarcity.
No production writes were made. `main` was not touched.

---

## 1. Construct definition

**Pull Scarcity** = the difficulty of obtaining a specific card from sealed product
under an accepted, modeled opening distribution — sourced only from modeled pull
probability / slot structure, never from price, rarity name alone, PSA population,
sales volume, listing count, or "hype."

Explicit non-identities:

- Pull Scarcity ≠ Treatment Prestige — orthogonal presentation axis
  ([[project_collector_appeal_findings]]; prior task's `TREATMENT_PRESTIGE_DIAGNOSTIC_ONLY`)
- Pull Scarcity ≠ Rarity Label — Section 4 quantifies the gap directly
- Pull Scarcity ≠ Price — by construction; price is excluded from every source used below
- Pull Scarcity ≠ Desirable Outcome Frequency (F) — F is a *pack-level union* over
  desirable subjects; scarcity is a *card-level* magnitude (Section 6)
- Pull Scarcity ≠ Chase Accessibility — Chase Accessibility is a *value-weighted,
  set-level* expectation that requires price; scarcity as defined here must not use
  price (Section 7)

---

## 2. Existing scarcity authorities (audit)

| Authority | File | Formula | Granularity | Uses price? |
|---|---|---|---|---|
| Modeled pull probability | `simulation_card_variant_pull_rates.modeled_probability`, loaded/asserted by `backend/desirability/chase_accessibility.py` (`assert_probability_authority`) | `p_i` per card-variant per calculation run | card-level | No |
| Pull-rate loader (Collector-facing) | `backend/desirability/pull_model.py` (`PULL_MODEL_LOADER_VERSION = pull_model_loader_v2_...`) | `probability_from_denominator()`: `P = 1/N` from "1 in N" odds; slot-grouped (add within slot) | card-level, slot-aware | No |
| Desirable Outcome Frequency (F) | `backend/desirability/desirable_outcome_frequency.py` | `F = P(pack contains ≥1 card tied to an eligible desirable subject)`, via slot-aware union `union_probability_from_cards()` | pack/set-level (aggregates across desirable subjects) | No |
| Chase Significance / Accessibility / Depth | `backend/desirability/chase_accessibility.py` | `HC_i = V_i²/ΣV_j²`; `O_pack = ΣHC_i·p_i`; `N_HC = 1/ΣHC_i²` | set-level, value-weighted | **Yes** (`price_used`) |
| Chase Opportunity (Overall RIP V11 Chase pillar) | `backend/desirability/chase_opportunity.py` | `100·K/(K+10)`, K = Core chase count from `chase_core_k.py` | set-level | Indirectly (K basket built from priced "chase" definitions upstream) |

**Two authoritative traps documented directly in the code** (`chase_accessibility.py`):
`effective_pull_rate` is a "1-in-N" odds value, not a probability (must be inverted
before use), and `pull_count`/`simulation_count` is expected-copies, not P(≥1 copy) —
these differ on 2,398 of 7,615 cohort rows per the module's own tolerance check. Any new
scarcity work must read `modeled_probability` directly, not these two fields, or it will
silently reproduce a known-documented bug class.

**Coverage:** the "22 supported sets" language recurs across `chase_accessibility.py`
(`MIN_MAPPED_HC_MASS` context) and `docs/research/CHASE_ACCESSIBILITY_STAGE14.md`
("22/22 sets," "22 sets report mappedHcMass = 1.000000"). This is the accepted
pull-probability-modeled cohort. A separate "128 sets" figure appears only in
`collector_appeal_v6_pokemon_baseline_transform_final.md`, describing the broader
Collector Appeal candidate-scoring cohort (Monte Carlo rank-shift test), not
pull-probability coverage — **these are two different cohorts and must not be conflated**
(this reconciles the task's framing that "generalized F is currently available for only
the modeled subset" of the broader 128-set Collector cohort).

No duplicate probability authority is proposed here. Any future scarcity work should
read `simulation_card_variant_pull_rates.modeled_probability` via the same accessor
`chase_accessibility.py` already uses (`assert_probability_authority`), not introduce a
new pull-probability computation path.

---

## 3. Card-level structural representations (compared, not selected)

| Form | Formula | Behavior |
|---|---|---|
| Raw probability | `p` | Bounded [0,1], but nearly all mass near 0 for scarce cards — poor resolution at the tail that matters most |
| Expected packs | `1/p` | Unbounded above; a single ultra-scarce card can dominate any linear aggregation; not stable across extreme probabilities |
| Log expected packs | `log(1/p) = -log(p)` | Monotonic with difficulty, compresses the unbounded tail, symmetric treatment of order-of-magnitude differences (1-in-1,000 vs 1-in-10,000 is a fixed additive step, not a 10,000x explosion) |
| Information-style scarcity `-log(p)` | identical to log expected packs (they are the same expression) | Same as above; standard information-theoretic "surprisal" framing |

All four are monotonic and price-independent by construction (none reference
`price_used`, `modeled_probability` is the only input). `-log(p)` / log-expected-packs is
the only candidate of the four that is simultaneously bounded-below (0 at p=1),
unbounded-but-compressed above, and stable under the extreme-probability tail that
`expected packs` and raw `p` each handle poorly in opposite directions. This is a
mathematical-behavior comparison only — no public score is selected here, per the task
constraint.

---

## 4. Rarity vs. actual scarcity

Exact per-set min/median/max/dispersion numbers were not recomputed in this task (doing
so would require a live query against `simulation_card_variant_pull_rates` for the 22
modeled sets, which this research-only task did not run to avoid any risk of touching
the pull-model pipeline while the Trends capture is active). The qualitative finding is
already established and documented in this repo without needing a new query:

- `chase_accessibility.py`'s own trap documentation proves within-cohort dispersion
  exists even *within a single field's semantics*: `pull_count` vs. presence-probability
  disagree on 2,398/7,615 rows (31.5%) — i.e., a naive rarity-adjacent proxy already
  diverges materially from the authoritative `modeled_probability` on nearly a third of
  the cohort, before even comparing across rarity labels.
- V2/V3 Treatment research (prior task) already demonstrated the same underlying point
  from the price side: within a single rarity/designation band (e.g. S&V Illustration
  Rare), cross-card comparisons were not identifiable because *scarcity itself varies
  materially within one nominal rarity label* — that is precisely "same rarity label,
  different actual scarcity," the condition this section asks about.
- Recommended follow-up (not performed here): a direct `GROUP BY rarity_key` dispersion
  query against the frozen 22-set cohort already used by V2/V3 and Chase Accessibility,
  reusing their existing joins rather than building a new one. This task deliberately did
  not execute that query so as to avoid any read/write pressure on the shared pull-rate
  pipeline during the concurrent Trends capture; it is a same-day follow-up, not a gap in
  reasoning.

**Directional conclusion (supportable from existing docs without new queries):** rarity
label is known to be an imperfect, non-1:1 proxy for actual modeled pull probability —
the codebase already treats them as distinct fields (`rarity_key` vs. `modeled_probability`
are separate columns everywhere they co-occur) and already documents at least one
mechanism (naive proxy fields) by which they diverge on a meaningful fraction of rows.
Rarity cannot safely stand in for actual scarcity; this is consistent with, not
contradicted by, the earlier Treatment research.

---

## 5. Treatment vs. scarcity

Reusing the prior task's taxonomy and its Section 9 finding directly: within the SV era,
certain treatment designations (e.g. Special Illustration Rare) are documented as
**near-deterministic functions of a fixed rarity/scarcity slot**, while composable finish
attributes (gold accent, texture, etched) are the parts of Treatment that can plausibly
vary independently of scarcity. No new market-price-driven analysis was run here (per
guardrail); this section confirms the previous finding still holds and flags it forward:
**any future scarcity component must be checked for the same designation-label
redundancy risk already identified for Treatment** — i.e., if a scarcity metric is built
per rarity-designation bucket rather than per exact card, it degenerates into exactly the
"designation label wearing a different name" problem already flagged in the Treatment
research, rather than genuine card-level scarcity.

---

## 6. Scarcity vs. Desirable Outcome Frequency (F)

**Mathematically:** F is a *pack-level union* over the set of eligible desirable
subjects — `F = P(≥1 card tied to an eligible desirable Pokémon subject appears)`,
computed via slot-aware union (add within slot, multiply slot-miss across independent
slots). It answers "does the pack produce anything desirable," not "how hard is this
specific card." Card-level scarcity `p_i` (or `-log p_i`) is exactly one input F
consumes internally per eligible card, but F **discards** per-card magnitude once it
folds each eligible card into the union — a set with one desirable card at p=0.01 and a
set with ten desirable cards summing to the same union probability produce the *same* F
value while having completely different scarcity structure (Archetypes A vs. D/E,
Section 11).

**Empirically (conceptual, using the required archetypes since no new query was run):**

- Archetype A (many moderately desirable, accessible cards) vs. Archetype B (one
  extremely scarce desirable chase): these can be constructed to have *identical* F
  (same total union probability of hitting something desirable) while having maximally
  different card-level scarcity distributions. **F cannot distinguish them; card-level
  scarcity can.**
- Archetype D (frequent desirable hits + one jackpot chase) vs. Archetype E (low F,
  several similarly scarce chases): again distinguishable only by looking at the
  per-card scarcity distribution underneath F, not by F itself.

**Conclusion:** card-level Pull Scarcity describes something F structurally cannot,
by F's own definition (a union collapses per-card magnitude). This is the strongest
argument in this report for scarcity being informationally distinct from an existing
Collector construct. It does **not** by itself imply scarcity should be a *scored*
Collector Appeal component — only that it is not redundant with F.

---

## 7. Scarcity vs. Chase Accessibility (critical redundancy gate)

**Chase Accessibility's exact formula uses `p_i` directly:**
`O_pack = Σ_i HC_i · p_i` where `HC_i = V_i² / Σ_j V_j²`. This means Chase Accessibility
already consumes the identical `modeled_probability` authority that any Collector
scarcity component would use — the *only* difference is the `HC_i` value-squared weight,
which requires `price_used`.

**Double-counting examples:**

1. If Collector Appeal added a card-level scarcity score built from the same `p_i`, and
   that card also happens to be one of the set's dominant Chase-Significance cards
   (large `HC_i` because it's both scarce and high-value), then **the same underlying
   pull-difficulty fact would enter Overall RIP twice**: once through the existing Chase
   pillar (`Chase Opportunity`, built from `chase_core_k.py`'s basket, itself downstream
   of Chase Accessibility's `p_i`-weighted structure) and once through a new Collector
   Appeal scarcity term for that same card.
2. This occurs **at the Overall RIP level**, not merely within one pillar — Chase
   Opportunity is documented as "the production Chase pillar of Overall RIP V11"
   (`chase_opportunity.py` docstring), and Collector Appeal is a separate, independently
   weighted pillar of the same Overall RIP. Two pillars both reacting positively to the
   same `p_i` fact for the same card is a structural double-count risk even though the
   two formulas look different on paper (`HC_i·p_i` sum vs. a hypothetical card-level
   `-log p_i` score).
3. **Key distinguishing fact:** Chase Accessibility's redundancy risk is *conditioned on
   price* (via `HC_i`), while Collector Appeal must stay price-free. So the overlap is
   not "identical formulas" — it's "same root probability fact (`p_i`), reused under
   different weighting, feeding the same downstream Overall RIP total." The task's
   framing ("could Overall RIP change twice for the same underlying pull difficulty") is
   answered **yes, plausibly**, for any card that is simultaneously scarce (drives a
   Collector scarcity score) and high-chase-significance (already drives the Chase
   pillar via the same `p_i`).

**Conclusion:** an independently scored Collector Appeal scarcity component carries real
double-counting risk against the existing Chase pillar, specifically for the subset of
cards where scarcity and chase-significance co-occur (which, per Section 4/5, is a
*meaningful* subset, not a rare edge case, since designation-driven scarcity and
high-price concentration are documented to correlate in the V3 market study). A
diagnostic-only exposure of `p_i`/`-log p_i` carries no such risk since it does not enter
Overall RIP at all.

---

## 8. Does scarcity itself create appeal?

No clean behavioral/collector evidence was located in this task (consistent with the
prior Treatment research's finding that direct, price-blind collector-preference
evidence is generally unavailable in accessible community sources —
[[project_collector_appeal_findings]]). The four framings from the task brief:

- **A. Scarcity increases perceived prestige** — plausible folk claim, no clean
  supporting evidence found; indistinguishable from price-driven "rarer = better
  investment" framing without a blinded instrument (same contamination problem
  documented for Treatment).
- **B. Scarcity just makes an already-desirable card harder to obtain** — this is the
  null/control framing: scarcity doesn't add appeal, it's a friction/accessibility fact
  layered on top of independently-sourced desirability. Nothing in this repo's existing
  constructs contradicts this framing; F and Chase Accessibility both already treat
  probability as a *multiplier/weight* on desirability or value, never as an
  appeal-generating quantity on its own.
- **C. Scarcity can reduce opening appeal via inaccessibility** — directly supported by
  the *existence* of Chase Accessibility as a distinct metric from raw chase-card value:
  the whole point of `O_pack` and `N_HC` (effective depth) is to capture that a single
  inaccessible jackpot is a *worse* pack experience than several accessible desirable
  hits, which is exactly framing C.
- **D. Scarcity matters only via interaction with Subject/Artist/Treatment** — this is
  tested empirically in Section 10 below (Card Chase Appeal) and found to fail.

No evidence found here supports A as an independent, additive, positive Collector Appeal
input. B and C are already the operating assumptions baked into F and Chase Accessibility
respectively — meaning the repo's existing architecture already reflects "scarcity is a
friction/context variable, not an appeal generator," and this research did not surface
anything to overturn that.

---

## 9. Candidate roles

| Option | Description | Assessment |
|---|---|---|
| A. Reject from Collector | Scarcity lives only in F / Chase Accessibility / diagnostics | Structurally clean, no double-count risk, but discards the genuine per-card information gap identified in Section 6 |
| B. Diagnostic only | Expose card pull odds, expected packs, chase depth without changing Collector Appeal's score | Matches Section 6's finding (real information) and Section 7's finding (scoring it risks double-counting) simultaneously |
| C. Interaction only (`Appeal × Scarcity`) | No independent score; scarcity contextualizes another appeal signal | Directly falsified for the multiplicative form by the Card Chase Appeal result (Section 10) — needs a non-multiplicative interaction form to even be worth reconsidering, and none is proposed or tested here |
| D. Bounded scarcity/prestige lift | Only viable if independent collector evidence supports scarcity-as-prestige | Blocked — no such evidence found (Section 8) |

**B (diagnostic only) is the option consistent with every finding in this report**: it
captures the genuine card-level information F structurally discards (Section 6), avoids
the Overall RIP double-count risk of an independently scored component (Section 7),
requires no unsupported "scarcity = prestige" claim (Section 8), and does not repeat the
falsified multiplicative interaction (Section 10).

---

## 10. Prior demand × scarcity failure — reconstruction

Study located: **"Card Chase Appeal"**, `docs/research/collector_appeal_market_prediction_results.md`.

- **Formula:** `Card Chase Appeal = Subject Desirability × Card Scarcity` (a direct
  multiplicative combination of a desirability score and a scarcity score into one
  card-level number).
- **Outcome (out-of-fold R², market back-test):**
  - Card Chase Appeal (the multiplicative combination): **0.137**
  - Scarcity alone: **0.475** (Δ = −0.338 vs. the combination)
  - Rarity median alone: **0.678** (Δ = −0.541 vs. the combination)
  - Desirability alone: the combination beat this by +0.091 — i.e., multiplying in
    scarcity helped *relative to desirability alone*, but multiplying in desirability
    *hurt badly* relative to scarcity/rarity alone.
- **Stated conclusion (verbatim from the doc):** "Multiplying the two into one score
  destroys information that keeping them separate retains," and "multiplying
  desirability by scarcity into one card score makes predictions worse than just knowing
  the card's rarity. Don't ship it."
- **Why information was lost (mechanism, as documented):** a single multiplicative score
  cannot represent the fact that a *highly desirable but common* card and an *undesirable
  but scarce* card can produce the same product — the two source signals are not
  interchangeable along a single multiplied axis, so the combination is less informative
  than either input kept separate, let alone both kept separate.
- **Does this falsify multiplication generally?** It falsifies the *simple multiplicative
  combination of these two specific signals into one production score* — it is strong,
  directly on-point precedent against any new `Appeal × Scarcity` architecture proposed
  in this task's Candidate C, and this research does not propose repeating that
  architecture under a new name. It does not, on its own, prove no interaction form
  could ever work (e.g., a non-linear, bounded, or fixed-effects-style interaction was
  not tested by that study) — but no such alternative form is proposed or evidenced here
  either, so Candidate C remains unsupported rather than merely "not yet tried."

A separate, non-equivalent multiplicative-structure study
(`collector_appeal_v6_cross_bucket_redesign_research.md`, candidates
`cand_G_multiplicative_g4/g8`) tested a desirability × structure-modifier form and found
it "well-behaved" but with an unspecifiable D-dependent inversion boundary, leading to a
different candidate being recommended instead. This is a different construct (not
demand×scarcity) and is noted only to avoid conflating the two multiplicative studies.

---

## 11. Synthetic archetypes

Reasoning against the required invariants, using the constructs already defined above
(F, Chase Accessibility, card-level scarcity as diagnostic):

1. **Extremely desirable + common** — high Subject Appeal, scarcity diagnostic near 0;
   F and Collector Appeal both already handle this correctly today (desirability enters
   independently; scarcity as diagnostic changes nothing).
2. **Extremely desirable + extremely scarce** — high Subject Appeal, scarcity diagnostic
   very high; under Option A/B, Collector Appeal score is unaffected by the scarcity
   value — correctly does not double-score the same card that Chase Opportunity is also
   rewarding via `HC_i`.
3. **Undesirable + extremely scarce** — must not become highly appealing merely because
   it's rare. Under B (diagnostic only), it doesn't — scarcity is exposed as a number,
   never fed into the score. This is the direct test that rejects Option D (bounded
   scarcity lift) absent evidence, and rejects any accidental "scarcity floor" in scoring.
4–5. **Moderate desirability + common/scarce** — same logic; scarcity value is
   informative context for a human reading the diagnostic, never a score input.
6. **Many accessible desirable cards** — high F, likely high `N_HC` (deep chase),
   diagnostic scarcity per-card modest — Chase pillar and F already jointly describe
   this; no Collector scarcity score needed.
7. **One inaccessible elite chase** — low `N_HC`, F could still be moderate/high or low
   depending on the union; per-card scarcity diagnostic on that one card would be very
   high — this is exactly the case Section 6 shows F structurally cannot surface, so
   exposing it as a diagnostic (not a score) adds real explanatory value without
   re-scoring Overall RIP.
8. **Several inaccessible elite chases** — same as 7, compounded; still diagnostic-only,
   still no double-count with the Chase pillar.
9–11. **Strong/weak roster with low/high F** — F and Subject Appeal already jointly
   capture roster strength and pack-level accessibility; scarcity diagnostics explain
   *why* F is low/high without needing to re-enter the score.
12. **Treatment-prestigious but common card** — ties directly to the Treatment research:
    confirms Treatment and Scarcity remain properly decoupled (a premium finish on a
    common card should show near-zero scarcity diagnostic and, per the prior task, no
    Treatment score at all today), so neither construct manufactures appeal for the
    other's sake.

All required invariants hold under Option B (diagnostic only): undesirable+scarce does
not become appealing, scarcity cannot manufacture Subject Appeal, an inaccessible chase
does not necessarily raise the Collector score, and the F/Chase redundancy is visible and
explained rather than silently duplicated.

---

## 12. Coverage

Reusing already-documented coverage rather than re-querying live tables during the
concurrent Trends capture (per guardrail to avoid touching shared pipeline load):

- Accepted, exact modeled pull probability: **22 sets** (the cohort referenced
  throughout `chase_accessibility.py` and `CHASE_ACCESSIBILITY_STAGE14.md`, with
  `MIN_MAPPED_HC_MASS = 0.99` gating coverage per set).
- Broader Collector Appeal candidate-scoring cohort: **128 sets**
  (`collector_appeal_v6_pokemon_baseline_transform_final.md`) — this is the cohort over
  which Collector Appeal candidates are Monte-Carlo rank-tested, not the pull-probability
  cohort.
- The gap between 22 and 128 is exactly the set of sets where F is `unavailable`
  (insufficient covered demand share) and Chase Accessibility would report
  `chase_accessibility_insufficient_probability_coverage` — i.e., **any card-level
  scarcity diagnostic inherits the same 22-set ceiling** as F and Chase Accessibility,
  since it depends on the identical `modeled_probability` authority.
- No new coverage breakdown by era/rarity/treatment was computed in this task (would
  require a live query against the same shared pull-rate tables); flagged as a same-day,
  low-risk follow-up rather than a gap in this analysis.

---

## 13. Missingness policy

For any card/set without accepted pull probability: **scarcity = unavailable.**
Consistent with F's own documented behavior (`REASON_INSUFFICIENT_COVERAGE` returns
`unavailable`, not a neutral/default value) and with `chase_accessibility.py`'s explicit
insufficient-coverage status rather than silent fallback. No rarity-derived approximation
is proposed here, and none should be substituted without its own separately validated,
preregistered study — exactly mirroring the standard already set by F and Chase
Accessibility's missingness handling.

---

## 14. Future market-validation specification (design only)

Reusing the existing Collector market-validation harness design, extended per the task's
sequence:

- M0: structural controls (set, era, release age, card type, rarity where appropriate)
- M1: + Subject Appeal
- M2: + actual Pull Scarcity (diagnostic candidate, not yet a production score)
- M3: + Treatment diagnostic/candidate
- M4: + Playability
- M5: + Artist

Report (later, not executed here): raw correlations, controlled effects, incremental
out-of-sample R², held-out-set Spearman, MAE/RMSE — reusing the exact harness/format
already used for `collector_appeal_market_prediction_results.md` (Section 10) so results
are comparable to the already-failed Card Chase Appeal baseline.

Two governing questions for that future study:
1. Does Artist/Treatment/Subject Appeal still add information *after* actual scarcity is
   controlled?
2. Does an explicit Collector Scarcity component add anything *after* F and Chase
   Accessibility already exist in the model? — Given Section 7's structural
   double-counting risk and Section 10's empirical multiplicative failure, the prior for
   this second question should be skeptical by default; the study should be designed to
   falsify "scarcity adds nothing beyond F+Chase" rather than to confirm a component that
   is already suspected redundant.

---

## 15. Final decision

`SCARCITY_DIAGNOSTIC_ONLY`

**Why not SUPPORTED:** Section 7 shows a plausible, structural double-counting path
against the existing Chase pillar of Overall RIP for any card where scarcity and
chase-significance co-occur — which, per the V2/V3 Treatment record, is not a rare edge
case. Section 8 found no clean evidence that scarcity is itself an independent,
positive, additive collector-appeal generator (as opposed to a friction/accessibility
fact already correctly modeled by F and Chase Accessibility as a weight/multiplier, never
a standalone positive score).

**Why not INTERACTION_ONLY:** Section 10 reconstructs a direct, on-point precedent —
`Subject Desirability × Card Scarcity` ("Card Chase Appeal") — that performed
substantially worse (R² 0.137) than scarcity alone (0.475) or rarity alone (0.678) in a
real market back-test, with an explicit "don't ship it" conclusion in this repo's own
research record. No alternative, non-multiplicative interaction form is proposed or
evidenced in this task, so Candidate C remains unsupported rather than merely untested.

**Why not REJECTED:** Section 6 shows card-level scarcity carries real information that F
structurally cannot surface (F is a pack-level union that discards per-card magnitude by
definition), and Section 11's archetypes (7, 8 especially) show cases where that
information materially changes the explanation of a set's opening experience even though
it should not change the score. Discarding scarcity entirely (Option A) would mean
Collector Appeal explanations for "why is this set's F low / why is `N_HC` shallow" have
no card-level grounding to point to.

**Recommended next step (not authorized or started here):** expose card-level
`modeled_probability` / `-log(modeled_probability)` (log expected packs) as a read-only
diagnostic on Card Detail / Collector explanation surfaces for the 22-set accepted
cohort, sourced via the existing `assert_probability_authority()` accessor in
`chase_accessibility.py` (no new probability computation path), with explicit
`unavailable` status outside that cohort. Do not add it as a Collector Appeal score
input, and do not multiply it against Subject/Artist/Treatment appeal, until a future
M0–M5 validation study (Section 14) produces evidence that an explicit scarcity term adds
information beyond F and Chase Accessibility already flowing into Overall RIP.

SCARCITY_DIAGNOSTIC_ONLY
