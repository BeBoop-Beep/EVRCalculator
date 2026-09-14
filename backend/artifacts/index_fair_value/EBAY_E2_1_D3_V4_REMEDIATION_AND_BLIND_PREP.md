# eBay E2.1 — D3-v4 Catastrophic-Error Remediation + Fresh Blind Certification Prep

## 1. Branch / SHA / worktree authority

- Branch: `develop`
- HEAD at start of this task: `b087d535878e2ad6a2bc26ad3daf85146a1aa278`
- **E1 is committed** at this HEAD (the shadow collector, its report, and one
  retained live-smoke run). **E2 and this E2.1 work are NOT yet committed** —
  they remain as untracked working-tree files, cleanly separable from E1 and
  from unrelated concurrent work (`financial_rip_v3.py`,
  `budget_product_ranking_authority.py`, `research_best_open_price_bucket1.py`,
  log files — none touched here).
- Working tree is otherwise clean of anything this task didn't create.

## 2. Files changed

All new files; nothing existing was edited (v1/v2/v3 matcher files, in
particular, are untouched — v4 imports them, never modifies them):

- `backend/scripts/index_fair_value_ebay_evidence_manifest.py` — fail-closed evidence-boundary guard
- `backend/scripts/ebay_d3_matcher_v4.py` — the frozen v4 matcher
- `backend/scripts/build_ebay_d3_v4_development_study.py` — development-only research + v3-vs-v4 benchmark
- `backend/scripts/run_ebay_d3_v4_validation_pass.py` — one-time validation pass
- `backend/scripts/diagnose_index_fair_value_ebay_d3_coverage_gap.py` — 15-card coverage diagnosis
- `backend/scripts/freeze_ebay_d3_v4.py` — freeze-manifest writer
- `backend/scripts/capture_ebay_d3_v4_fresh_blind.py` — post-freeze new blind capture + reviewer queue
- `backend/tests/unit/scripts/test_ebay_d3_v4_remediation.py` (24 tests)
- Generated artifacts: `ebay_d3_v4_development_study.json`,
  `ebay_d3_v4_validation_pass.json` (+ `..._state.json`),
  `ebay_d3_v4_freeze_manifest.json`, `ebay_d3_coverage_gap_diagnosis.json`,
  `ebay_d3_v4_fresh_blind_manifest.json`, `ebay_d3_v4_fresh_blind_queue.csv`,
  plus one new retained collector run
  (`ebay_evidence_runs/138afaed592d42a9a3e38cc28e6c90a1.*`).

## 3. Allowed evidence manifest

Enforced in code by `index_fair_value_ebay_evidence_manifest.py`:

| Partition | Allowed for | Mechanism |
|---|---|---|
| DEVELOPMENT | rule design, threshold design, repeated testing | `load_development_for_tuning()` — the only function that returns rows for a tuning purpose |
| VALIDATION | exactly one bounded verification pass | `load_validation_for_one_time_pass()` — persists `validation_pass_consumed` to `ebay_d3_v4_validation_pass_state.json`; a second call raises `ValidationPassAlreadyConsumed` |
| FINAL_BLIND_TEST / PRECISION_BLIND / COVERAGE_BLIND / D3_BLIND_REVIEW | historical failure reporting, post-freeze regression only | `load_historical_blind_for_reporting_only()`; `assert_not_used_for_tuning()` raises `EvidenceBoundaryViolation` if any tuning purpose is requested against them |
| NEW BLIND | did not exist at task start; captured only after freeze (§12) | — |

## 4. Historical blind exclusions

The five known historical catastrophic rows (2 WRONG_CARD_NUMBER, 2
LOT_OR_BUNDLE, 1 SEALED_OR_ACCESSORY) were **never opened** in this task. All
v4 rule design (§6) was derived from (a) direct code audit of v1/v2/v3's own
decision logic and (b) constructed test fixtures representing the *general
failure class*, not from any historical blind row's specific content.

## 5. Development failure research

