# Treatment Prestige — Collector-Preference Research (Price-Independent)

Research status: `TREATMENT_PRESTIGE_DIAGNOSTIC_ONLY`

This is a research-only companion to [[CARD_TREATMENT_PRESTIGE_V2_RESULTS.md]] and
[[TREATMENT_MARKET_PRESTIGE_V3_RESULTS.md]]. Those two studies ask "does treatment
associate with price" (V2: causal, rejected — `DO_NOT_APPROVE_CARD_TREATMENT_PRESTIGE_V2`;
V3: observational market association, `V3_MARKET_PRESTIGE_PARTIALLY_SUPPORTED`). This
study deliberately asks a different, narrower question: **is Treatment Prestige a real
collector-preference construct that can be defined and evidenced without touching market
price at all?** No price data, pull-rate data, or PSA population data was used to
construct anything in this document. No Collector V6/V7 formula was changed. No
production writes were made. `main` was not touched.

---

## 1. Construct definition

**Treatment Prestige** = the additional collector appeal created by the physical/visual
presentation or special treatment of a card, independent of:

- who/what is depicted (Pokémon subject → owned by desirability research)
- who illustrated it (Artist Recognition → closed lane, direct-preference-primary)
- how hard the card is to pull (Exact Pull Scarcity → owned by the pull model)
- what it costs (market price → explicitly out of scope here)

Explicit non-identities:

- Treatment Prestige ≠ Pull Scarcity — a treatment can be common (reverse holo exists in
  nearly every modern set at a fixed slot rate) or scarce (SIR); scarcity is a frequency
  fact, prestige is a preference fact.
- Treatment Prestige ≠ Rarity label — "Rarity" in `pokemon_canonical_cards.rarity` is a
  print-run/allocation label assigned by the publisher, not a collector vote.
- Treatment Prestige ≠ Price — price mixes scarcity, subject demand, artist demand,
  treatment, condition-population, and liquidity; it cannot be decomposed into a clean
  treatment signal without exactly the identification problems V2/V3 already ran into.

---

## 2. Current treatment-data audit (repo facts)

Confirmed by direct inspection (no inference):

- `pokemon_canonical_cards.rarity` — free-text TEXT column, sourced from
  `source_payload JSONB` (raw Pokémon TCG API payload). No dedicated columns for
  holo/foil/illustration/full-art/gold/rainbow/etched/stamped — those concepts are folded
  into this one free-text string (`backend/db/migrations/026_add_pokemon_canonical_cards.sql`).
- `simulation_card_variant_pull_rates.printing_type` / `.special_type` — separate
  string fields carrying finish (`holo`, `reverse_holo`) and special-pattern info
  (`poke_ball`, `master_ball`, `stamped`) independent of the rarity label
  (`backend/db/migrations/20260827230636_...sql`).
- `pokemon_card_treatment_scores` (V2) — first-class `treatment_key`, `rarity_key`,
  `printing_type`, `special_type`, `edition`, `era_id`, `scope_type` columns
  (`backend/db/migrations/20260828160000_create_card_treatment_prestige_v2.sql`).
- Normalization already exists in three independent modules:
  - `backend/domain/pokemon/card_rarity_taxonomy.py` (`pokemon-card-rarity-taxonomy-v2`)
  - `backend/desirability/card_treatment_prestige_v2.py` (`RARITY_ALIASES`,
    `PRINTING_ALIASES`, `SPECIAL_ALIASES`, `resolve_treatment_identity()`)
  - `backend/desirability/treatment_market_prestige_v3.py`
    (`TREATMENT_COMPONENT_CLASSIFICATION`: rarity_designation, printing_finish,
    special_treatment, edition_status = treatment; mechanic/species/set = controls;
    promo_status = excluded-ambiguous)
- Era-scoped raw→group mapping exists per era directory under
  `backend/constants/tcg/pokemon/{baseWotcEra,eCardEra,exEra,neoEra,gymEra,
  platinumEra,diamondAndPearlEra,heartGoldAndSoulSilverEra,blackAndWhiteEra,xyEra,
  sunAndMoonEra,swordAndShieldEra,scarletAndVioletEra,megaEvolutionEra,popEra,npEra,
  otherEra}/*Config.py`, each with its own `RARITY_MAPPING`.
- Literal fields named `alternate_art`, `full_art`, `gold`, `rainbow`, `textured`,
  `etched` do **not** exist as columns anywhere; where present at all, they live inside
  free-text rarity values (e.g. `"rare rainbow"`, `"hyper rare"`) aliased downstream.
