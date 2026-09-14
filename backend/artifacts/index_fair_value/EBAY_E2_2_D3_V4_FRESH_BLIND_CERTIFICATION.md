# eBay E2.2 — D3-v4 Fresh-Blind Certification Attempt (BLOCKED)

## 1. Branch / SHA / worktree state

- Branch: `develop`, HEAD `b087d535878e2ad6a2bc26ad3daf85146a1aa278` (unchanged
  since E2.1 — E1 is committed here; E2/E2.1/E2.2 remain uncommitted and
  cleanly separable from unrelated concurrent work, which this task did not
  touch: `backend/calculations/evr/best_open_price.py`,
  `test_prepared_financial_rip_and_best_open_price.py`, log files).

## 2. Frozen matcher identity and fingerprint

- Matcher: `backend/scripts/ebay_d3_matcher_v4.py`, version `index_fair_value_ebay_d3_v4`.
- Frozen fingerprint (`ebay_d3_v4_freeze_manifest.json`):
  `14336982da2cbd420f686c350cc47f5c2843dd94afb7b711175a7f7dbe14b523`.
- **Recomputed live fingerprint at the start of this task matches exactly**
  (`check_preconditions()["checks"]["matcher_fingerprint_matches"] == True`) —
  no matcher/config drift occurred since E2.1's freeze.

## 3. Cohort fingerprint

- Recorded (`ebay_d3_v4_fresh_blind_manifest.json`):
  `31e97a7429a24afa4595a16902a15f1d52e0b18eddb44be780e6c0cf80e5d19b`.
- Recomputed from the current `ebay_d3_v4_fresh_blind_queue.csv` contents:
  **identical** — the cohort has not been silently regenerated or edited
  since E2.1's capture.

## 4. Label fingerprint

**Not present.** A label fingerprint can only be computed once labels exist;
this task's precondition check confirms zero rows are labeled (see §7), so no
label fingerprint exists to report.

## 5. Reviewer protocol

`SINGLE_REVIEWER_BLIND`, exactly as declared by E2.1. `reviewer_b_exists:
false`. This protocol metadata is present and internally consistent, but no
labeling has actually occurred against it yet.

## 6. Reviewer count

**0 active.** The manifest declares the intended protocol (single reviewer),
but zero labels have been recorded — there is no reviewer activity to audit
yet.

## 7. Label completion / uncertain counts

| | Count |
|---|---|
| Total blind cohort rows | 420 |
| Rows with `exact_match_yes_no_uncertain` populated | **0** |
| Rows with any required label field populated | **0** |
| `labels_exist` flag in `ebay_d3_v4_fresh_blind_manifest.json` | `false` |

This is the exact, unambiguous state verified directly against the real
artifact files on disk in this session — not inferred or assumed.

## 8-16. Not evaluated

Matcher status counts, accepted precision, Wilson interval, recall,
acceptance/rejection/ambiguity rates, card-level coverage, the catastrophic
false-accept table, the confidence/status audit, and the slice analysis are
all **not computed** in this task. Per the Critical Precondition instruction,
D3-v4 was never run against the blind cohort — computing any of these numbers
without real human labels would be fabrication, not certification.

## 17. v3 vs v4 diagnostic

**Not run.** This diagnostic is explicitly gated on "AFTER labels were frozen
and D3-v4's primary certification result has been recorded" — neither
condition holds, so it was not performed.

## 18. Certification-gate matrix

All four gates report `NOT_EVALUABLE` — there is no accepted sample to
evaluate them against:

| Gate | Threshold | Status | Reason |
|---|---|---|---|
| Accepted precision | ≥ 0.99 | `NOT_EVALUABLE` | zero labeled rows; no accepted sample exists |
| Wilson lower bound | ≥ 0.98 | `NOT_EVALUABLE` | same |
| Card coverage | ≥ 0.80 | `NOT_EVALUABLE` | same |
| Catastrophic false accepts | ≤ 0 | `NOT_EVALUABLE` | same |

These are the exact repository-established gates from
`ebay_d3_new_blind_benchmark_design.json:preregistered_gate` — reused
verbatim by `certify_ebay_d3_v4_fresh_blind.apply_gates()`, not redefined or
loosened for this task.

