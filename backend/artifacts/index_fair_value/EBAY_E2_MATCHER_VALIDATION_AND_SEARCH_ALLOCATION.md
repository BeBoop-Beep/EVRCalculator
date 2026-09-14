# eBay E2 — D3-v3 Matcher Validation, Search-Allocation Study, Evidence-Quality Contract

## 1. Git SHA / branch

- Branch: `develop`
- HEAD at time of this report: `b087d535878e2ad6a2bc26ad3daf85146a1aa278`
  (one unrelated `updates` commit landed on top of the E1 shadow-collector HEAD
  `6305d4c9` between sessions; not touched here.)

## 2. Files changed

New files only:

- `backend/scripts/benchmark_index_fair_value_ebay_d3.py`
- `backend/scripts/research_index_fair_value_ebay_search_allocation.py`
- `backend/scripts/index_fair_value_ebay_evidence_quality.py`
- `backend/tests/unit/scripts/test_benchmark_index_fair_value_ebay_d3.py`
- `backend/tests/unit/scripts/test_research_index_fair_value_ebay_search_allocation.py`
- `backend/tests/unit/scripts/test_index_fair_value_ebay_evidence_quality.py`
- This report, plus retained research artifacts under
  `backend/artifacts/index_fair_value/ebay_evidence_runs/` (one additional
  bounded live run, `b650bed3...`) and
  `ebay_search_allocation_research_targets.json` (the 4-card target list used
  for that run).

No existing file was modified in its final committed state. (The existing
`certify_ebay_d3_v3.py` was rerun once, in place, to verify reproducibility —
it rewrote its own output artifacts with new timestamps/commit hashes but an
identical substantive result; those two files were reverted to their
committed content with `git checkout --` afterward.)

## 3. Gold-label lineage

| Partition file | Rows | Reviewer/adjudicated columns populated? | Matcher evaluated | Frozen? |
|---|---|---|---|---|
| `ebay_manual_gold_labels.csv` | 1,050 | 0 populated (`review_status`=`PENDING_INDEPENDENT_HUMAN_REVIEW` throughout) | none (source pool) | Yes, hash-matched to `ebay_gold_benchmark_manifest.json` |
| `ebay_gold_development.csv` | 450 | 0 populated in the static CSV columns | v1 → v2 → v3 (re-evaluated at each matcher revision) | Yes |
| `ebay_gold_validation.csv` | 250 | 0 populated | v1, v2 (`build_ebay_d2v_validation_study.py`) — **v3 never evaluated this partition** | Yes, but no `validation_partition_sha256` reference found in any v3 manifest |
| `ebay_gold_final_blind.csv` (D2-era) | 350 | 0 populated | superseded before v3's official certification (see below) | Yes |
| `ebay_d3_precision_blind.csv` | 300 | N/A — schema has no label columns at all | v3 (the "fresh" round actually used for certification) | Yes |
| `ebay_d3_coverage_blind.csv` | 420 | N/A | v3 | Yes |
| `ebay_d3_blind_review_queue.csv` | 704 (= 300+420−16 intentional overlap) | N/A | v3 | Yes |

**The real ground truth lives outside these CSVs**, in append-only JSONL
event logs (`ebay_gold_review_history.jsonl`, 1,878 lines; plus
`ebay_final_blind_gold_audit_history_v1.jsonl` and
`ebay_d3_fresh_gold_audit_history.jsonl`, 53 and 45 lines of post-hoc
corrections respectively), overlaid at evaluation time into an "effective
gold" fingerprint. **Every single label record across every partition has
`"reviewer_id": "Donny"`** — the dual-reviewer + adjudication schema
(`reviewer_1_label`/`reviewer_2_label`/`adjudicated_label`) that the CSV
headers advertise is entirely vestigial and unused. There is, and never was,
an independent second human reviewer for this matcher.

## 4. Reviewer/adjudication counts

- Distinct reviewers across all partitions: **1** ("Donny").
- `reviewer_2_label` / `adjudicated_label` populated anywhere: **0 rows**, in
  any partition.
