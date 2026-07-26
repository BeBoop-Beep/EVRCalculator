# Desirability-as-Price-Driver Study — Research Protocol (PARKED)

**Status: specification only. Do not build yet.** This is a design doc for a
future backend/data study, recorded so the plan is fixed *before* any results
are viewed and so no frontend copy overclaims ahead of it. When the study is
run, it should be run as a standalone analysis (notebook/script), reviewed,
and only then surfaced in the UI. Nothing in the live product may imply these
results exist until then.

Written to double as the methodology writeup if published.

---

## 1. Purpose and honest framing

Establish whether collector demand — the **price-independent** part of
desirability — actually drives individual card prices, in a way that survives
the obvious confounds. The claim must be defensible against a price-derived
competitor model (e.g. Collectrics) and against a stats-literate reader.

The study is designed so that **any** outcome is publishable:

- A positive result is a credibility win for desirability.
- A null/weak result is itself a shareable study — "collector appeal affects
  price less than the hobby assumes, with proof."

Because the outcome is unknown, the method must be airtight before results are
viewed. This document is that pre-registration.

**Claim ladder (enforced in UI copy today):** everything currently shipped is
*contemporaneous correlation* — desirability and market values measured at the
same time. The product may say desirability **explains / tracks / agrees
with** market value. It may not use "predicts," "forecast," or "leading
indicator" until the lagged forward-return stage (§6) is run and holds. A
contract test guards this in the Insights section source.

## 2. The three components (verify labels first)

Desirability decomposes into components exposed today as toggles. Working
interpretation — **to VERIFY in discovery, not assume**:

| Component | Working interpretation | Price relationship |
|---|---|---|
| Pure Pokémon Demand | Collector appeal (fan votes on favorite Pokémon) + Google Trends 30-day interest | Price-INDEPENDENT — the clean predictor |
| Treatment Score | How premium the print is (SIR, IR, alt art, full art, gold, rainbow) | Rarity-adjacent → price-CONTAMINATED — the dirty component / disclosed control |
| Card Appeal | Pure Demand + Treatment merged (clean + dirty) | Expected to show the HIGHEST raw correlation precisely because it partly measures price with price — its high number proves little on its own |

**Mandatory discovery task before trusting any result:** confirm from the
actual code/data which component is genuinely price-independent. There is a
live suspicion that the "Card Appeal" label may be misapplied. If the
pure/merged labels are swapped, every interpretation below inverts. Report the
true composition of each component before proceeding.

## 3. Study design — pooled, within rarity band

- **Pool all available cards (~30,000+ across ~170 sets)**, not per-set.
  Per-set samples (≤295) are underpowered; the current Card Validation n=15
  subsample is far too small and must not be the basis of any claim. Pooling
  fixes the power problem.
- **Primary analysis is WITHIN rarity/treatment bands**, not across them:
  SIRs vs SIRs, mega rares vs mega rares, rares vs rares. This strips the
  dominant confound — rarity drives both appeal-of-print and price.
- **The decisive question:** *within a single rarity band, do
  higher-collector-demand Pokémon command higher prices than lower-demand
  Pokémon of the same rarity?*
  - Holds within-band → demand is a real, rarity-independent driver.
  - Appears only across bands → it was rarity all along.
- Also run the naive across-all-cards correlation, but label it explicitly as
  confounded/weak context, never as the finding.

## 4. Statistics and guardrails

- Compute **both Pearson r and Spearman ρ**; treat **Spearman as primary**.
  Card prices are extremely right-skewed (few grails, long cheap tail) and
  Pearson is distorted by outliers. Spearman answers the honest question: do
  higher-demand cards tend to *rank* higher in price?
- **Where Pearson and Spearman diverge, surface the gap** — it usually means
  outliers are carrying Pearson. Never hide it.
