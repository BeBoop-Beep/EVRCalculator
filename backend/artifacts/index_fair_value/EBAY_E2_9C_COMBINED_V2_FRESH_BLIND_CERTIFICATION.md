# EBAY_E2_9C — Final Fresh-Blind Certification of COMBINED-IDENTITY-v2

**Final decision:** `EBAY_COMBINED_IDENTITY_V2_FRESH_BLIND_NOT_CERTIFIED_WILSON_LOWER_GE_0_98`

Worktree `D:\EVRCalculator-ebay-e2.9`, branch `feature/ebay-e2.9-image-veto-tiered-identity`, HEAD `aee7f131` (unchanged). Nothing staged, committed, or pushed. No matcher/image/policy/threshold/gate was modified.

## 1. All precondition fingerprints (independently recomputed, not trusted from the prompt)

Before scoring anything, every claimed value in "LOCKED HUMAN AUTHORITY" was independently recomputed from the actual files on disk:

| # | Precondition | Independently recomputed result | Pass |
|---|---|---|---|
| 1 | Cohort row count = 414 | `load_queue_rows()` → 414 | ✓ |
| 2 | Cohort fingerprint matches | `cohort_fingerprint()` → `b95c4d2d...a720d1b4c` | ✓ |
| 3 | Labels complete | manifest `labels_exist=True` | ✓ |
| 4 | Final human freeze exists | manifest `finally_frozen=True` | ✓ |
| 5 | Final label fingerprint recomputes exactly | `compute_label_fingerprint(rows)` → `a520aeb0...e41c8f8a8`, matches claim and manifest | ✓ |
| 6 | Correction history fingerprint matches | `_history_fingerprint(correction_events)` → `8149dc9e...959ede5c7`, matches claim and manifest | ✓ |
| 7 | Review session = `e2_9b_session_1` | `get_active_session_id()` → `e2_9b_session_1` | ✓ |
| 8 | Session not invalidated | `is_session_invalidated()` → `False` | ✓ |
| 9 | D3-v5 fingerprint matches frozen | `v5.rule_fingerprint()` → `93301e5d...4581c69` | ✓ |
| 10 | IMAGE-v2 fingerprint matches frozen | `image_v2.source_sha256()` → `bf50ee1f...4c680ea1` | ✓ |
| 11 | COMBINED-v2 fingerprint matches frozen | `policy_v2.policy_source_hash()` → `59e32c0a...9954abf07` | ✓ |
| 12 | Canonical-resolution manifest fingerprint matches durable authority | `sha256(durable copy)` → `9fc36d8d...8ab295d446` | ✓ |
| 13 | Capture occurred after combined-policy freeze | `2026-09-15T02:40:50Z` (capture) > `2026-09-14T21:56:09Z` (policy freeze) | ✓ |
| 14 | Reviewer queue contains no matcher/image/policy outputs | `assert_no_forbidden_columns()` passes | ✓ |
| 15 | No post-freeze human-label mutation | queue mtime (22:22:22.902Z) coincides with `final_human_freeze` timestamp (22:22:22.898Z) — same write, no later edit; independently confirmed by #5's exact fingerprint match | ✓ |

**All 15 preconditions independently verified true.** No precondition failure. Scoring proceeded.

One note from this verification pass: an early check of my own briefly appeared to show a mismatch on item 11 (`policy_v2.policy_source_hash() != m["combined_identity_v2_policy_fingerprint"]`) — this was my own script comparing two intentionally-different values (the raw *source hash* vs. the composite *policy fingerprint*, which also folds in the text/image fingerprints). Both values independently matched their correct counterparts once compared correctly; there was no real authority drift.

## 2. Phase 1 — Score (label-blind)