- `Collector Appeal` (`backend/desirability/collector_appeal.py`) explicitly lists
  `treatment_prestige` in `excludedInputs` in `collector_appeal_payload()` — it is a
  documented candidate, not a live input. This confirms Treatment Prestige has never
  entered a shipped score.

**Conflation point:** raw rarity strings conflate designation (Illustration Rare, Ultra
Rare), finish (holo vs. reverse holo), and sometimes edition/special-pattern in a single
free-text token per era. The existing V2/V3 taxonomies already separate these into
composable fields — that decomposition does not need to be rebuilt, only reused.

---

## 3. Canonical treatment taxonomy (proposed, composable)

Reusing the V3 decomposition (`TREATMENT_COMPONENT_CLASSIFICATION`) as the base, since it
is already implemented, tested, and era-aware:

| Attribute | Values (examples) | Independent axis? |
|---|---|---|
| A. Base presentation | normal, holo, reverse_holo | Yes — varies within a rarity |
| B. Illustration presentation | illustration_rare, special_illustration_rare, full_art, gallery-style equivalents | Yes — semantically distinct from rarity slot |
| C. Premium finish/material | etched, gold/hyper_rare_gold, rainbow, textured, special foil pattern | Yes — some are era-specific finishes layered on top of a designation |
| D. Promotional/stamped | stamped, prerelease, event/promo | Ambiguous (see V3 finding: promo_status is `class C, excluded_ambiguous` because it conflates channel/set/rarity) |
| E. Composite | any card may carry >1 of A–C simultaneously | Required — do not force single-label classification |

This matches the guardrail in the task: do not force mutual exclusivity, and do not
invent categories the catalog can't defensibly derive. Recommendation: **adopt the
existing V3 `TREATMENT_COMPONENT_CLASSIFICATION` as the canonical taxonomy skeleton**
rather than create a fourth parallel one; extend it only where new eras add SV-style
categories (mega/current) not yet represented.

---

## 4. Era mapping matrix

| Era | Illustration-tier equivalent | Premium finish | Confidence |
|---|---|---|---|
| Base/WotC | none (holo vs. non-holo only) | 1st Edition stamp | Exact — no illustration tier existed |
| e-Card | none | none | Exact |
| EX era | Gold Star ≈ proto-illustration-prestige concept | none | Approximate — Gold Star conflates rarity+treatment+species selection |
| Neo/Gym | none | none | Exact |
| Diamond & Pearl / Platinum | none | none | Exact |
| HGSS | none (Prime/LEGEND experiment) | LEGEND split-card | Ambiguous — LEGEND is a mechanic+treatment hybrid |
| Black & White | Full Art (BW/XY era) begins | none | Strong equivalent to later "Illustration Rare" lineage |
| XY | Full Art, Secret Rare (rainbow) | rainbow foil | Strong equivalent |
| Sun & Moon | Full Art, Rainbow Rare, Prism Star | rainbow, prism foil | Strong equivalent |
| Sword & Shield | Full Art, Rainbow Rare, Secret Rare (gold), Amazing Rare | gold, rainbow, textured (VMAX) | Strong equivalent |
| Scarlet & Violet | Illustration Rare, Special Illustration Rare, Hyper Rare (gold) | gold, textured | Exact — this is the era the existing V2/V3 studies already froze cohorts against |
| Mega Evolution/current | Illustration Rare / SIR lineage continues | gold/rainbow-equivalent | Exact by extension of SV taxonomy, pending confirmation once cohort data exists |

Key finding restated from the guardrail: **"Secret Rare" is not one visual treatment
across eras.** XY/SM Secret Rare (rainbow) is visually and conceptually different from
SWSH Secret Rare (gold) and from the SV Hyper Rare gold treatment that replaced the
"Secret Rare" name entirely. Any cross-era Treatment Prestige score must be scoped
within era-consistent designation families, exactly as V2/V3 already do (`scope_type`
includes `era`, `era_supertype`).

---

## 5. Preference-source inventory + contamination audit

This is the load-bearing section for the final decision. Targeted search (this session)
for direct, price-independent collector preference evidence found:

| Candidate source | Type | Contamination |
|---|---|---|
| Community "prettiest card" / aesthetic-appreciation threads (e.g. Sportskeeda coverage of a 151-set "prettiest card" share) | Informal, single-post opinion, no structured vote | `PARTIALLY_CONTAMINATED` — not a poll, no sample size, no methodology, subject/artist confounded with treatment |
| Collector-guide blog commentary ("alt-arts are gallery pieces," "premium among investors") | Marketing/guide copy | `PRICE_CONTAMINATED` — explicitly frames preference in investment terms |
| Reddit r/PokemonTCG poll threads on illustration rare vs. secret rare | Searched for directly; none located with usable methodology, sample size, or price-blinding | `UNUSABLE` — no retrievable structured data |
| Official Pokémon Company / TCG surveys on treatment preference | Searched; none found | `UNUSABLE` — does not appear to exist publicly |

