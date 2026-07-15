# Desirability-vs-Price Card-Level Validation Study — Results

**Prompt A of a staged program.** This document holds the trustworthy numbers
to review before any UI is built. Data/analysis only. No UI, no scoring
changes, nothing committed.

**Status: STAGES 0, 1, 2 COMPLETE.** Stage 0 audit was reviewed and approved;
Stages 1 (pooled study) and 2 (keep/fix/cut) are now filled with live results.

- Database: Supabase project `TheIndex` (`zwxzxuuawalvwioadhmf`), `public` schema.
- Run date: 2026-07-14. All numbers are live queries against production data,
  not assumptions. Reproducible via `docs/research/desirability_card_study.sql`
  (exact queries used) and `docs/research/desirability_card_study.py`.
- Nothing committed. No UI/scoring/backend logic changed.

---

## Plain-language summary

Pooled over **16,276** priced Pokémon cards (Spearman ρ is primary because
prices are extremely right-skewed):

- **Pure Pokémon Demand (the clean, price-independent read) — weak-to-moderate,
  and mostly a rarity side-effect.** ρ = **0.37** pooled. But when you compare
  cards *within the same price tier*, it collapses to **0.05–0.18**. So the
  pooled 0.37 is largely "iconic Pokémon happen to appear on more expensive
  cards," not "among similarly-priced cards, the more-loved Pokémon costs more."
  It is a genuine but modest signal, strongest at the two extremes (cheap
  commons and four-figure grails) and near-zero in the $5–25 middle. **Trust:
  low-to-moderate; do not present it as a strong standalone price driver.**
- **Treatment Score (rarity proxy) — strong, as expected, and it proves
  nothing about desirability.** ρ = **0.58**. It is a pure function of rarity,
  and rarity drives price, so this is close to correlating price with a coarse
  version of itself. Useful as a disclosed control; not evidence.
- **Card Appeal (the merged headline number) — strong, but the strength is
  Treatment's, not demand's.** ρ = **0.57**, essentially equal to Treatment
  alone (0.58) and well above Pure Demand (0.37). Blending demand into the
  rarity proxy did **not** beat the rarity proxy by itself. Presenting Card
  Appeal's ~0.57 as validation of collector demand would overstate the case:
  the honest lead is Pure Demand's weaker, mostly-between-band 0.37.

**Bottom line for the downstream plan:** the price-independent signal exists but
is weak and largely rarity-driven at the pooled level; whether it survives *as a
rarity-independent driver* is genuinely unresolved and is exactly what the
within-rarity-band study (Prompt C) must decide. Nothing here supports leading
the UI with the merged Card Appeal correlation.

---

# STAGE 0 — DATA AUDIT

## Headline: the data supports the study, with three caveats to acknowledge up front

1. **Reachable universe is ~20k cards, not the ~30k the protocol targeted.**
   There are **20,143** canonical cards across **171** sets; **19,307** carry a
   usable price. The decisive Pure-Demand study runs on **16,277** priced
   Pokémon cards. This is still far more than enough for a well-powered pooled
   Spearman/Pearson analysis — but the "~30,000+" figure in the protocol should
   be corrected to ~20k reachable / ~16.3k in the decisive test.
2. **The labels are NOT swapped.** The toggle the UI calls **"Pure Pokemon
   Demand"** is the genuinely price-independent one. Confirmed from code, not
   assumed. Details in Q4.
3. **"Card Appeal" is a merge of _three_ inputs, not two.** The working
   hypothesis assumed Card Appeal = Pure Demand + Treatment. In code it is
   `0.55·PureDemand + 0.25·Treatment + 0.20·Scarcity` (renormalized over
   whichever components are present). Scarcity is a rarity/print-run proxy, so
   Card Appeal carries a second contaminated input, not one. Because scarcity
   is frequently absent, in practice it usually collapses to
   ≈`0.69·PureDemand + 0.31·Treatment`.

None of the three is a blocking finding. The clean Pure-Demand component **can**
be isolated per card, so the study is runnable.

---

## Q1 — Coverage

| Metric | Value |
|---|---|
| Total canonical cards (`pokemon_canonical_cards`) | **20,143** |
| Distinct sets | **171** (matches `sets` table row count) |
| Cards with a usable price (>0) | **19,307** |
| Canonical cards with **no** price | 836 (20,143 − 19,307) |
| Priced **Pokémon** cards (the decisive study N) | **16,277** |

- Reachable N is **~20k, not the ~30k** stated as the target in the protocol.
  The gap is not a data-loss bug — it is the actual size of the canonical
  checklist currently ingested (171 sets). Reported as an audit correction, not
  worked around.