`backend/scripts/run_ebay_combined_identity_v2_fresh_blind_scoring.py` scored all 414 rows using D3-v5 (`classify_listing`, frozen), IMAGE-v2 (`resolve_image_state`/`verify_by_retrieval`, frozen), and COMBINED-IDENTITY-v2 (`combine`, frozen), reading canonical targets from the durable E2.8/E2.9B canonical-resolution manifest (no new resolution performed — all 69 represented cards already present).

- `score_row()` receives a copy of each row with `exact_match_yes_no_uncertain` structurally removed before scoring — verified by both source inspection (`test_score_row_never_reads_human_label`) and by the fact the function has no code path that could reference it.
- Ran live against real listing images (real network fetch + real frozen DINOv2 inference), started `2026-09-15T22:48:29Z`, finished `2026-09-15T22:50:13Z` (~1m44s), 414/414 scored.
- **Prediction artifact:** `backend/artifacts/index_fair_value/ebay_combined_identity_v2_fresh_blind_predictions.json`
- **Predictions fingerprint:** `667dc7bc8ad3d2fcb9db5a3ffa75c57d60816e84c8d2c6c6cf0c20bcdaabc926` — computed and written before any label was consulted, and re-verified byte-for-byte at the start of Phase 2.

Prediction distribution (label-blind): `REJECTED_TEXT` 192, `TIER_A_IMAGE_VERIFIED` 107, `TIER_B_TEXT_VERIFIED_IMAGE_UNVERIFIED` 78, `TEXT_AMBIGUOUS_NOT_PROMOTED` 22, `REJECTED_IMAGE_CONTRADICTION` 15.

## 3. Phase 2 — Evaluate (join to human labels)

`backend/scripts/run_ebay_combined_identity_v2_fresh_blind_certification.py` joined the frozen prediction artifact to the frozen human labels by `row_id` only after re-verifying the predictions-fingerprint match. No prediction was altered.

## 4. Primary certification metrics (exact, no rounding before gate evaluation)

| Metric | Value |
|---|---|
| Total definitive rows | 414 |
| Accepted rows | 185 |
| True accepts | 185 |
| False accepts | **0** |
| Rejected rows | 229 |
| True rejects | 176 |
| False rejects | 53 |
| Accepted precision | **1.0** |
| Wilson 95% lower bound | **0.9796577571223828** |
| Recall | 0.7773109243697479 |
| Row acceptance rate | 0.4468599033816425 |
| Distinct-card coverage | **0.7714285714285715** (54/70) |

## 5. Tier-specific results (kept visible, not collapsed)

| | Tier A | Tier B |
|---|---|---|
| Accepted count | 107 | 78 |
| True accepts | 107 | 78 |
| False accepts | 0 | 0 |
| Precision | 1.0 | 1.0 |
| Distinct cards covered / incrementally recovered | 45 | **9** (cards Tier A alone would not have covered) |

Tier B is reported here as `TEXT_VERIFIED_IMAGE_UNVERIFIED` throughout — never described as image-verified.

## 6. Card coverage (fixed 70-card denominator, never 69)