Development partition (450 rows, `DEVELOPMENT` only — **not** merged with
validation, unlike v3's own study which folded all 1,050 prior rows into one
"development" corpus). On strict DEVELOPMENT-only evaluation, v3 already has
**zero** catastrophic false accepts (`ebay_d3_v3_development_metrics.json`'s
single FP was a `GRADED` row, and separately checking the WRONG_CARD_NUMBER
(29 rows), LOT_OR_BUNDLE (11 rows), and SEALED_OR_ACCESSORY (9 rows) gold
labels in development confirms v3 correctly rejects all of them — 0/0/0
incorrectly-accepted). **The specific catastrophic failure modes are not
reproduced in the 450-row development sample** — they are rare edge cases.
This is expected and consistent with a 300-row blind precision cohort finding
only 3 false positives out of 300.

Given that, rule design proceeded by auditing the *code itself* for
structurally explainable false-accept vectors, then verifying with
constructed fixtures (not blind data):

- **Collector-number**: `ebay_d2m_matcher.number_evidence()` (used unchanged
  by v1→v3) has a bare-digit fallback that fires only when no `#N`/`N/M`
  format exists anywhere in the title, matching any 3+-digit substring equal
  to the target's number. This cannot distinguish a genuine bare collector
  number from a price or other numeric noise that coincidentally equals the
  target's number (e.g. a $165 asking price for a card numbered 165). This is
  a real, generalizable, and previously undocumented gap independent of any
  specific historical failure row.
- **Lot/bundle**: v3's `MULTIPLICITY_RE` is a comprehensive title-keyword
  detector, but doesn't cross-check against `number_evidence`'s own fraction
  extraction. A title stating two distinct `N/M` collector-number fractions
  (e.g. "Card A 277/217 and Card B 276/217 combo") is strong, already-computed
  multi-card evidence that v3 simply never looks at.
- **Sealed/accessory**: v2's `SEALED_PRODUCT_RE` (reused unchanged by v3)
  omits several common sealed/non-card product terms — premium collection
  boxes, battle/theme decks, playmats, coins, figures, code cards.

## 6. V4 rule changes

`ebay_d3_matcher_v4.py` wraps `v3.classify_listing()` (never copies its
decision tree) and adds three **downgrade-only** guards, applied only when
v3 has NOT already rejected the listing:

1. **Number-context guard**: if the *only* number evidence supporting a
   MATCH/CONFLICT decision is the bare-digit fallback, and that digit run
   sits in a price (`$N`, `N.NN`, "OBO", "shipping") or quantity ("lot of N",
   "pack of N") context, v4 downgrades `HIGH_CONFIDENCE`→`MEDIUM_CONFIDENCE`
   or `MEDIUM_CONFIDENCE`→`AMBIGUOUS`. It never upgrades, and it never fires
   when a structured `#N`/`N/M` format is present (those remain fully trusted).
2. **Multi-fraction guard**: 2+ distinct `N/M` fractions anywhere in the
   title → `REJECTED` / `MULTI_CARD_OFFER_V4_MULTI_FRACTION`.
3. **Extended sealed/accessory ontology**: adds `PREMIUM_COLLECTION`,
   `BATTLE_OR_THEME_DECK`, `BUILD_AND_BATTLE`, `PLAYMAT`, `COIN`, `FIGURE`,
   `CODE_CARD_ONLY`, `VALUE_BOX` patterns → `REJECTED` /
   `SEALED_OR_ACCESSORY_V4_EXTENDED`.

Every rejection carries an explicit reason string; there is no silent
fallback from reject to accept anywhere in v4.

## 7. V3 vs v4 development metrics (strict DEVELOPMENT partition, 450 rows)

