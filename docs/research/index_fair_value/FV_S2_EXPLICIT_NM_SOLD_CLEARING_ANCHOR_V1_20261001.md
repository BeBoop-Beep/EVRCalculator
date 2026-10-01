# FV-S2 — Explicit-NM Sold Clearing Anchor V1 (research)

**Status: `FV_SOLD_CLEARING_ANCHOR_RESEARCH_READY_PROSPECTIVE_SHADOW_BLOCKED`**

Research only. `EXPLICIT_NM_SOLD_CLEARING_ANCHOR_V1` is **not** production inDex Fair Value, **not** a
condition-normalization authority, and is not blended with TCGplayer or the structural model. No canonical
price, Set Value, Market Explorer, Rankings/RIP or Collector Appeal surface is touched. The D3 condition
research is independent and unchanged.

Frozen Core Panel `9e3068ffb2e644e3dab2f5c237271afa4efe061ed8f3139187dc9e8331bd1d1f` (207 cards) —
fingerprint recomputed from the manifest, not trusted. Observation date `2026-09-30`.
Evidence label: **`RETROSPECTIVE_BACKFILLED_EVIDENCE`** (see "Temporal semantics").

## Method (contract: `sold_clearing_anchor_v1/methodology_contract.json`)

Eligible comp = persisted sold row where: identity `EXACT`, attribution `exact`, `graded=false`, USD,
provider card id equals the persisted exact identity, **and** the title (a) contains the card number as a
standalone numeric token (`N/M` numerator, `#N`, or bare; a slash *denominator* never counts, leading zeros
ignored), (b) contains `NM` / `Near Mint`, (c) contains none of: LP/MP/HP/damaged/DMG/crease/torn/water damage
(or their long forms), PSA/BGS/Beckett/CGC/SGC/AGS, TAG or ACE followed by a numeric grade, Gem Mint, Black
Label, Pristine, proxy, fan art, custom card/case, extended-art case, no card, sticker, digital, code card, lot,
bundle, repack, metal card.

Anchor = median sale price in the **shortest** trailing window of 7, 30, 60, 90, 180 days containing ≥ 10 eligible
comps (window = exactly *N* calendar days ending on the observation date). Window choice sees only comp counts,
sale dates and the fixed date — `select_anchor` and `_compute_anchors` have no price parameter, a row carrying a
target-price key raises `FV_S2_TARGET_LEAKAGE_GUARD`, and a test proves anchors are unchanged when every target
price is scaled 40×. The TCGplayer NM price observed on 2026-09-30 is loaded after anchors exist and is used only
as the evaluation outcome.

## Reproduction (read-only; 59,050 persisted rows, snapshot sha256 `4becdbbe…507215c`)

| Metric | October 1 finding | Reproduced | |
| --- | ---: | ---: | --- |
| Cards meeting ≥ 10-comp rule | 194 / 207 | **194 / 207** | exact |
| Coverage, price ≥ $25 | 115 / 115 | **115 / 115** | exact |
| Coverage, price ≥ $100 | 52 / 52 | **52 / 52** | exact |
| Uncovered cards | bulk, $0.06–$0.23 | **13 cards, $0.06–$0.23** | exact |
| MdAPE overall | ≈ 9.68% | **9.68%** | exact |
| MdAPE ≥ $25 | ≈ 6.51% | **6.51%** | exact |
| MdAPE ≥ $100 | ≈ 6.27% | **6.27%** | exact |
| MAE ≥ $100 | ≈ $23.32 | **$23.66** | +1.4%, unexplained (below) |
| Pearson(log price, −ln p), 207 cards | ≈ 0.829 | **0.829** | exact |
| Within-set centered correlation | ≈ 0.840 | **0.840** | exact |

Not reproduced in this bucket: the Collector-Appeal / transaction-velocity LOSO R² comparison (0.785 → 0.806/0.807).
It is context only and feeds nothing here.

### Deviations and what caused them

1. **First run did not match, and the cause was my own rule reading.** My first implementation also rejected titles
   carrying a *different* card number (e.g. `…167/131 NM Condition 075/131`) as "exact card-number identity must fail
   closed". The October 1 study did not apply that rule. Diagnosis on Eevee ex 167: removing it moves 14 → 15 comps
   and $157.50 → $147.50, and all nine Prismatic rows then match exactly. I adopted the spec-literal presence rule as
   V1 and kept the stricter variant as a *reported sensitivity* (overall MdAPE 9.71%, ≥ $100 MAE $23.58; 78 eligible
   comps in the panel carry a second card number). It is a candidate tightening, **not applied**.
2. **Window boundary.** "Trailing N days" is ambiguous. Exactly N calendar days reproduced the study; N+1 does not
   (sensitivity: overall MdAPE 9.50%, ≥ $100 MdAPE 6.32%, ≥ $100 MAE $23.21).
