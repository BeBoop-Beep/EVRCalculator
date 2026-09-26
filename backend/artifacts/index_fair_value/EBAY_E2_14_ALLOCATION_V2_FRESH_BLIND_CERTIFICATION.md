# EBAY_E2_14 — Final Fresh-Blind Certification Under CAPTURE-ALLOCATION-v2

**Final decision:** `EBAY_COMBINED_IDENTITY_V2_ALLOCATION_V2_FRESH_BLIND_NOT_CERTIFIED_CATASTROPHIC_FALSE_ACCEPTS_EQ_0`

(The certification script's own gate dictionary names `wilson_lower_ge_0_98` first by insertion order — both it and the catastrophic gate genuinely fail — but the catastrophic gate is the more severe, safety-critical failure and is named as primary here, consistent with how every prior report in this series has treated catastrophic false accepts as the non-negotiable gate.)

Worktree `D:\EVRCalculator-ebay-e2.9`, branch `feature/ebay-e2.9-image-veto-tiered-identity`, HEAD unchanged. Nothing staged, committed, or pushed. No matcher, image verifier, policy, allocation, or human-label change was made in this task.

## 1. Every precondition (independently recomputed, not trusted from the prompt)

All 20 preconditions (the 19 named + the explicit "prior evidence excluded" check) were independently recomputed from the real files on disk before any scoring occurred:

| # | Precondition | Result |
|---|---|---|
| 1 | Queue row count = 553 | ✓ |
| 2 | Target universe = 70 | ✓ |
| 3 | Represented target cards = 70 | ✓ |
| 4 | Cohort fingerprint matches (`5dd90629...a1b769c74`) | ✓ |
| 5 | Final human freeze exists (`finally_frozen: true`) | ✓ |
| 6 | Final label fingerprint recomputes exactly (`0ef9e380...202fda374`) | ✓ |
| 7 | Correction-history fingerprint matches (`49289e18...83a9bee378`) | ✓ |
| 8 | Labels complete (`labels_exist: true`) | ✓ |
| 9 | Review session = `e2_13_session_1` | ✓ |
| 10 | Session not invalidated | ✓ |
| 11 | D3-v5 fingerprint matches frozen | ✓ |
| 12 | IMAGE-v2 fingerprint matches frozen | ✓ |
| 13 | COMBINED-v2 fingerprint matches frozen | ✓ |
| 14 | CAPTURE-ALLOCATION-v2 fingerprint matches frozen | ✓ |
| 15 | Canonical-resolution fingerprint matches | ✓ |
| 16 | Capture occurred after allocation-v2 freeze | ✓ |
| 17 | E2.9B and all prior evidence excluded (0 overlap, measured) | ✓ |
| 18 | No model outputs in the human queue | ✓ |
| 19 | No post-final-freeze human-label mutation (queue mtime coincides with freeze timestamp to the millisecond; independently confirmed by #6's exact fingerprint match) | ✓ |

**All 19+ preconditions verified true. No `EBAY_E2_14_CERTIFICATION_BLOCKED` condition occurred.** Effective label counts also independently verified from the live queue: **YES=336, NO=215, UNCERTAIN=2** — matching the claim exactly.

## 2. Phase 1 — Score (label-blind)

`backend/scripts/run_ebay_e2_14_fresh_blind_scoring.py` reused the identical, already-proven scoring logic from E2.9C's scoring script (`score_row()`), retargeted at the E2.13 queue. Ran the real frozen D3-v5 + IMAGE-v2 + COMBINED-IDENTITY-v2 stack against all 553 rows, `2026-09-16T04:19:16Z` → `2026-09-16T04:21:34Z` (~2m18s).

- **Prediction artifact:** `backend/artifacts/index_fair_value/ebay_e2_14_fresh_blind_predictions.json`
- **Predictions fingerprint:** `5f17182ab6247ca6aa0fce117488a7873595195c0031e4abe46e5e2a369c1b25` — written and fingerprinted before any label was read; re-verified byte-for-byte at the start of Phase 2 before evaluation proceeded.

## 3. Phase 2 — Evaluate

`backend/scripts/run_ebay_e2_14_fresh_blind_certification.py` joined the frozen predictions to the frozen labels by `row_id` only after re-confirming the predictions fingerprint. UNCERTAIN rows (2 total) were excluded from every definitive metric and never coerced to YES/NO — both are reported separately (Section 4).

## 4. Certification metrics (definitive rows only, unrounded for gate evaluation)

| Metric | Value |
|---|---|
| Definitive row count | 551 (553 − 2 UNCERTAIN) |
| Accepted count | 259 |
| True accepts | 258 |
| **False accepts** | **1** |
| Rejected count | 292 |
| True rejects | 214 |
| False rejects | 78 |
| Accepted precision | 0.9961389961389961 |
| Wilson 95% lower bound | **0.9784576202034251** |
| Recall | 0.7678571428571429 |
| Row acceptance rate | 0.47005444646098005 |
| **Distinct card coverage** | **0.8285714285714286** (58/70) |

**UNCERTAIN rows (reported separately, excluded above):**

| | Value |
|---|---|
| Uncertain count | 2 |
| Uncertain accepted | 0 |
| Uncertain rejected | 2 |

## 5. Tier-specific metrics

| | Tier A | Tier B |
|---|---|---|
| Accepted count | 140 | 119 |
| True accepts | 140 | 118 |
| **False accepts** | 0 | **1** |
| Precision | 1.0 | 0.9915966386554622 |
| Distinct cards covered | 50 | 51 |
| Distinct cards incrementally recovered beyond Tier A | — | **8** |

Tier B is reported here as `TEXT_VERIFIED_IMAGE_UNVERIFIED` — never described as image-verified. **The single false accept occurred in Tier B, not Tier A.**

## 6. Card coverage (fixed 70-card denominator)

- Tier-A-covered card IDs: 50
- Tier-B-only incremental card IDs: 8
- **All covered card IDs: 58**
- **All uncovered card IDs: 12** (includes Pecharunt ex, which was only 1/8-sampled per E2.13's honestly-reported shortfall)
- **Final card coverage: 58 / 70 = 0.8286** — computed against the fixed 70-card universe, never the definitive-row count.

**This gate PASSES** (≥56/70 required).

## 7. False-accept forensics

**Exactly one accepted human-NO row** — reported in full, not hidden inside the aggregate precision number:

| Field | Value |
|---|---|
| row_id | `E13-0127` |
| Canonical target | Pikachu ex, Ascended Heroes #277 |
| Listing title | "PIKACHU EX #277 POKEMON ASCENDED HEROES - MINT/NEAR MINT" |
| Human NO reason | **WRONG_LANGUAGE** |
| D3-v5 state | HIGH_CONFIDENCE (no text contradiction — the title itself contains no language marker at all) |
| IMAGE-v2 state | UNVERIFIED |
| Combined tier | TIER_B (`TEXT_VERIFIED_IMAGE_UNVERIFIED`) |
| Canonical-resolution identity | `2c445258-b198-43de-b710-0921ebe3f0ab` (correct card/set/number — the canonical reference itself is not in question) |
| Exact reason the frozen policy accepted it | D3-v5 has no language-detection signal beyond its `NON_ENGLISH_RE` title-text check, which found no non-English text in this **English-language listing title** (the title is a standard English seller description) — the card **pictured** is presumably a non-English print, which the seller's title does not disclose in a way regex text-matching could ever catch. IMAGE-v2 returned UNVERIFIED (not MISMATCH), so it did not independently catch this either — a language variant of the same card art is visually near-identical in embedding space, which is exactly the kind of signal DINOv2-based visual similarity is not designed to distinguish. Tier B accepted the row because HIGH_CONFIDENCE text + no contradiction + UNVERIFIED image is, by the frozen policy's own definition, eligible. |

**Classification: WRONG_LANGUAGE.** This is potentially catastrophic per the standing contract (any exact-instrument identity false accept is potentially catastrophic) and is reported individually here, not smoothed into the 0.996 aggregate precision number.

**No threshold, policy, resolver, matcher, image, or allocation change was made in response to this finding** — per the explicit "no post-hoc changes" instruction, this failure is reported as a failure.

## 8. Locked four gates — exact, unrounded evaluation

| Gate | Requirement | Observed | Result |
|---|---|---|---|
| Accepted precision | ≥ 0.99 | 0.9961389961389961 | **PASS** |
| Wilson 95% lower bound | ≥ 0.98 | 0.9784576202034251 | **FAIL** |
| Card coverage (denominator 70) | ≥ 0.80 (≥ 56/70) | 58/70 = 0.8286 | **PASS** |
| Catastrophic false accepts | == 0 | 1 | **FAIL** |

**Two of four gates fail.**

## 9. Comparison to E2.9C (context only — not used to tune this run)

| | E2.9C (414 rows, 6/card) | E2.14 (553 rows, 8/card) | Change |
|---|---|---|---|
| Accepted count | 185 | 259 (definitive) | **+74** |
| Accepted precision | 1.0 | 0.9961 | −0.0039 (the new false accept) |
| Wilson lower | 0.97966 | 0.97846 | slightly lower, despite a larger sample — the one false accept costs more than the larger n gains |
| Card coverage | 54/70 (0.7714) | **58/70 (0.8286)** | **+4 cards** |
| Catastrophic false accepts | 0 | **1** | regression |

**Deeper allocation (CAPTURE-ALLOCATION-v2's 8 rows/card) did measurably improve both accepted sample size (+74) and card coverage (+4 cards, clearing the 56/70 requirement) — exactly the hypothesis E2.12 set out to test, and it worked for coverage.** But it also surfaced a genuine, rare, previously-unseen catastrophic failure mode (a language mismatch invisible to both current text and image checks) that the smaller 414-row E2.9B cohort never happened to contain. This is not a flaw introduced by the deeper allocation — it is real evidence the deeper allocation *found*, which a smaller sample had simply not yet encountered. E2.9C was not used to tune anything about this run; this comparison is reported for context only, after the fact.

## 10. Artifacts

- `backend/artifacts/index_fair_value/ebay_e2_14_fresh_blind_predictions.json`
- `backend/artifacts/index_fair_value/ebay_e2_14_fresh_blind_certification.json`
- This report

All record `production_authority: false`.

## 11. Tests

`backend/tests/unit/scripts/test_ebay_e2_14_fresh_blind_certification.py` — 26 tests, all passing, covering all 25 required areas: precondition-failure simulation for every named fingerprint (cohort, final-label, correction-history, D3-v5, IMAGE-v2, COMBINED-v2, allocation-v2, canonical-resolution — each via a tampered-copy monkeypatch that never touches the real files), Phase-1 label-blindness (source-verified), prediction-fingerprint-before-evaluation, UNCERTAIN exclusion from definitive metrics (with the real 2-row count), Tier A/B accounting against the real result (including the real 1 false accept), false-accept full-forensics recording, card de-duplication invariants, fixed-70 coverage denominator, the 56/70-passes / 55/70-fails boundary, Wilson calculation against known values, the real catastrophic-gate failure, immutability of the predictions file during evaluation, no production/Fair-Value/Explorer writes, and frozen-authority fingerprints unchanged.

Two pre-existing E2.13 tests (`test_new_session_starts_empty`, `test_no_model_outputs_in_real_queue`) asserted a "before labeling" snapshot (`reviewed_count == 0`, all labels blank) that is no longer true now that E2.13 has been genuinely, legitimately labeled and frozen — updated to check the permanent invariants that remain true (correct session identity; no *model/policy* output ever appears in the queue) rather than a point-in-time fact that time has moved past.

```
python -m pytest backend/tests/unit/scripts/test_ebay_e2_14_fresh_blind_certification.py -q
26 passed

python -m pytest backend/tests/unit/scripts/test_ebay*.py -q
833 passed, 1 failed (pre-existing, unrelated CRLF byte-hash artifact,
documented unchanged from HEAD across every prior E2.9.x/E2.1x report)
```

## 12. Status

**NOT CERTIFIED.** Precision and coverage gates pass with real margin; Wilson lower bound and — decisively — the catastrophic-false-accept gate both fail. Per the explicit "no post-hoc changes" rule, no remediation was attempted in this task. Fair Value and Market Explorer dependent valuation work **remain BLOCKED**. Index Fair Value is **not** unblocked for E3. No production authority was or is activated.

---

## Final result

**`EBAY_COMBINED_IDENTITY_V2_ALLOCATION_V2_FRESH_BLIND_NOT_CERTIFIED_CATASTROPHIC_FALSE_ACCEPTS_EQ_0`**

CAPTURE-ALLOCATION-v2 delivered exactly what E2.12 hypothesized on the coverage axis — card coverage rose from 54/70 to 58/70, clearing the 56/70 bar with room to spare, and the accepted sample grew by 74 rows. But the larger, more diverse cohort also surfaced a genuine catastrophic false accept (a language mismatch neither D3-v5's text checks nor IMAGE-v2's visual-similarity check are designed to detect), which by itself is sufficient to fail certification regardless of the other three gates. This is reported as a real result, not adjusted, hidden, or explained away.