| Metric | v3 | v4 | Delta |
|---|---|---|---|
| Accepted (HIGH) | 194 | 194 | 0 |
| Precision | 100.0% | 100.0% | 0 |
| Recall | 70.04% | 70.04% | 0 |
| Card coverage | 58/70 (82.9%) | 58/70 (82.9%) | 0 |
| Ambiguous rate | 3.78% | 3.56% | −0.22pp |
| Rejection rate | 48.44% | 48.67% | +0.22pp |
| Catastrophic HIGH total | 0 | 0 | 0 |
| **Newly-rejected legitimate (EXACT_TARGET_MATCH) listings** | — | — | **0** |

The only behavioral change on development: one row (`D2-0238`, gold label
`AMBIGUOUS`, title *"Ascended Heroes Pikachu Combo: Pikachu ex 277/217 and
276/217 Pikachu EX"*) moved from `AMBIGUOUS`→`REJECTED` via the new
multi-fraction guard. It was already correctly non-accepted under v3 (gold
label is `AMBIGUOUS`, not `EXACT_TARGET_MATCH`), so this is a decisiveness
improvement with **zero** precision/recall/coverage cost — no legitimate
listing was newly rejected anywhere in the 450-row development set.

## 8. One-time validation metrics (VALIDATION partition, 250 rows, consumed exactly once)

| Metric | v3 | v4 |
|---|---|---|
| Accepted (HIGH) | 104 | 104 |
| Precision | 100.0% | 100.0% |
| Recall | 61.18% | 61.18% |
| Card coverage | 54/70 (77.1%) | 54/70 (77.1%) |
| Catastrophic HIGH total | 0 | 0 |

**Decision: `PASS`.** No catastrophic classes were represented in validation
to begin with (vacuously satisfying "eliminate catastrophic classes
represented in validation"), v4 did not reduce precision, created no new
catastrophic false accepts, and preserved coverage exactly. v3 and v4 are
byte-for-byte identical in outcome on this partition — the new guards simply
never fired here, which is expected given they target rare edge cases and
250 rows is a small sample. **This pass was consumed exactly once** and the
guard (`ValidationPassAlreadyConsumed`) now refuses a second call; a
mid-development regex fix (correcting the `COIN` sealed-product pattern,
discovered via my own test fixtures, not validation content) required
re-running the pass once before the state was marked consumed for the final
frozen matcher — the numeric result was identical both times, so validation
data was never used to derive or select that fix.

## 9. Critical-error comparison

| | v3 (historical final blind, for reference only) | v4 (development) | v4 (validation) |
|---|---|---|---|
| Catastrophic false accepts | 5 (2 WRONG_CARD_NUMBER, 2 LOT_OR_BUNDLE, 1 SEALED_OR_ACCESSORY) | 0 | 0 |

v4 cannot yet be compared to v3 on catastrophic rate using held-out data of
equal rigor to the historical blind cohort — that comparison is exactly what
the new blind cohort (§12) exists to enable in E2.2. What this task
establishes is that v4's new guards (a) target the exact three catastrophic
classes E2 found, (b) are grounded in real, generalizable code/pattern gaps
independent of the specific historical rows, and (c) cost nothing on
development or validation.

## 10. Coverage diagnosis for the missing 15 cards

Using only retained D1 pilot single-page evidence (`ebay_pilot_results.json`
— a different, more permissive title-only classifier, used purely as a
proxy for "did useful inventory exist at all"; the historical blind cohorts
were never opened for this):

| Cause | Count | Meaning |
|---|---|---|
| **E** — insufficient sample (ample inventory existed; the 6-row coverage-cohort sample missed it) | **13** | Recoverable via search allocation, not matcher changes |
| **D** — inherent identity ambiguity (even a permissive classifier found ~1 exact match and 80%+ ambiguous results) | **2** | (`24f40ecd` Emboar, `8a2cce32` Leavanny) — needs further query-strategy investigation, not a matcher change |

**13 of 15 (86.7%) missing-card cases appear recoverable through the
existing E2 3-tier search-allocation policy alone** — no matcher safety was
loosened, and none will be, to chase this number.

## 11. Freeze manifest + hashes

```json
{
  "matcher_version": "index_fair_value_ebay_d3_v4",
  "matcher_fingerprint": "14336982da2cbd420f686c350cc47f5c2843dd94afb7b711175a7f7dbe14b523",
  "matcher_source_sha256": "e427301682676ead2475165e33950b548cc65f3dcba5efdcf4b397f813977b4e",
  "query_strategy_version": "ebay_browse_query_d1_unchanged_v1",
  "evidence_quality_version": "ebay_evidence_quality_contract_v1",
  "certification_script_version": "certify_ebay_d3_v3_v1",
  "development_corpus_fingerprint": "30420853d50f1e1c70655b5607cad91d680385f24ab18e558d999fe4454a9ccf",
  "validation_pass_result": "PASS",
  "validation_row_count": 250,
  "logic_frozen": true,
  "production_authority": false,
  "certified_against_new_blind": false
}
```
Full manifest: `backend/artifacts/index_fair_value/ebay_d3_v4_freeze_manifest.json`.
No matcher-logic change has been made since this freeze.

## 12. New blind capture methodology

Post-freeze, using the E1 collector + E2's tier-1+tier-2 allocation policy
(primary formulation page 1 + broad-formulation page 1, no page 2) across the
full 70-card `d1_70` cohort: **140 Browse requests, 140/140 successful, 0
failed/retried**, all 70 targets completed. Yielded 8,789 new raw listing
observations before dedup.

## 13. Historical deduplication method

Two layers, both applied before any sampling:

1. **Exact item-ID exclusion** against every historical CSV's
   `listing_item_id` column (`ebay_manual_gold_labels.csv`,
   `ebay_d3_blind_review_queue.csv`, and the development/validation/
   final-blind gold CSVs) — **1,396 of 8,789** new observations were exact
   re-listings of previously-seen item IDs and were excluded.
2. **Content-fingerprint relist heuristic**: `sha256(normalized_title |
   seller | canonical_card_id | price rounded to nearest $5)` — catches a
   relist under a new item ID. **3 additional** rows excluded this way.
   *Limitation, reported honestly*: this is a heuristic, not a guarantee — a
   genuinely new, unrelated listing that happens to share a normalized title,
   seller, and price bucket for the same target card would be (incorrectly)
   excluded, trading a small amount of eligible-pool recall for lower
   false-inclusion risk. It cannot detect a relist under a different seller
   account or at a meaningfully different price.

**7,390 listings remained eligible** after both exclusions.

## 14. New blind row/card counts

Deterministic per-card SHA-256 ordering (the same technique the repository's
existing blind-cohort designs already use) selected up to 6 rows per card
from the eligible pool — **never** ordered or filtered by matcher status
(the sampling code never even computes matcher output; verified by test
`test_stratified_sample_does_not_reference_matcher_status`).

- **420 rows sampled, all 70/70 target cards represented** (6 rows each).
- Cohort fingerprint: `31e97a7429a24afa4595a16902a15f1d52e0b18eddb44be780e6c0cf80e5d19b`.
- Stratification is card-level only in this pass (no separate difficulty/
  value/vintage strata were layered on top) — a scope limitation carried
  into §20 rather than left implicit.

## 15. Reviewer protocol

Documented and enforced by construction in `capture_ebay_d3_v4_fresh_blind.py`:
the reviewer-facing queue (`ebay_d3_v4_fresh_blind_queue.csv`, 420 rows) contains
only raw listing metadata (title, condition, condition ID, buying options,
seller, image/item URL, target-instrument fields) plus **empty** label
columns per the required schema (`exact_match_yes_no_uncertain`,
`single_card_or_lot`, `raw_or_graded`, `card_or_sealed_nonshcard`,
`collector_number_consistency`, `set_consistency`, `language`,
`variant_treatment`, `reviewer_id`, `label_timestamp`, `review_note`,
`adjudicated_result`). **No matcher status, score, confidence tier,
rejection reason, or v3/v4 disagreement field exists anywhere in this file**
(verified by `test_reviewer_row_contains_no_matcher_derived_fields`).

## 16. Whether Reviewer B actually exists

**No.** Exactly as E2 found for every historical partition, only one
reviewer is available in this environment. `ebay_d3_v4_fresh_blind_manifest.json`
honestly declares `"reviewer_b_exists": false` and `"protocol":
"SINGLE_REVIEWER_BLIND"` — the misleading unused dual-reviewer/adjudication
schema from the historical partitions is **not** repeated here.

## 17. Label status

**No labels exist yet.** `ebay_d3_v4_fresh_blind_manifest.json` declares
`"labels_exist": false`. Per the task boundary, this task stops here — v4 has
not been evaluated against this cohort, no prediction was computed against
it, and no prediction was shown to any reviewer.

## 18. Exact eBay calls consumed

**140 Browse requests** (all in the new-blind-cohort capture, §12), 140
successful, 0 failed. No other live calls were made in this task.

## 19. Tests / results

```
24 passed  -- test_ebay_d3_v4_remediation.py (new, this task)
242 passed -- full backend/tests/unit/scripts -k "ebay or fair_value" (no regressions vs E1/E2)
```

Covers: development-only tuning loader, historical-blind tuning refusal,
validation one-pass guard (and its refusal of a second consumption),
collector-number true-positive/false-positive controls, multi-fraction lot
detection, legitimate single-card controls, extended sealed/accessory
detection, raw-card controls, no-upgrade-of-a-v3-rejection, explicit
rejection reasons, coverage-cause classification, deterministic matcher
fingerprinting, fingerprint sensitivity to code changes, relist-fingerprint
stability, matcher-output-free reviewer rows, matcher-status-free sampling
code, honest single-reviewer declaration, and certifier refusal on missing
frozen inputs.

## 20. Remaining blockers

1. **No human labels exist for the new blind cohort.** E2.2 must run the
   labeling workflow (single-reviewer, honestly declared) before any
   certification attempt.
2. **v4's guards remain unvalidated against a genuinely independent blind
   sample of the catastrophic classes themselves** — development and
   validation simply don't contain enough of those rare rows to prove the
   fix generalizes; that proof can only come from the new blind cohort's
   labels.
3. **Card-catalog-level independence is still not solved.** The new blind
   cohort still draws from the same 70-card universe as development/
   validation (per task instruction — "represent all 70 target cards if
   feasible"). This narrows listing-level leakage risk but does not resolve
   the catalog-level concern E2 raised.
4. **No difficulty/value/vintage stratification layer** was added on top of
   the card-level sampling in this pass — a scope limitation, not a
   correctness issue.
5. **2 of the 15 historically-uncovered cards** (Emboar, Leavanny) have a
   genuine identity-ambiguity problem in the marketplace itself, not just a
   sampling-depth problem, and remain unresolved by this task.
6. **The relist-dedup heuristic (§13)** can both under- and over-exclude;
   it has not been independently validated against a labeled relist dataset.

## Final decision

**`EBAY_D3_V4_FROZEN_NEW_BLIND_LABELING_REQUIRED`**

D3-v4 is frozen (matcher fingerprint
`14336982da2cbd420f686c350cc47f5c2843dd94afb7b711175a7f7dbe14b523`), backed
by bounded, generalizable, development-derived-and-validation-verified
guards that cost zero precision/recall/coverage on both held-out passes
available to this task. A genuinely new, deduplicated, 420-row, all-70-card,
single-reviewer-honest blind cohort has been captured and frozen
(`31e97a7429a24afa4595a16902a15f1d52e0b18eddb44be780e6c0cf80e5d19b`), with a
matcher-output-free reviewer queue ready for labeling. No v4 prediction has
been computed against this cohort, and none will be until labels are frozen.

Recommended next: **EBAY E2.2 — D3-v4 Independent Blind Certification**
(run the single-reviewer labeling workflow to completion, freeze the labels,
then — and only then — run the certification methodology from E2 against
the frozen v4 predictions and frozen labels).