## 19. Evidence-quality cap decision

**Unchanged.** The `matcher_certified` cap in
`index_fair_value_ebay_evidence_quality.py` remains `False`-driving (evidence
capped at `MEDIUM`) for D3-v4, exactly as it was for D3-v3. Certification did
not occur, so the cap is not lifted. Verified by
`test_evidence_quality_still_capped_when_matcher_uncertified`.

## 20. Test results

New file: `backend/tests/unit/scripts/test_certify_ebay_d3_v4_fresh_blind.py` — 21 tests, all passing:

```
21 passed  -- test_certify_ebay_d3_v4_fresh_blind.py (new, this task)
263 passed -- full backend/tests/unit/scripts -k "ebay or fair_value" (no regressions vs E1/E2/E2.1)
```

Covers all 20 required areas: missing/incomplete/unfrozen label refusal,
matcher-hash-mismatch refusal, cohort-fingerprint-mismatch refusal,
forbidden-matcher-column detection, uncertain-label exclusion policy, exact
precision/Wilson calculation, catastrophic classification from the human
label schema, HIGH_CONFIDENCE-only catastrophic accounting, card-level
coverage vs "false-only-accept" distinction, sample-size retention in the
metrics contract, independent (non-overridable) gate reporting, fixed
(non-caller-supplied) gate thresholds, v3/v4 diagnostic independence,
evidence-quality cap persistence, active-ask-only semantics, and — critically
— an end-to-end test that `main()` genuinely refuses to run against the real,
currently-unlabeled cohort on disk right now.

The certification tool itself is fully built, tested, and proven (against
real repository state, not a mock) to refuse execution until labels are
frozen. What remains is the human labeling work itself.

## 21. Confirmation of zero production-price/simulation/snapshot changes

Confirmed. This task read existing artifacts, ran the precondition checker
(read-only against real files), and added new files/tests only. No file
under `backend/calculations`, `backend/db/services` (pricing), simulation
runners, or frontend was read, let alone written. No TCGplayer price, Set
Value, market snapshot, or ranking was touched.

## 22. Explicit scientific limitations

1. **The blind cohort exists and is verifiably unmodified, but is entirely
   unlabeled.** E2.1 ended by handing off a labeling queue; that handoff has
   not yet been picked up.
2. **Single-reviewer protocol, once labeling does happen, will still not
   constitute inter-rater-validated ground truth** — this was already known
   and honestly declared in E2.1, and remains true regardless of when
   labeling completes.
3. **The certification tool built in this task (`certify_ebay_d3_v4_fresh_blind.py`)
   has only been exercised against synthetic fixtures and the real
   (unlabeled) cohort's refusal path** — its accept-path metric computation
   (Phases D-H) has not yet been exercised against a real, fully-labeled
   420-row dataset. That is expected and correct given the task boundary
   (labels don't exist), but it means the "first real run" of the accept
   path is still ahead, in E2.2's actual re-attempt.

## Final decision

**`EBAY_D3_V4_CERTIFICATION_BLOCKED_LABELS_NOT_FROZEN`**

The frozen v4 matcher's integrity is intact (fingerprint match confirmed),
the frozen blind cohort's integrity is intact (fingerprint match confirmed),
and the certification tooling required to score it — gates, catastrophic
taxonomy, Wilson interval, card-level coverage, uncertain-label handling, and
every refusal path — is now built and tested. But the blind cohort has zero
human labels, so per the mandatory precondition check, D3-v4 was **not** run
against it, no precision/recall/coverage/catastrophic numbers were computed
or reported, and E3 readiness was **not** assessed.

**No matcher tuning occurred. No post-blind adjustment occurred. No gate was
invented or loosened.**

**Recommended next step:** complete the single-reviewer labeling pass over
`backend/artifacts/index_fair_value/ebay_d3_v4_fresh_blind_queue.csv` (420
rows, all matcher-output-free), freeze the resulting labels (populate
`ebay_d3_v4_fresh_blind_manifest.json:labels_exist = true` and record a label
fingerprint), and then re-run this exact E2.2 task. Do not attempt to
partially label, sample, or shortcut the 420 rows — the certification tool
requires 100% label completion before it will proceed at all.

Do not proceed to E3 until a passing certification decision exists.