**Finding:** no `CLEAN` source was located. Nearly all discoverable community discussion
of "which treatment is better" is phrased in terms of scarcity ("rarer"), investment
("better pull," "more valuable"), or is really about a specific card's subject/art
rather than the treatment category in the abstract. This is consistent with the general
difficulty already documented in this project for Appeal-type constructs: see
[[project_appeal_history_blocked]] and [[project_trends_anchor_defect]] for parallel
cases where a desirability signal lacked clean primary data and had to be diagnostic-only
or paused pending better data collection.

This absence is itself the central research result: **the market has not produced a
public, structured, price-blinded, rarity-blinded treatment-preference dataset.** Building
one requires a first-party instrument (Section 7), not secondary research.

---

## 6. Treatment vs. rarity-status confound test

Because no clean survey data exists, this cannot be empirically resolved from secondary
sources. What can be said from the V2/V3 record already in this repo:

- V2 (causal identification) found that within the *same* rarity/scarcity band,
  cross-designation comparisons (e.g. SIR vs. Illustration Rare vs. Ultra Rare within
  S&V) are **not identifiable** — there is no common-support population of the same
  Pokémon at the same scarcity level across designations to isolate "do collectors like
  the art style" from "this one is rarer." (`Round 5/6 identification diagnosis`,
  `CARD_TREATMENT_PRESTIGE_V2_RESULTS.md`)
- V3 (market-observational) found large, stable, era-specific price associations for
  designation (e.g. SV Special Illustration Rare ≈ +512% vs. common, stable across
  leave-set-out), but explicitly could not separate that from scarcity, since V3's design
  keeps Exact Pull Scarcity in the world rather than removing it, and states the
  limitation directly: "observational confounding; treatment bundles include unmeasured
  scarcity."

Conclusion for this task: with *existing* data, reasons (A) genuine art preference, (B)
known rarity, and (E) price are entangled and empirically inseparable in this catalog.
Isolating (A) requires exactly the blinded pairwise design in Section 7 — it cannot be
recovered from price or pull data, however creatively re-analyzed, because price and pull
data are the confound, not a proxy for it.

---

## 7. First-party pairwise preference experiment design (design only — not implemented)

**Question asked of respondents:** "Which card's presentation/art treatment do you
prefer?" — price, rarity label, and pull odds hidden from the stimulus.

**Pair construction rules:**

1. Same Pokémon species, different treatment (e.g. same species as Illustration Rare vs.
   Special Illustration Rare, or holo vs. reverse-holo of the identical printing).
2. Same artist (where creditable), different treatment — isolates treatment from artist
   style.
3. Same species + same artist, different treatment — tightest isolation, rarest pair type
   to source.
4. Visually comparable subjects (matched by prior, price-independent
   `pokemon_desirability_composite_v1` score bucket) across treatments, when (1)–(3) are
   unavailable — a looser control, flagged as such.

**Blinding requirements:**
- Crop/replace any set-symbol, rarity-symbol, or card-number watermark that leaks
  designation.
- Never show two cards from the same product context that would let a respondent infer
  scarcity from packaging language.
- Randomize left/right position per respondent to remove order effects.
- Collect enough demographic/segment metadata (collector vs. player self-identification)
  to test whether preference differs by respondent type, without asking about price.

**Sample size / power:** would need to be set once a target minimum-detectable-effect is
chosen; not scoped here since no survey is being run in this task.

**Explicitly out of scope for this design:** asking "which is worth more," "which would
you rather own," or "which is rarer" — those reintroduce price/scarcity into the
response.

---

## 8. Treatment vs. Artist separability

To keep Artist Recognition, Subject (Pokémon desirability), Treatment, and Scarcity
separable at the card level, the minimum required metadata is:

- `artist_id` (or normalized artist name) — already a plausible field on
  `pokemon_canonical_cards`/source payload, needs confirmation it's populated
  consistently pre/post SV.
- `species_id` — already used by V2/V3 (`pokemon_desirability_composite_v1` join key).
- `treatment_key` (V2/V3 decomposed fields) — already exists.
- `modeled_probability` / pull-rate reference — already exists in
  `simulation_card_variant_pull_rates`.

No new tables are required to *keep these separable*; the existing V2/V3 schema already
carries all four as distinct columns/joins. The risk is analytical, not
schema-related: any future Treatment Prestige coefficient must be fit with artist and
species as controls (as V3 already does with species FE), or it will silently absorb
artist-driven variance (a Kanda SIR looking "prestigious" because of Kanda, not the SIR
treatment).