- Every priced row joins cleanly to a canonical card (19,307 → 19,307). No
  orphaned price rows.

**Excluded by data availability at this stage:** 836 canonical cards with no
price row (cannot enter any price correlation).

## Q2 — Price

- **Field:** `pokemon_canonical_card_market_prices_latest.market_price`
  (`numeric`). Table comment: _"Refreshable canonical latest Near Mint USD
  market-price layer. One selected variant/condition per canonical checklist
  card."_ One selected price per card (Near Mint USD), so no per-card
  variant-collision handling is needed for the study.
- **Freshness (`captured_at`, a `date`):**

  | Metric | Value |
  |---|---|
  | Priced cards (distinct, price > 0) | 19,307 |
  | captured_at range | 2026-04-11 → 2026-07-14 (today) |
  | Captured within last 7 days | 19,229 (99.6%) |
  | Captured within last 30 days | 19,264 (99.8%) |
  | Captured > 90 days ago | 2 |

  Price data is **current and clean** — effectively a same-week snapshot. This
  is a genuine contemporaneous read, which is exactly what an "explains current
  price" study needs.

- **Price distribution (16,277 priced Pokémon cards) — extreme right skew:**

  | Stat | Value (USD) |
  |---|---|
  | min | 0.01 |
  | median (p50) | **0.81** |
  | p90 | 38.64 |
  | p99 | 334.39 |
  | max | 4,999.99 |
  | mean | 20.95 |
  | share < $1 | **52.5%** |
  | share < $5 | 71.2% |

  Mean ($20.95) sits above the 85th percentile; half of all cards are under a
  dollar while the top carries thousands. This **confirms the decision to treat
  Spearman ρ as primary** and Pearson r as outlier-sensitive secondary.

## Q3 — Rarity / treatment

- **Field:** `pokemon_canonical_cards.rarity` (`text`), populated for ~98.6% of
  priced cards (**261 nulls** out of 19,307).
- **~47 distinct raw values.** They include case/format variants of the same
  class (`Common` vs `common`, `Ultra Rare` vs `ultra rare`,
  `special illustration rare` vs `Special Illustration Rare`), plus a machine
  token `MEGA_ATTACK_RARE`. These are normalized in the scoring code by
  `normalize_rarity_label()` (lowercases, collapses whitespace, strips
  `_`/`-`) before `get_treatment_score()` / `classify_rarity()` run, so the
  variants are handled — but any raw analysis must apply the same normalization.
- **Top of the distribution (priced cards):** Common 5,165 · Uncommon 4,764 ·
  Rare 2,532 · Rare Holo 1,579 · Rare Ultra 766 · Promo 522 · Illustration Rare
  470 · Rare Rainbow 324 · Ultra Rare 320 · Rare Secret 319 · Rare Holo EX 304 ·
  Double Rare 297 · Rare Holo V 281 · (null) 261 · Special Illustration Rare 210
  · … (full 47-value enumeration captured in the analysis script output).
- **Assessment:** rarity exists and is clean enough for bucketing **after
  normalization**. The 261 nulls and the case-variants are the only hygiene
  items; both are reportable and handled, not blocking. (The full within-band
  bucket study is Prompt C — not run here.)

## Q4 — The three desirability components (CRITICAL)

Verified from source, not assumed. Key files:
- `backend/desirability/composite.py` (Pure Demand composition)
- `backend/desirability/card_appeal.py` (Treatment, Scarcity, Card Appeal merge)
- `frontend/components/explore/RipStatisticsPageClient.jsx:6563-6650`
  (UI toggle → underlying field bindings — the label-swap evidence)

### Pure Pokemon Demand — **PRICE-INDEPENDENT (the clean predictor)**
- Source: `pokemon_desirability_composite_scores.desirability_score`.
- Composition (`composite.py:75`, `score_components_json.formula`):
  **`0.75 · fan_popularity_score + 0.25 · current_trend_score`**
  - `fan_popularity_score` = fan votes on favorite Pokémon
    (`favoritepokemon` scraper).
  - `current_trend_score` = Google Trends **30-day relative search interest**
    (`today 1-m`, US), explicitly _not_ absolute volume.
- Scored **per Pokémon species** (1,025 rows = full Nat-Dex gen 1–9), then
  mapped onto individual cards through `pokemon_card_desirability_links`.
- **Contains no price input and no rarity input.** This is the genuinely clean,
  non-circular read. ✅

### Treatment Score — **PRICE-CONTAMINATED (rarity proxy / disclosed control)**
- Source: `get_treatment_score(rarity)` (`card_appeal.py:55`).
- A deterministic lookup from the normalized rarity label to a fixed score
  (e.g. `special illustration rare → 96`, `ultra rare → 80`, `common → 18`,
  unknown → `30`).