- Total individually-labeled rows (via the review-history + audit-history
  overlay, not the static CSV columns): 704 for the D3 "fresh" round
  (matches `ebay_d3_fresh_human_gold_manifest.json:effective_row_count`).

## 5. Partition fingerprints (as recorded / reproduced)

```
matcher_fingerprint            b5e44641f35c5f846a8d83bc6c777285f6e07707c9c672feef47c55cd67c95ec
benchmark_design_fingerprint   75505bfcbe2e167821a3178b5da192e1240879fe3e4edd75891fa2c55c02d2c6
precision_cohort_fingerprint   2292c755f3e3563c0d8eb268219fa5863b5243b61093264eec1da991ff1142c5
coverage_cohort_fingerprint    e76e63dbbec489e3f8965dcfcaa9f920d004002632f00095318bc7fbc4c7061a
review_queue_fingerprint       897ad0574f70c649311dc440e0af7a2380cd8d9addaf28b55c2cb1313621ccde
human_gold_fingerprint         635365a6773910f8acb5c57efecba81163e187c147eb34f844a50a71bdf85a8c
```

Rerunning `certify_ebay_d3_v3.py` reproduces the identical `final_result`
(`EBAY_IDENTITY_MATCHER_V3_NOT_VALIDATED`) and identical substantive metrics
— only the `evaluated_at`/`evaluation_code_commit`/manifest-fingerprint
metadata fields change between runs, confirming the pipeline is genuinely
fingerprint-gated and reproducible, not hand-computed.

## 6. Blindness / leakage audit

Chronology (all 2026-09-12/13, converted where noted):

| Event | When (local -07:00 / UTC) |
|---|---|
| `ebay_gold_final_blind.csv` (D2-era split) committed | 2026-09-11 20:03 |
| FINAL_BLIND_TEST initial labeling | 2026-09-12 22:31–22:39 |
| FINAL_BLIND_TEST **post-hoc label corrections** (audit_replace, including a flip to `EXACT_TARGET_MATCH`) | 2026-09-12 22:55–23:13 |
| `ebay_d3_matcher_v3.py` committed and frozen | 2026-09-12 23:34–23:37 |
| Fresh blind capture (precision/coverage/review-queue) | 2026-09-12 23:42–23:45 |
| D3_BLIND_REVIEW (fresh round) initial labeling | 2026-09-13 00:18–00:39 |
| D3 fresh audit corrections | 2026-09-13 03:58–04:10 |
| Final certification run | 2026-09-13 04:22 |

**Explicit answers:**

