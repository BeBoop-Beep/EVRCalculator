# Collector Appeal V6 Cross-Bucket Redesign — Recommendation

Status: **research recommendation only. Nothing in this document has been implemented, and no production state has changed.**

## Domain classification

| Domain | Classification | Rationale |
|---|---|---|
| Pokémon | **CORE** | Independent, empirically-grounded evidence (fan popularity + Trends); unchanged from today's authority; the only domain with enough evidence density to anchor a roster metric on its own. |
| Trainer | **BOUNDED LIFT** | Genuinely independent empirical evidence (12m/5y entity-observation percentile) exists, but the evidence population and scale are not shown comparable to Pokémon's. A capped, headroom-bounded lift lets real Trainer signal move the score without letting cross-domain scale mismatch drive rank. |
| Functional/Item | **DIAGNOSTIC** (not WITHHOLD — it should stay visible, just not as a demand signal) | No independent collector-demand evidence exists at all; only Playability can move it. Reporting it as a Playability/Utility diagnostic is legitimate and useful; treating it as Collector Appeal is not. |

## Answers to the seven required questions

**1. Should Pokémon and Trainer remain separate bucket scores?**
Yes. `D_pokemon` and `D_trainer` should each be computed and persisted as their own within-domain roster scores. This is what makes the downstream combination auditable — you can see exactly how much of the final number is Pokémon-driven versus Trainer-driven, and it preserves the option to withhold Trainer entirely at the API/contract layer if needed later.

**2. Should Trainer affect final Collector Appeal now?**
Yes, but only through a bounded, capped mechanism — not by pooling raw values. The empirical results support this: Candidate B1 removes all 24 double-digit rank distortions found in the current model (max distortion drops from 41 to 7 positions) while still letting real Trainer strength move the score (e.g., Cosmic Eclipse's strong Trainer roster still contributes a visible, non-zero lift). A pure Pokémon-only control (Candidate A) is safer still but discards real signal that the sensitivity analysis shows is robust (±20% Trainer-source noise moves no set's rank by more than 2 positions under B1).

**3. If yes, how without raw cross-domain comparison?**
Via a **bounded headroom lift**, architecturally identical in form to the already-accepted card-level Playability lift: `D = D_pokemon + (100 - D_pokemon) * BETA * (D_trainer/100)`. This never compares an individual Trainer subject's score to an individual Pokémon subject's score — it only ever asks "how strong is this set's Trainer roster, on its own terms" and lets that answer nudge the Pokémon-anchored score within a shrinking headroom. This is the same architectural pattern the codebase already uses and has already validated at the card level, just applied one level up.

**4. Should Functional contribute at all?**
No, not to Collector Roster Appeal. Functional has zero independent collector-demand evidence — its only source of variation is Playability, which is a gameplay-utility signal, not a collector-desirability signal. Conflating the two would reintroduce exactly the kind of unverified-comparability problem this research was commissioned to fix, just at a different domain pair. Functional should be surfaced as a **separate Playability/Utility diagnostic**, explicitly labeled as non-demand, never summed into D.

**5. Does generalized F remain valid under the corrected card eligibility architecture?**
Yes, with no change required to F's own construction. F's eligibility rule ("card belongs to the frozen cohort, is hit-eligible, has Card Collector Appeal above neutral, has modeled pull probability") is a **card-level** gate that doesn't depend on which domain a card's subject baseline came from — F never itself sums cross-domain group values, it operates on individual card-level `final_card_collector_appeal`, which is unchanged by this redesign (C3B is untouched). The only implication is that if a future corrected D changes which sets are "scored" versus "unavailable" at the roster level, F's set-level availability should be re-derived consistently — but the F formula itself needs no redesign.

**6. Does C5's small signed F modifier remain valid?**
Conceptually yes — C5 combines D and F at the set level, and neither D's internal cross-domain fix nor F's card-level construction changes the *shape* of that combination contract. However, since D's numeric value would change under a corrected architecture (even if only by single-digit points on most sets, per Section 5's table), C5's combined output would necessarily be recomputed against the new D — this is expected and does not indicate a flaw in C5's own transform, weights, or modifier logic, which are out of scope for this research and were not touched.

**7. Does this require a new model identity/fingerprint?**
Yes, unambiguously. `D`'s formula changes (bucket-aware bounded lift replaces pooled mass), which changes `collectorRosterFormulaFingerprint`, which changes the C4/C5/C6 lineage chain and therefore requires a new `model_version` and a new model run — never a mutation of `0efa3c8f-918d-49d7-ad5e-3ae37278058f`.

**8. Can the existing published V6 remain historical and a corrected successor be append-only?**
Yes. Nothing about this recommendation requires touching the existing published run. A corrected successor model would be built via the same append-only pattern already used to create V6 itself (new `model_version` string, new `model_run_id`, independent `promote_pokemon_collector_appeal_model_run` / `select_pokemon_collector_appeal_current` cutover), leaving V6 fully intact as a historical/control reference for exactly the kind of construct-validity comparison this document performs.

## Recommended architecture

**Candidate B1 (bounded Trainer headroom lift), with Functional excluded from D and surfaced only as a diagnostic**, is the smallest conceptually-correct correction that:
- eliminates the demonstrated 20–41 rank distortions (down to a residual ≤7, which reflects genuine bounded Trainer contribution, not scale-mismatch artifact),
- preserves the existing bounded-lift architectural pattern rather than inventing a new mechanism,
- is empirically robust to Trainer-source measurement uncertainty (±20% noise → ≤2 rank positions of churn, 0/3,840 Monte Carlo observations exceeding that),
- does not fabricate demand evidence for Functional subjects,
- requires no price input, no Artist, no Treatment, no Scarcity, and no weight changes to Overall RIP V12.

**Implementation caveat to carry into the build phase (not resolved here):** the data contract must represent "no Trainer groups present in this set" as an explicit `trainer_unavailable` state distinct from "Trainer groups present, scored near zero" — mathematically the lift term evaluates to the same (≈0) result either way, but the two states have different meanings and should not be silently collapsed, mirroring the existing missing-F-is-never-fabricated-as-zero policy already in place elsewhere in V6.

**Open item not resolved by this research (flagged, not solved here):** the ~0.995–0.999 correlation between `D_pokemon` and set-size proxies (card count, group counts of every type) indicates roster mass is fundamentally a basket-size statistic. This is a pre-existing property of the roster-mass formula inherited unchanged from current V6/C4 (not introduced by this redesign), consistent with the previously-documented Set Chase Efficiency Stage I degeneracy finding. It does not block the cross-bucket correction recommended here, but should be scoped as a separate research question before any future V7 program treats absolute D values as basket-size-independent.

## Final token

`V6_CROSS_BUCKET_REDESIGN_READY`

Candidate B1 (Pokémon = CORE, Trainer = BOUNDED LIFT via headroom formula, Functional = DIAGNOSTIC-only) is sufficiently supported — by synthetic falsification (Section 4), full 128-set empirical validation (Section 5), and sensitivity/robustness analysis (Section 6) of the companion research report — to proceed to implementation as a **new, append-only model identity**, leaving `pokemon_collector_appeal_v6_generalized_roster_frequency` / `0efa3c8f-918d-49d7-ad5e-3ae37278058f` untouched and historical. The exact public version string and formal fingerprint should be assigned at implementation time, once the architecture is formally accepted.