3. **Outcome price date.** The latest-price table now holds 2026-10-01. Using it gives 51 / 51 for ≥ $100 and MdAPE
   6.34% — the study used 2026-09-30, so the harness reads the 09-30 observation for the variant and condition the
   canonical price authority selected (all 207 present; all panel variants match).
4. **MAE ≥ $100 ($23.66 vs ≈ $23.32).** The only residual. Counts, windows and anchors for the nine audited cards are
   exact, so it is not the rule. Candidates I could not separate: sold rows ingested after the study, or a
   different MAE convention. 1.4%, immaterial to any conclusion; reported rather than tuned.
5. **`HP` is rejected literally** per the contract. "200 HP" (hit points) titles are therefore false negatives.
   Exempting them leaves every MdAPE unchanged (9.68% / 6.51% / 6.27%) and moves ≥ $100 MAE only $23.66 → $23.63; I kept the contract's fail-closed behaviour.

## Prismatic Evolutions case study (`prismatic_case_study.json`)

| Card | Market 09-30 | Window / comps | Anchor | Anchor err | Structural (ModelC OOF) | Structural err | IQR | Sale days |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Leafeon ex 144 | $331.93 | 60d / 21 | $275.00 | −17.2% | $177.42 | −46.5% | 77.50 | 16 |
| Flareon ex 146 | $203.82 | 90d / 11 | $200.00 | −1.9% | $180.47 | −11.5% | 28.70 | 10 |
| Vaporeon ex 149 | $282.41 | 60d / 10 | $276.03 | −2.3% | $194.57 | −31.1% | 78.74 | 8 |
| Glaceon ex 150 | $269.14 | 60d / 12 | $231.50 | −14.0% | $181.64 | −32.5% | 70.25 | 9 |
| Jolteon ex 153 | $193.91 | 60d / 12 | $167.25 | −13.7% | $177.42 | −8.5% | 34.09 | 11 |
| Espeon ex 155 | $312.32 | 90d / 25 | $289.99 | −7.1% | $265.28 | −15.1% | 60.00 | 19 |
| Sylveon ex 156 | $528.19 | 60d / 21 | $460.00 | −12.9% | $319.98 | −39.4% | 65.00 | 17 |
| Umbreon ex 161 | $1,355.96 | 60d / 10 | $1,530.78 | **+12.9%** | $351.59 | **−74.1%** | 437.29 | 8 |
| Eevee ex 167 | $176.43 | 60d / 15 | $147.50 | −16.4% | $290.50 | **+64.7%** | 44.65 | 13 |

All nine match the October 1 table exactly (counts, windows, anchors, market prices).

### Why the anchor handles Umbreon and the structural model does not

Evidence, not mechanism proof. The structural model is a smooth function of scarcity/appeal/set context; the
anchor reads the card's own clearing prices.
* Tail compression: among ≥ $100 cards the log-log slope of estimate on market price is **1.00 for the anchor and
  0.28 for the structural model** (≥ $25: 1.00 vs 0.82; all cards: 0.81 vs 0.83, where bulk noise dominates).
  Structural median signed error on those 52 cards is −31.8% (MAE $185, MdAPE 49.6%) vs −0.06% (MAE $23.66,
  MdAPE 6.27%) for the anchor.
* Umbreon is ~2.6× the next-priced Prismatic SIR; a shrunk model cannot reach it, a direct comp median needs no
  extrapolation.

Honest limits: Umbreon rests on the **minimum** 10 comps over 8 sale days with an IQR of $437 (≈ 29% of the
anchor), so its +12.9% is within sampling noise and should not be read as a precision claim. The anchor sits
*below* market for 8 of the 9 SIRs (median ≈ −13%) — NM-labeled eBay sales clear under TCGplayer's market price
there; Umbreon is the one sign flip. The structural model *over*-predicts Eevee by 65%, so its failure is not just
tail shrinkage. This is an in-sample, same-panel result.

## Temporal semantics

The 180-day evidence was backfilled after most transaction dates. Every historical figure here is
**`RETROSPECTIVE_BACKFILLED_EVIDENCE`**, not an as-known-then replay. Rules, window set and the ≥ 10 threshold were
developed against this same panel and price outcome, so these are descriptive in-sample numbers, not a
out-of-sample validation. For prospective runs the harness already supports an `information_cutoff`: rows whose
`collected_at` is after the evaluation timestamp (or unknown) are excluded, and results are labelled
`AS_KNOWN_AT_CUTOFF`. Each prospective record must carry `sold_at`, `collected_at`/`ingested_at`, and the
evaluation timestamp.

## Provider metadata drift

`PkmnPricesStore.insert_evidence()` freezes first-seen enrichment: if the provider later turns an ungraded sale
into, say, TAG 9, the economic transaction stays unchanged and only `provider_metadata_drifts` increments.
This work does **not** rewrite evidence (test: a drifted re-ingest leaves the stored row byte-identical and returns
`(0, 1, 1)`).