- **It is a pure function of rarity.** Rarity is the dominant driver of price,
  so Treatment is effectively a price proxy. Expected to correlate; that
  correlation proves little on its own. ✅ (matches hypothesis)

### Card Appeal — **MERGED (clean + two contaminated inputs)**
- Source: `calculate_adjusted_card_appeal(pokemon, treatment, scarcity)`
  (`card_appeal.py:95`).
- Weights: **`0.55 · PureDemand + 0.25 · Treatment + 0.20 · Scarcity`**,
  renormalized over whichever components are non-null (requires PureDemand
  present).
- **Correction to the working hypothesis:** it is a **three**-input merge, not
  two. The third input, **Scarcity** (`calculate_scarcity_score`, from pull
  probability / odds denominator), is itself a rarity/print-run proxy — a
  *second* contaminated input. When scarcity is unavailable (the common case;
  the UI copy says _"Scarcity is not included yet when scarcity data is
  unavailable"_) the merge renormalizes to ≈`0.69·PureDemand + 0.31·Treatment`.
- Interpretation unchanged: a high Card Appeal correlation does not validate
  desirability, because it partly measures price (via Treatment ± Scarcity)
  with price. Meaningful only if Pure Demand already holds. ✅

### The label-swap check — **LABELS ARE CORRECT, NOT SWAPPED**
Traced each UI toggle to the field it actually resolves
(`RipStatisticsPageClient.jsx`):

| UI toggle label | Resolver | Underlying value | Price-independent? |
|---|---|---|---|
| **"Pure Pokemon Demand"** | `getCardDesirabilityScore` (6563) | `subjectDemandScore` / `pokemonDesirabilityScore` = composite `desirability_score` | **YES — clean** |
| **"Card Appeal"** | `getCardAppealScore` (6604) | `card_appeal_score` → falls back to `adjusted_card_appeal_score` (the 3-input merge) | No — merged/contaminated |
| **"Treatment Score"** | `getCardTreatmentScore` (6592) | `treatment_score` (rarity map) | No — rarity proxy |

The user's suspicion that "Card Appeal" might be the genuinely price-independent
read is **not** borne out: "Pure Pokemon Demand" is the clean one, and it is
labeled correctly. No downstream interpretation needs to invert. ✅

### Can the clean Pure-Demand component be isolated per card?
**Yes — not blocking.** Per card it is the link-weighted subject demand:
`_weighted_card_subject_score(links, composite_scores)`
(`set_components.py:916`) — the contribution-weighted average of the linked
species' `desirability_score`, fully separable from Treatment and Scarcity.
Every priced Pokémon card (16,277) resolves to a link, and every link resolves
to a composite score (composite covers all 1,025 species), so coverage of the
clean component over priced Pokémon cards is effectively 100%.

## Q5 — Non-Pokémon cards

3,030 priced cards have no demand/appeal score. Breakdown by supertype
(priced + unlinked):

| Supertype | Priced, unlinked (no demand score) |
|---|---|
| Trainer | 2,656 |
| Energy | 356 |
| (null supertype) | 17 |
| Pokémon (edge) | 1 |
| **Total** | **~3,030** |

**Handling:** excluded from the Pure-Demand and Card-Appeal analyses — they
legitimately have no species demand score (Trainer/Item/Stadium/Energy). This
matches the shipped policy (`CARD_APPEAL_MARKET_PRICE_INFO_TEXT`). They remain
eligible for a Treatment-only view (Treatment derives from rarity, not species),
which is worth noting but out of scope for the decisive test. Reported with
counts; nothing imputed.

## Q6 — Historical appeal (Stage E availability check only)

- `pokemon_desirability_composite_scores`: **single snapshot** — 1 distinct
  `created_at` date (2026-06-11), 1 scoring version, 1,025 rows. **Only current
  appeal is stored at the composite level.**
- Upstream raw sources retain a few snapshots (2 fan-popularity source
  snapshots, 3 trend source snapshots; `pokemon_desirability_scores` 1,988 rows,
  `pokemon_trend_scores` 1,048 rows) — i.e. 2–3 historical raw captures, not a
  usable longitudinal appeal time series.

**One-line answer:** No usable historical appeal series exists (current appeal
only). Any forward-return / predictive stage (Prompt E) is **blocked on data**
and would require capturing appeal snapshots going forward. Reported only — not
built.

---

## Audit gaps & data-hygiene notes

1. **Coverage is ~20k, not ~30k** (Q1). Protocol target overstated the reachable
   universe; decisive test N = 16,277.
2. **Card Appeal is a 3-input merge** (Q4) — Scarcity is a second contaminated
   input the working hypothesis omitted.
3. **Scarcity input availability — RESOLVED: effectively zero in shipped Card
   Appeal.** The shipped snapshot builder calls
   `calculate_adjusted_card_appeal(subject_score, treatment, None)` —
   scarcity is passed as `None`
   (`backend/db/services/pokemon_public_snapshot_service.py:491-518`). So the
   product's Card Appeal is already just the renormalized
   `0.6875·PureDemand + 0.3125·Treatment`, and Stage 1 computed exactly that. A
   separate `scarcityAdjustedCardAppealScore` toggle exists but is not the Card
   Appeal metric and is out of scope here.
4. **261 priced cards have null rarity** → no Treatment Score; they drop out of
   Treatment/Card-Appeal analyses (kept for Pure Demand). Row count reported.
5. **Rarity case/format variants** require `normalize_rarity_label()` before any
   raw grouping (Q3).
6. **No historical appeal** (Q6) — Stage E is data-blocked.

## Planned data exclusions for Stage 1 (for transparency, none applied yet)

| Exclusion | Approx. rows | Reason |
|---|---|---|
| Non-Pokémon priced cards | ~3,030 | No species demand score (Trainer/Energy/null) |
| Canonical cards with no price | 836 | Cannot enter a price correlation |
| Null-rarity priced cards | 261 | No Treatment Score (Treatment analysis only; kept for Pure Demand) |

Nothing is dropped to strengthen a correlation; every exclusion above is a
structural "field does not exist for this row," reported with its count.

---

# STAGE 1 — POOLED CARD-LEVEL STUDY

Pooled across **all priced Pokémon cards** (not per-set). Spearman ρ primary;
Pearson r on raw price and on ln(price) as secondary. Spearman uses
tie-corrected average ranks. Component definitions replicate the shipped
backend exactly (see the audit Q4 and the `.sql` script).

### Top-line pooled results (no rarity control)

| Component | n | **Spearman ρ** | Pearson r (raw price) | Pearson r (ln price) |
|---|---|---|---|---|
| **Pure Pokémon Demand** (clean) | 16,276 | **0.370** | 0.196 | 0.406 |
| **Treatment Score** (rarity proxy) | 16,059 | **0.582** | 0.130 | 0.507 |
| **Card Appeal** (merged) | 16,276 | **0.569** | 0.221 | 0.577 |

Treatment n is lower because 261 priced Pokémon cards have null rarity (no
treatment score); they remain in the Pure Demand / Card Appeal columns. One card
with a non-finite/degenerate rank pairing is dropped by `corr()` (16,277 → 16,276).

**These pooled numbers ARE the "naive across-all-cards correlation without rarity
control"** the protocol asked for as confounded context. They mix rarity and
demand together; the within-band read below shows how much of the Pure-Demand
number is actually rarity.

### Step 1 — Pure Pokémon Demand vs price (the decisive test)

ρ = **0.370** (n = 16,276). This is a **real, positive, price-independent
signal** — the clean component alone ranks price better than chance, so the
relationship is not purely circular. But it is **modest**, and the heterogeneity
check shows most of it is a between-tier effect (next section). Lead with this
number, not the merged 0.57.

### Step 2 — Treatment Score vs price (the contamination control)

ρ = **0.582** (n = 16,059). As predicted, the rarity proxy correlates strongly.
This demonstrates and quarantines the contamination: Treatment is essentially a
coarse restatement of price, so its high ρ **proves nothing about desirability**.
It is the ceiling that any rarity-driven number will approach.

### Step 3 — merged Card Appeal vs price (the finished product)

ρ = **0.569** (n = 16,276). Critically, this is **≈ Treatment alone (0.582) and
below it**, and well above Pure Demand (0.370). Merging demand into the rarity
proxy did not beat the rarity proxy — it slightly diluted it. Under the protocol's
order-is-the-proof rule, the merged number is only meaningful if Step 1 held
strongly; it did not. So Card Appeal's 0.57 is **carried by Treatment/rarity**,
and must not be read as validating collector demand.

### Heterogeneity — where the Pure-Demand signal actually lives

Pure Demand vs price computed **within price bands** (price band is a coarse
stand-in for rarity/price level; the rigorous within-*rarity*-band study is
Prompt C, not run here):

| Price band | n | Spearman ρ (demand vs price) |
|---|---|---|
| < $1 | 8,543 | 0.157 |
| $1–5 | 3,041 | 0.078 |
| $5–25 | 2,554 | 0.047 |
| $25–100 | 1,422 | 0.090 |
| ≥ $100 | 716 | 0.176 |

The pooled 0.370 **collapses to 0.05–0.18 once price level is held roughly
constant.** Most of the pooled signal is between-band: higher-demand Pokémon
tend to land on more expensive cards, rather than demand ranking price *among
comparably-priced cards*. The residual within-band signal is real but weak and
**U-shaped** — strongest for sub-$1 commons (0.157) and $100+ grails (0.176),
near-zero in the $5–25 middle (0.047). (These within-band ρ are attenuated by
range restriction, so treat them as directional, not as the final within-rarity
verdict — that is Prompt C.)

### Pearson vs Spearman divergence (surfaced, not hidden)

Raw-price Pearson (0.13–0.22) is far **below** both Spearman (0.37–0.58) and
ln(price) Pearson (0.41–0.58). The four-figure grails dominate the raw-price
variance and crush linear correlation, while rank-based and log-based measures
agree with each other. **Raw Pearson is the least trustworthy number here;** the
skew is exactly why Spearman is primary. The Spearman/log-Pearson agreement is
reassuring for the direction and rough magnitude of each component.

---

# STAGE 2 — KEEP / FIX / CUT VERDICT

### Pure Pokémon Demand → **FIX (conditional; do not yet claim "keep")**

- **Evidence:** clean, price-independent input; pooled ρ = 0.37 is a genuine
  positive signal (not circular), **but** it falls to 0.05–0.18 within price
  tiers, i.e. most of it is rarity/price-level structure, not demand pricing
  cards within a tier.
- **Why not "keep":** the protocol's decisive question — *within a band, do
  higher-demand Pokémon cost more?* — is only weakly and unevenly supported by
  the price-band proxy, and the real rarity-band test hasn't run. Claiming it as
  a standalone price driver now would overstate a mostly-between-band effect.
- **Why not "cut":** it is clean and it does carry non-trivial signal at the
  extremes; it is not merely a price proxy. Removing it would be premature.
- **What would change the verdict to keep:** the within-*rarity*-band result
  (Prompt C) holding — higher-demand Pokémon out-pricing lower-demand Pokémon of
  the *same rarity*, in bands with adequate n. If it washes out there too, this
  moves to "cut/flag."

### Treatment Score → **KEEP as a disclosed rarity control — NOT as desirability evidence**

- **Evidence:** ρ = 0.58, exactly as a near-price-proxy should behave.
- **Verdict:** legitimate to keep as the "how premium is this print" axis, but
  its correlation with price must **never** be presented as validation of the
  desirability thesis. It is the contamination, doing its job of being visible.

### Card Appeal (merged) → **FIX / FLAG the framing**

- **Evidence:** ρ = 0.57 ≈ Treatment (0.58), > Pure Demand (0.37). The headline
  strength is inherited from the rarity proxy; adding demand did not improve on
  Treatment alone.
- **Verdict:** the metric can stay, but **flag** any presentation that uses Card
  Appeal's ~0.57 as the proof point for collector demand — that conflates a
  rarity effect with a demand effect. If Card Appeal is shown, the honest
  companion number is Pure Demand's 0.37 (and its within-band collapse). This is
  the Prompt B honesty issue, foreshadowed here by the numbers.

---

## Data exclusions actually applied in Stage 1 (with counts)

| Exclusion | Rows | Reason |
|---|---|---|
| Non-Pokémon priced cards | ~3,030 (2,656 Trainer, 356 Energy, 17 null-supertype) | No species demand score — cannot compute Pure Demand / Card Appeal |
| Canonical cards with no positive price | 836 | Cannot enter a price correlation |
| Null-rarity priced Pokémon cards (Treatment column only) | 261 | No Treatment Score; kept in Pure Demand / Card Appeal columns |
| Degenerate rank pairing dropped by `corr()` | 1 | 16,277 eligible → 16,276 in the Pure Demand / Card Appeal correlation |

No card was dropped to strengthen any correlation; every exclusion is a
structural "the field does not exist for this row," reported with its count.

## Files created/modified in this pass (nothing committed)

- **New (untracked):**
  - `docs/research/desirability-card-study-results.md` (this results doc)
  - `docs/research/desirability_card_study.sql` (exact queries that produced the
    Stage 1 numbers; read-only)
  - `docs/research/desirability_card_study.py` (standalone Python reproduction
    using scipy; read-only, requires `DATABASE_URL`)
- **Working branch:** `research/desirability-card-study`.
- No app / UI / backend / scoring files were modified. All three components were
  recomputed from raw data using the shipped formulas; the live scoring code was
  read, never changed. Nothing committed or pushed.