---

## 9. Treatment vs. Scarcity — redundancy risk

Per the V3 record, several designations are near-synonymous with a fixed rarity slot in a
given era (e.g. within SV, "Special Illustration Rare" almost always denotes one specific
print-run tier). Where a treatment label is deterministically 1:1 with a scarcity tier in
an era, giving both (a) Exact Pull Scarcity credit and (b) full Treatment Prestige credit
for the same card double-counts one structural property under two names.

**Recommendation:** if a future Treatment Prestige signal is built, it should be
restricted to attributes that are *not* deterministic functions of designation within an
era — i.e., composable finish/material attributes (textured, gold accent, etched) that
can and do vary independently of the rarity slot (Section 3, category C), rather than the
designation label itself (category B), which is already effectively scarcity information
wearing a different name.

---

## 10. Candidate architecture comparison (conceptual only, no fitting)

| Option | Description | Fit for current evidence |
|---|---|---|
| A. No signal (control) | Baseline, no change | Always valid fallback |
| B. Treatment-category prestige | Score per designation from direct preference evidence | Not supportable — no clean preference evidence exists (Section 5) |
| C. Composable visual attributes | Separate scores for illustration-focused / textured / gold / rainbow / stamp, each independently evidenced | Structurally sound (matches Section 9's redundancy fix) but still blocked on evidence |
| D. Bounded card-level lift (`Base Appeal + remaining_headroom × λ × TreatmentPrestige`) | Positive-only, capped contribution | Correct target shape *if and when* evidence exists; λ deliberately not chosen here per task guardrail |
| E. Diagnostic only | Expose treatment identity/coverage without scoring | **Matches current evidence state** |

---

## 11. Synthetic falsification (conceptual, no market fitting)

Walking the 12 required cases against candidate architecture D (bounded positive lift)
and E (diagnostic):

1. Common beautiful illustration — a positive-only bounded lift correctly allows credit
   without requiring rarity.
2. Scarce plain card — correctly receives $0 treatment lift; scarcity is scored
   elsewhere.
3. Common gold-looking treatment — tests whether "looks premium" alone (without rarity)
   would be scored; under (C)'s composable design, a genuinely common gold finish gets
   whatever independently-evidenced gold-attribute score exists, not an automatic high
   score — correctly resists rarity leakage only if the evidence source itself is
   rarity-blind (Section 7 requirement).
4. Scarce gold treatment — should not receive a higher treatment score merely for being
   scarce; scarcity is scored on a separate pillar.
5–6. Popular Pokémon / regular treatment vs. unpopular Pokémon / premium treatment —
   requires species control (Section 8) to avoid treatment absorbing subject appeal.
7–8. Elite artist / regular treatment vs. unknown artist / premium treatment — requires
   artist control (Section 8) to avoid treatment absorbing artist appeal.
9–10. Rare rainbow vs. common rainbow — same finish, different rarity: correct result is
   equal treatment credit, different scarcity credit; this is the direct test of
   Section 9's redundancy concern and the strongest argument for scoring finish
   attributes (C) rather than designation labels (B).
11. Stamped promo with high recognition — flagged in Section 3 as ambiguous
   (`promo_status: class C, excluded_ambiguous` per V3); correctly excluded from any
   treatment score under the current taxonomy.
12. Extremely rare, visually ordinary card — should receive ~$0 treatment lift despite
   high scarcity, again confirming the two pillars must stay decoupled.

Result: the *structural* requirements (positive-only, non-overpowering, rarity ≠
automatic prestige) are satisfiable by architecture D/C **in principle**, but every case
above depends on a treatment score that was itself derived from rarity-blind evidence.
Since no such evidence source currently exists (Section 5), the falsification exercise
shows the architecture is sound but currently unfillable.

---

## 12. Coverage study

Exact cohort sizes were not re-derived in this task (no new queries were run against
production data, per the research-only/no-market-price constraint and to avoid
duplicating the already-frozen V2/V3 cohorts). From the existing frozen studies already
in the repo:

- V3's frozen cohort: 19,847 of 20,651 canonical cards priced; 165 sets; 17 eras; 1,022
  species. Taxonomy coverage there: rarity/designation 98.80% mapped, printing finish
  100%, special-treatment/edition nulls represent "no explicit designation," not missing
  data.
- V2's frozen cohort: 7,619 exact variant rows, 7,597 (99.7%) join cleanly to canonical
  cards, across 22 supported sets.

These coverage numbers can be reused directly for a future Treatment Prestige coverage
report — they already answer "does the catalog have clean treatment identity" for the
overlapping 22-set and ~165-set cohorts. No separate new coverage query was justified for
this research task since it would only reproduce V2/V3's existing, already-audited
numbers.

---

## 13. Operational data-model recommendation (not implemented)

If a future Treatment Prestige source becomes evidenced, the minimum schema needed
(versioned, composable, additive to what already exists in
`pokemon_card_treatment_scores`):

- `treatment_taxonomy_version` (already exists as `TAXONOMY_VERSION` constants; needs a
  persisted column if not already tracked per-row)
- `treatment_attributes` (composable set/array: illustration_focused, textured, gold,
  rainbow, stamped, etc.) rather than one mutually-exclusive `treatment_key`
- `source_raw_rarity`, `source_printing_type`, `source_special_type` (already exist)
- `mapping_confidence` (exact / strong / approximate / ambiguous / not_treatment, per
  Section 4)
- `preference_evidence_version` (references whichever frozen first-party survey run
  produced the score, once one exists)
- `treatment_prestige_score` (nullable — absent until evidenced)
- `treatment_source_confidence`

No migration was written or applied. This is a recommendation for a future, separately
authorized task.

---

## 14. Refresh cadence recommendation

- **Static** (taxonomy, card→treatment mapping): re-derive only when a new era/set
  introduces new designation or finish vocabulary — event-driven, not scheduled. This
  mirrors how `backend/constants/tcg/pokemon/<era>/*.py` is already organized (one config
  per era, edited only when a new era ships).
- **Dynamic** (collector preference evidence, if ever collected via Section 7's
  instrument): re-run only when enough new treatment types have shipped to be worth
  re-surveying, or on a slow cadence (e.g. annually) — collector aesthetic preference is
  not expected to drift week to week. Do not scrape or re-survey on the same cadence as
  price/Trends data.

---

## 15. Future market-validation plan (design only — no execution here)

Once/if a Treatment Prestige candidate is frozen from rarity-blind, price-blind
first-party evidence (never from price itself), the existing Collector market-validation
harness should test, in order:

- M0: structural controls (set, era, release age, card type, rarity where appropriate)
- M1: + modeled Pull Scarcity
- M2: + Subject Appeal (`pokemon_desirability_composite_v1`)
- M3: + Artist
- M4: + Treatment Prestige

Primary question: does Treatment Prestige add independent explanatory power *after*
actual scarcity, subject, and artist are already in the model. Report (later, not in this
task): raw Spearman, controlled effect, Δ out-of-sample R², MAE/RMSE change, held-out-set
stability, era consistency. This reuses V3's existing fixed-effects/bootstrap machinery
(`residualize_fixed_effects`, `centered_contributions`) rather than requiring new
infrastructure.

---

## 16. Final decision

`TREATMENT_PRESTIGE_DIAGNOSTIC_ONLY`

**Why not READY:** No clean (`CLEAN`), or even reliably `PARTIALLY_CONTAMINATED`,
price-independent, rarity-blind collector preference source was found (Section 5). Without
that evidence, any card-level Treatment Prestige score would necessarily be built from
price or rarity-label correlation — which is exactly what V2 (rejected) and V3
(observational-only, explicitly not causal) already show is confounded with scarcity and
cannot be defended as an independent construct.

**Why not REJECTED:** The construct is not incoherent. The taxonomy already exists and is
implemented (Sections 2–3), era mapping is tractable (Section 4), the confound with
scarcity is structurally avoidable if scoring is restricted to composable finish
attributes rather than designation labels (Section 9), and a concrete, executable
first-party experiment design exists to produce the missing evidence (Section 7). This is
a data-availability gap, not a construct-validity failure.

**Why not PARTIAL (i.e., "taxonomy ready, evidence just thin"):** PARTIAL implies some
usable, if limited, direct preference evidence exists to authoritatively score at least a
subset of treatments. None was found — the gap is total, not partial. `DIAGNOSTIC_ONLY`
is the accurate status: expose treatment identity/taxonomy/coverage (useful today, zero
price contamination risk) without any score entering Collector Appeal, pending the
Section 7 first-party instrument.

**Recommended next step (not authorized or started here):** commission or run the
Section 7 blinded pairwise preference instrument. Until that produces `CLEAN` or
`PARTIALLY_CONTAMINATED` data with adequate sample size, Treatment Prestige should remain
exactly where it already sits today — an `excludedInputs` diagnostic entry in
`collector_appeal.py`, not a scored input.

TREATMENT_PRESTIGE_DIAGNOSTIC_ONLY