Does production Fair Value need a versioned enrichment/reconciliation overlay? **Yes, before any production
use.** The immutable row is correct for audit but the *effective* grade/attribution of a sale is exactly what a
price estimator needs, and the receipt counter alone cannot say which comps were affected. The overlay should be
keyed by `(provider_card_id, provider_listing_id)`, append-only, carry `observed_at` and an enrichment version, and
be consumed as-known-at the evaluation time. Not built here. The research anchor protects itself meanwhile: 322
panel rows are `graded=false` yet carry grader/grade evidence in the title and are rejected fail-closed.

## Dormant daily-increment collector (prepared, not activated)

`backend/scripts/run_core_panel_daily_increment.py` · `ACTIVATION_ENABLED = False` · `--commit` exits 78 before
touching credentials, DB or provider; only `--preflight` runs (0 provider calls, 0 writes).

**Gap being closed.** B4 stops a Core Panel card at `phase1_ready`; B5 excludes the completed panel; nothing guarantees
daily newest sales for the 207 cards.

**Design.**
* Eligible only if a cached exact identity exists, the B4 backfill is `CURRENT`/complete, `phase1_ready`, and a
  frontier exists. It never performs identity lookups and never restarts or edits backfill.
* One bounded `date_desc` combined (raw + graded) page per card with `since=<frontier>`. In-repo documentation
  (`PKMNPRICES_SOLD_HISTORY_PERSISTENCE_20260929.md`) states `since` filters on `ingested_at`, so completeness =
  "provider reports the `since` set exhausted", not "page looked old". Rows at/older than the frontier despite `since`
  mean the filter was not honoured → fail closed.
* Frontier starts at B4's `core_panel_incremental_watermark` (read-only) and advances only when exhausted.
* **Overflow:** a full page entirely newer than the frontier continues (≤ 4 pages/card/day) inside the daily cap.
  If the bound hits, an `open_gap` (floor + resume cursor) is persisted and the frontier does **not** advance;
  open gaps are served first next run, so sales cannot be silently skipped.
* Writes: evidence only through `insert_evidence` (append/dedupe); state only under the namespaced key
  `core_panel_daily_increment` in the sync metadata (every pre-existing field and the B4 cursor keys are asserted
  unchanged); run row with `mode=core_panel_daily_increment_v1`.
* Same gates as B5: DB-safety hold before and after locks, lock order active-supply → scrape-dispatcher → provider
  → publication (test compares against the B5 wrapper), release-pin check, scrape/C-continuity pause rules
  re-checked before every page. The wrapper `infra/oracle/run_core_panel_daily_increment.sh` is not installed; the
  crontab is `*.crontab.DISABLED` with the only entry commented out and no installer is provided.

**Credit bound (derived from code constants, asserted at runtime and in tests).**

| Consumer | Daily hard cap | Source |
| --- | ---: | --- |
| B5 | 55,000 | `DAILY_B5_CREDIT_CAP` |
| Active supply C | 4,500 | `FULL_PANEL_CREDIT_CAP` (projected ≈ 4,140) |
| Vintage-gap collector | 600 | `--item-credit-cap 600` in the workflow (tested) |
| **Core Panel increment** | **8,000** | = 4,140 mandatory one-page pass + 3,860 bounded overflow |
| **Committed total** | **68,100** | of the 75,000 ceiling → **6,900 unallocated** (≥ 5,000 required) |

Uncapped worst case would be 207 × 4 × 20 = 16,560; the 8,000 cap is enforced per invocation (pre-page check against
20-credit worst case) and across invocations (prior same-day increment credits), and shrinks further if other
consumers have already spent beyond contract. A provider `x-credits-limit` other than 75,000 halts the run.
The conservative accounting test bills the requested limit rather than returned rows and still stays ≤ 8,000.

## Verification

See handoff for exact commands and results. Research mode: zero provider calls and zero credits (the module imports
no provider client; the DB handle exposes only `select`), zero DB writes (`ReadOnlyClient` raises on any write
surface; 229 SELECTs), no B4/B5 state touched, no canonical authority touched, deterministic artifacts (byte-identical
re-run), panel fingerprint recomputed and tamper-tested.

## Remaining blockers before a prospective Fair Value shadow

1. Collector activation: reviewed flip of the flag, VM release pin, scheduler install — all explicitly out of scope.
2. The `since` / `date_desc` semantics and per-item vs per-limit billing are taken from repo docs and unverified
   without a provider call; a one-card canary (a few credits) needs explicit approval.
3. Initial catch-up debt: sales ingested between B4's watermark and activation must be recovered; may take several
   bounded days.
4. A shadow prediction ledger with pre-registered rule version, evaluation timestamps and no-tuning guard does not
   exist yet.
5. Enrichment/reconciliation overlay decision (above).
6. Result is in-sample and retrospective; explicit-NM coverage beyond the 207-card panel is unmeasured.