- Tier-A-covered card IDs: 45 cards
- Tier-B-only incremental covered card IDs: 9 cards
- **All covered card IDs: 54** (45 + 9)
- **All uncovered card IDs: 16**
- Represented-but-uncovered cards (had listings in the blind cohort, but none scored as an eligible true accept): **15**
- The one capture-unrepresented target card (no eligible new listing evidence survived historical exclusion — see E2.9B): `640cd931-d97f-4173-ad9d-3ab86f91d92c` (Pecharunt ex, Shrouded Fable #93) — counted as **uncovered**, per instruction, with no invented exception.

**Final card coverage: 54 / 70 = 0.7714** — computed against the fixed 70-card universe, not 69. This is below the required 56/70.

## 7. False-accept forensics

**Zero accepted human-NO rows.** There is nothing to report in the false-accept forensics table — no row, target identity, listing title, or NO-reason to characterize, and no identity-error category to classify.

## 8. Catastrophic false-accept contract

**Catastrophic false accepts = 0.** Gate passes. Taxonomy counts (all zero, listed per instruction rather than omitted): `WRONG_CARD: 0, WRONG_CARD_NUMBER: 0, WRONG_SET: 0, WRONG_VARIANT_OR_TREATMENT: 0, GRADED: 0, LOT_OR_BUNDLE: 0, SEALED_OR_NON_CARD: 0, WRONG_LANGUAGE: 0, OTHER: 0`.

## 9. Locked final gates — exact, unrounded evaluation

| Gate | Requirement | Observed | Result |
|---|---|---|---|
| Accepted precision | ≥ 0.99 | 1.0 | **PASS** |
| Wilson 95% lower bound | ≥ 0.98 | 0.9796577571223828 | **FAIL** (misses by 0.0003422...) |
| Card coverage (denominator 70) | ≥ 0.80 (≥ 56/70) | 54/70 = 0.7714285714285715 | **FAIL** |
| Catastrophic false accepts | == 0 | 0 | **PASS** |

**Two of four gates fail.** Per instruction, the 54/70 result is not rounded or relaxed toward the 56/70 requirement, and the 0.97966 Wilson lower bound is not rounded up to 0.98.

## 10. Certification artifacts

- `backend/artifacts/index_fair_value/ebay_combined_identity_v2_fresh_blind_predictions.json`
- `backend/artifacts/index_fair_value/ebay_combined_identity_v2_fresh_blind_certification.json`
- This report

All record `production_authority: false`.

## 11. No post-hoc policy changes

No threshold, policy, resolver, image, text-matcher, or special-case rule was changed after scoring began (or at any point in this task). No human-label artifact was modified. Certification failing is being reported as a failure, not remediated in this task.

## 12. Tests

`backend/tests/unit/scripts/test_ebay_combined_identity_v2_fresh_blind_certification.py` — 27 tests, all passing, covering the 24 required areas (several requirements map to more than one test, e.g. precondition-failure simulations #1–4 each use a tampered-copy monkeypatch that never touches the real files):

```
python -m pytest backend/tests/unit/scripts/test_ebay_combined_identity_v2_fresh_blind_certification.py -q
27 passed

python -m pytest backend/tests/unit/scripts/test_ebay*.py -q
625 passed, 1 failed (pre-existing, unrelated: test_ebay_d2v_validation.py — confirmed via
`git diff --quiet HEAD` that its target file, ebay_d2m_matcher.py, is byte-identical to HEAD;
this is the same CRLF/LF checkout-dependent byte-hash artifact already documented in the E2.9 report)
```

Item 24 (frozen authorities unchanged) and the closing `test_all_real_preconditions_passed` test assert against the **real**, live state of this worktree, not a simulated fixture — both pass.

## 13. Fair Value / Explorer blocker status

**Certification did not pass.** Per the task's own framing, this section only applies "after pass" — it does not. Fair Value and Market Explorer dependent valuation work **remain BLOCKED**, in the same state E2.9/E2.9A left them, pending either a remediated future policy/coverage version or a deliberate decision (out of scope for this task) to proceed with partial coverage.

---

## Final result

**`EBAY_COMBINED_IDENTITY_V2_FRESH_BLIND_NOT_CERTIFIED_WILSON_LOWER_GE_0_98`**

All 15 preconditions verified true; scoring and evaluation ran cleanly end-to-end with full phase separation (predictions fingerprinted before any label was read). The result is genuinely strong on precision and safety — 1.0 accepted precision, 0 false accepts, 0 catastrophic errors across 185 real accepted listings — but the Wilson 95% lower bound (0.97966) falls just short of the 0.98 gate, and distinct-card coverage (54/70 = 0.7714) falls short of the required 56/70. Both are reported exactly as measured, without rounding or relaxation. No remediation was attempted; per instruction, a failed gate stays failed in this task, and any fix belongs to a future version.