- **Report n per band.** Splitting by rarity (and further by Pokémon) thins
  cells fast; 30k total does not guarantee adequate n per comparison. Set a
  minimum-sample floor; any band/cell under it is reported as "insufficient
  sample," never quietly charted. This prevents recreating the n=15 problem
  inside a bucket.
- **Per-Pokémon driver read within each band:** identify whether the
  more-appealing Pokémon are the price drivers within each band. Report as
  texture, not a single verdict.

## 5. Three-component decomposition + keep/fix/cut gate

Run §3/§4 separately for each component against price:

1. **Pure Pokémon Demand vs price — the decisive test.** If price-independent
   demand alone holds within bands, the predictor is real and non-circular.
   Lead with this even though its number will be lower than the merged one.
2. **Treatment Score vs price.** Expected to correlate because it is nearly a
   price proxy; its role is to demonstrate and quarantine the contamination,
   stated honestly.
3. **Merged Card Appeal vs price.** A higher merged correlation does NOT
   validate desirability — adding a price proxy raises correlation
   mechanically. The merge is only meaningful if step 1 already held. **The
   ORDER is the proof; the merge is the finished product.**

For each component, an explicit **keep / fix / cut** decision: a component
that fails to hold within bands is critiqued, revised, or removed from
desirability rather than defended. A component that only "works" via price
contamination is flagged as such.

## 6. Expect a partial, conditional result (design for texture)

The most likely real outcome is "holds here, not there" — e.g. pure demand
holds strongly in top rarity bands but washes out among commons, or holds for
iconic Pokémon but not obscure ones. The output must surface WHICH bands and
WHICH Pokémon tiers hold up, not one pass/fail number. That nuance is the
actual product — more credible and more useful than a flat verdict.

**Confirmation-bias guard:** iconic top-of-set examples (Charizard, Pikachu,
mega chases) confirm the story under any explanation, including "rarity did
it" — they are not evidence. The within-band commons/mid-tier cards are where
the real test lives.

## 7. Predictive stage — SECOND, gated, later

Everything above proves desirability *explains* current price
(contemporaneous). It does NOT prove *prediction*. The predictive test is a
separate later stage, gated on:

- (a) the within-band explanatory result (§5 step 1) actually holding, AND
- (b) historical appeal snapshots existing.

**Discovery for the gate:** determine whether historical appeal values are
stored (appeal as it was weeks/months ago) or only current appeal.

- **If historical snapshots exist** → the test is: pure demand at time T vs
  forward price *return* T→T+30/60/90, out-of-sample, within rarity bands,
  controlled for base price. Report as a decile spread or rank information
  coefficient (IC) over time, not a single correlation.
- **If only current appeal exists** → the forward test is BLOCKED ON DATA.
  Scope the study to "explains," and record that capturing historical appeal
  snapshots going forward is the prerequisite to ever making a predictive
  claim. Do not fabricate history.

Only after the predictive stage holds may any UI use future-tense language
("predicts," "leading indicator"). Until then, all copy is "explains / tracks
/ agrees with."

## 8. Frontend honesty rules in force until the study runs

These apply to the live Desirability Evidence UI **now** (implemented in the
current pass; see `frontend/components/explore/RipStatisticsPageClient.jsx`
and `frontend/components/explore/desirabilityAlignment.mjs`):

- Lead with the defensible set-level result (desirability ↔ set value across
  all ranked sets), NOT the underpowered single-set card-level correlation.
- The card-level relationship, where shown, is explicitly labeled
  **"Preliminary"** (small single-set sample), never validated or predictive.
- No "predict / forecast / leading indicator" language anywhere — enforced by
  a contract test in `RipStatisticsSetLoad.contract.test.js`.
- The engine's per-signal agreement score is unsigned 0–100 rank closeness;
  the UI renders it as a ranked list and never fabricates a signed
  confirm/conflict axis or new agreement math from it.
- Desirability and set value are computed from independent inputs; the
  section tooltip states this (the agreement is not circular), and no claim
  goes beyond what the contemporaneous data shows.