1. **Were final-blind labels frozen before final evaluation?** Yes, mechanically — the metrics were computed after the labels existed. But the *last human edit* to the final-blind labels landed only ~20 minutes before the matcher itself was frozen, all in one unbroken session by the same person who wrote the matcher.
2. **Was the matcher edited after inspecting final-blind labels?** No commit modifies `ebay_d3_matcher_v3.py` after its single freeze commit (`f744ae4b`, 2026-09-12T23:34:10-07:00) — verified directly via `git log --follow`. `ebay_d2m_matcher.py`/`v2` (which v3 imports unchanged) also show no post-freeze edits.
3. **Was the final-blind cohort independent from development/validation?** At the listing level, yes — zero `listing_item_id` overlap between development, validation, and any blind partition (the only intentional overlap is the documented 16 rows shared between `ebay_d3_precision_blind.csv` and `ebay_d3_coverage_blind.csv`, both subsets of the same 704-row queue by design). **At the card-catalog level, no** — all 70 target `canonical_card_id`s appear in every partition, including final blind. The matcher's per-card rules (variant/alias/product-object logic) were necessarily developed while looking at failure patterns for the exact same 70 cards later scored blind.
4. **Duplicate/near-duplicate items across partitions?** None found beyond the documented 16-row precision/coverage overlap.
5. **Same target cards across partitions with listing independence preserved?** Yes — listing independence holds; card independence does not (see #3).
6. **Was there a second blind round conducted after inspecting the first?** **Yes — this is the most serious finding.** There were two separate "final blind" rounds against the same frozen matcher fingerprint: an original D2-era 350-row round, and a second "fresh" 704-row round captured 9 minutes *after* the matcher's own freeze manifest was committed and labeled by the same reviewer the following morning, by which point that reviewer already knew the matcher's fingerprint and (from the same night's work) its general failure shape. Self-reported flags (`"new_certification_labels_viewed": false"`, `"matcher_predictions_consulted": false`) are unverifiable — there is no cryptographic or third-party attestation backing them, only the honor of the same single person who built everything else in the pipeline.

**Conclusion: independence cannot be fully established.** Listing-level blindness holds; single-reviewer self-labeling and card-catalog-level overlap across every partition, plus a same-person second blind round run after the matcher and first-round results were already known, mean the reported 99.0% point-estimate precision cannot be treated as an independently certified number, even before accounting for the gate failures below. This is consistent with — and independently corroborated by — the pipeline's own certifier already having flagged the result as `EBAY_IDENTITY_MATCHER_V3_NOT_VALIDATED`.

## 7-9. D3-v3 metrics by partition (never combined)

**Development** (450 rows, from `ebay_d3_v3_development_metrics.json`):

| accepted (HIGH) | precision | Wilson-95 lower | recall | card coverage | ambiguity rate | rejection rate |
|---|---|---|---|---|---|---|
| 450 | 99.78% | 98.75% | 67.2% | 87.1% (61/70) | 5.9% | 47.0% |

Catastrophic HIGH errors on development: 1 (`GRADED`).

**Validation**: **NOT EVALUATED for v3.** No `ebay_d3_v3_validation_metrics.json` (or equivalent) exists — the v3 study line went development → fresh blind directly, skipping the validation partition entirely. This is a process gap, reported here rather than silently glossed over.

**Final blind** (fresh round; `ebay_d3_v3_final_certification_metrics.json`, reproduced this session):

Precision cohort (300 HIGH-confidence rows, N sufficient for meaningful power per the pipeline's own `sufficient_effective_power` check):

| accepted precision | Wilson-95 CI | TP | FP |
|---|---|---|---|
| 99.00% | [97.10%, 99.66%] | 297 | 3 |

Coverage cohort (420 rows spanning all 70 cards, 6 rows/card):

| HIGH count | recall | specificity | F1 | card coverage | ambiguity rate | rejection rate |
|---|---|---|---|---|---|---|
| 207 | 83.0% | 98.8% | 0.903 | **78.6% (55/70)** | 2.1% | 45.0% |

## 10. Critical-error table (final blind, both cohorts combined for error counting only — never for precision)

| Category | Count |
|---|---|
| WRONG_CARD_NUMBER | 2 |
| LOT_OR_BUNDLE | 2 |
| SEALED_OR_ACCESSORY | 1 |
| GRADED | 0 |
| RELATED_BUT_WRONG_VARIANT / WRONG_SET / WRONG_LANGUAGE / AMBIGUOUS | 0 |
| **Total critical false accepts** | **5** |
| Critical false-accept rate (of 207 HIGH rows in coverage cohort) | **2.42%** |

Five HIGH-confidence (accepted) predictions were, per human label, actually a
wrong collector number twice, a lot/bundle twice, and a sealed/accessory
product once. **This alone fails the zero-tolerance critical-error gate**,
independent of the precision point estimate.

## 11. Cohort breakdowns

15 of 70 cards (21.4%) had **zero** valid HIGH+exact-match evidence in the
coverage cohort (`cards_with_zero_valid_high_exact` in the certification
metrics) — e.g. Giovanni's Charisma, Kyurem ex, Emboar, Grubbin, Mega
Charizard Y ex. Per-card N is small (6 rows/card in the coverage cohort), so
finer slices (modern/vintage, low/medium/high value, promo numbering, etc.)
would mostly land in single-digit cells — not reported as point estimates
here to avoid manufacturing false precision from tiny N; the one
cohort-level statistic that *is* well-powered and decisive is card coverage
itself (55/70 = 78.6%, below the required minimum).

## 12. Search-page marginal-yield table

From 6 cards' worth of retained/newly-captured E1 evidence (17 live Browse
calls total this session, see §19), primary-formulation results only:

| Page bucket | Requests | Deduplicated listings | Accepted | Accept rate | Accepted/request |
|---|---|---|---|---|---|
| Page 1 | 6 | 551 | 393 | 71.3% | **65.5** |
| Page 2 | 3 | 288 | 135 | 46.9% | **45.0** |

Page 2 accept rate drops by roughly a third relative to page 1, but still
returns real, non-negligible accepted evidence (45/request) — not a cliff to
zero. No card in this sample reached page 3 (the `next` link was exhausted
first).

## 13. Query-strategy comparison

| Formulation | Requests | Deduplicated listings | Accepted | Accept rate | Accepted/request |
|---|---|---|---|---|---|
| `primary` | 9 | 839 | 528 | 62.9% | 58.67 |
| `collector_number_focus` (broad) | 6 | 97 | 71 | 73.2% | 11.83 |

**Zero item-ID overlap** was observed between the two formulations for every
target sampled — the broad query is not returning duplicate volume, it
surfaces a genuinely distinct slice of listings, with a slightly *higher*
accept rate than primary despite returning far fewer results per call.
Collector number + set name presence in the query measurably improves
identity precision (broad formulation's higher accept rate) but primary's
extra terms (edition/printing/"Pokemon card") drive far higher raw recall
per request, which dominates overall efficiency. One strong primary query
comfortably outperforms the broad query on raw efficiency; the broad query
earns its keep purely as a cheap, non-duplicative seller-diversity
supplement, not as a primary-query replacement.

## 14. Recommended daily allocation policy

Implemented deterministically in `research_index_fair_value_ebay_search_allocation.py:allocate()`:

1. **Tier 1 (mandatory):** `primary` formulation, page 1, for every target — highest yield-per-request observed, funded first, always.
2. **Tier 2 (mandatory):** `collector_number_focus` formulation, page 1, for every target — zero-duplication incremental evidence and seller diversity, cheap (1 request/target).
3. **Tier 3 (conditional):** `primary` formulation, page 2 — funded only for targets whose accepted-evidence count is still below a usable floor (default 15) after tiers 1-2.
4. **No page 3+** funded speculatively for any formulation; deeper pages showed rapidly collapsing marginal listings once `next` is naturally near-exhausted.

The allocator guarantees every target its tier-1+tier-2 minimum before any
target receives tier-3 depth, so one noisy/illiquid card pulling extra pages
can never starve the rest of the cohort (tests #12-14 in the new suite).

## 15-16. Projected requests

| Scenario | Requests (70-card cohort) |
|---|---|
| Minimum (tier 1 only) | 70 |
| Typical (tier 1 + tier 2, no target needs tier 3) | 140 |
| Worst case (tier 1 + tier 2 + tier 3 for every target) | 210 |

All three scenarios fit comfortably inside the 1,000-call/day application
budget (worst case uses 21% of it), so there is no pressure to skip tier 3
for cost reasons — the reason to gate tier 3 is evidence quality (avoiding
low-yield noise), not budget scarcity.

## 17. Evidence-quality contract

Implemented in `index_fair_value_ebay_evidence_quality.py`: a typed
`EvidenceQuality` enum (`INSUFFICIENT` / `LOW` / `MEDIUM` / `HIGH`), never a
percentage or probability. Inputs: accepted-listing count, unique-seller
count, seller concentration, price dispersion (coefficient of variation),
condition-known rate, ambiguous-identity rate, evidence age, and whether the
matcher version consulted is production-certified.

**Key design decision driven directly by §3-6/§10 above:** because
`ebay_d3_matcher_v3` is not production-certified
(`EBAY_IDENTITY_MATCHER_V3_NOT_VALIDATED`), matcher-accepted evidence is
*structurally capped at `MEDIUM`* regardless of depth/diversity/dispersion —
`HIGH` requires both a clean evidence bundle *and* a certified matcher
version, which does not exist yet. This keeps "high internal evidence
quality" (a statement about the ask data itself) strictly separate from "high
confidence the ask reflects a sale" (never claimed anywhere in this module).

## 18. Tests / results

45 new/updated tests, all passing, no live dependency:

```
26 passed  -- test_benchmark_index_fair_value_ebay_d3.py (6)
              test_research_index_fair_value_ebay_search_allocation.py (11)
              test_index_fair_value_ebay_evidence_quality.py (9)
19 passed  -- test_index_fair_value_ebay_evidence_collector.py (E1, unchanged)
218 passed -- full backend/tests/unit/scripts -k "ebay or fair_value" (no regressions)
```

## 19. Live calls consumed this session

**17 Browse calls total**, all against retained/new E1 collector infrastructure, well under the 20-request Phase-G ceiling:

- 12 requests: a dedicated 4-card research run (`b650bed3...`) to get page-3-reachable, multi-formulation samples beyond the 2 cards already captured by E1's smoke run, specifically to answer the search-allocation questions from real data rather than guesswork.
- (The E1 smoke run's 5 requests, `ce3dabf3...`, were reused/retained from the prior session, not re-called.)

No credentials were touched. No cohort broadening beyond the existing 70-card D1 universe (the 4 research targets are members of that same cohort).

## 20. Remaining blockers

1. **No second independent human reviewer exists anywhere in this pipeline.** The dual-reviewer/adjudication schema is vestigial. A real production certification needs a second, genuinely independent labeler (ideally blind to the first reviewer's labels and to the matcher's existence).
2. **Card-catalog-level leakage risk** — every partition shares the same 70 target cards as development. A future certification should draw final-blind cards from outside the development/validation card universe, not just outside the listing-ID universe.
3. **The "fresh" second blind round was captured and labeled after the matcher fingerprint and first-round results were already known to the same person.** A new blind round should be captured and sealed by someone (or some process) demonstrably without access to prior results.
4. **5 critical false accepts and 21.4% zero-coverage cards** in the existing final-blind result are real, reproducible failures — not sampling noise — and must be diagnosed via development data before any new matcher revision, per the no-final-blind-tuning rule.
5. **Validation partition was never evaluated for v3** — a gap in the version's own development lineage, independent of the blind-round concerns.

## Final decision

**`EBAY_D3_MATCHER_NOT_CERTIFIED_CRITICAL_FALSE_ACCEPTS_AND_COVERAGE_GATE_FAILURE`**

D3-v3 fails its own pre-registered gates (`wilson_lower`, `coverage`,
`catastrophic` all `false`; only `precision` passes) on a final-blind
evaluation whose independence is itself compromised (single self-labeling
reviewer, card-catalog overlap across all partitions, a same-person second
blind round run after the first round's results were known). The point
estimate of 99.0% precision is not actionable as a production gate result
under these conditions.

**Smallest scientifically valid remediation path (per the no-final-blind-tuning rule):**

1. Diagnose the 5 catastrophic errors and the 15 zero-coverage cards using
   **development data only** (`ebay_gold_development.csv` + its review
   history) — do not open `ebay_d3_precision_blind.csv`/`coverage_blind.csv`
   contents for this.
2. Derive a bounded rule fix for the specific structural causes already
   named in `ebay_d3_v3_high_false_positive_forensics.csv`'s
   `likely_structural_cause` column (multiplicity/selectability detection
   gaps, number-conflict parsing gaps, accessory/sealed-context gaps).
3. Verify the fix against the **validation** partition (not yet used for v3
   at all — a clean, never-touched validation opportunity).
4. Freeze the new matcher version with its own fingerprint.
5. Capture and seal a **brand-new** final-blind cohort — ideally with a
   second, genuinely independent human reviewer, and ideally drawn from a
   card universe not limited to the same 70 development cards — before
   attempting certification again.
6. Also close the process gaps: get a real second reviewer for future rounds, and evaluate the next matcher version against validation before any blind round.

Given this, **E3 (Active-Ask Source Estimator) is not yet scientifically
safe to build on D3-v3's identity output as a trusted filter.** The E1
collector may continue running D3-v3 in its current *diagnostic-only,
non-authoritative* capacity (unchanged from E1), and the evidence-quality
contract in this report already enforces that by capping matcher-derived
evidence at `MEDIUM` quality until a matcher passes an independent
certification.
