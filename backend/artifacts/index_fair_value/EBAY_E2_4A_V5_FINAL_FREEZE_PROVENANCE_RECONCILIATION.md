# EBAY_E2_4A — V5 Final-Freeze Provenance Reconciliation

## 1. Exact timing issue

The real V5 final human freeze (417/417 rows, reviewer "Donny", protocol
`SINGLE_REVIEWER_BLIND`) genuinely completed via the review-server workflow
while E2.4's certifier was being implemented in the same session.
`freeze_initial()` had already been edited to record
`initial_human_freeze.review_session_id`, and that edit was live before the
real initial freeze ran — so `initial_human_freeze.review_session_id` =
`"v5_session_2"` is genuine, tool-written provenance. `freeze_final()` was
edited to record `final_human_freeze.review_session_id` and a top-level
`finally_frozen` flag, but that edit landed **after** the real final freeze
had already executed. The real, already-frozen manifest's
`final_human_freeze` block therefore never contained `review_session_id`,
and the manifest never got a `finally_frozen` flag.

A prior remediation step in this session hand-edited those two fields
directly into the frozen manifest to unblock the certifier. That was
**reverted** in this task, because it made the manifest falsely claim to
have always contained fields it did not have when the real freeze ran —
exactly the failure mode this task explicitly forbids ("do not pretend the
historical manifest originally contained fields that did not exist at that
time"). The manifest's `final_human_freeze` block is now back to its
authentic historical shape:

```json
{"label_fingerprint": "c0b2f18a...", "freeze_timestamp": "2026-09-14T03:20:25.038291+00:00", "reviewer_id": "Donny"}
```

## 2. Why a canonical re-freeze was impossible

`ebay_d3_v5_blind_review_server.freeze_final()` refuses with
`EBAY_D3_V5_REVIEW_BLOCKED_ALREADY_FINALLY_FROZEN` once `final_human_freeze`
exists in the manifest — correct behavior, since re-running a freeze against
an already-frozen cohort would be indistinguishable from silently
re-materializing labels. The only way forward that does not touch the real
labels, cohort, or matcher is an independently-verified, separately-recorded
attestation — never another hand-edit of the frozen manifest.

## 3. Fingerprints verified (real cohort, read-only)

All four independently recomputed from the actual queue/manifest/matcher —
never trusted from any single source alone:

| Value | Recorded | Recomputed | Match |
|---|---|---|---|
| Cohort fingerprint | `3e19667cba3d0e579378b7a8b802aba2c40f4668cf7699f63cb989792a329cdf` | same | ✅ |
| Final label fingerprint | `c0b2f18a025d81bacbb7c136a912e167e72105d362adfb8cabfe73dc6189591f` | same | ✅ |
| Matcher fingerprint (frozen V5) | `93301e5da1cf8129896993f12cfec2b66c5c887d679cb6f0755785c884581c69` | same (current `v5.rule_fingerprint()`) | ✅ |

Row count: 417/417, all labels complete (all `REQUIRED_LABEL_FIELDS`
populated on every row). No forbidden matcher-derived columns present in the
cohort CSV.

## 4. Valid review session

**`v5_session_2`** — status `ACTIVE`, `matcher_predictions_consulted: false`.
Its own append-only history file
(`ebay_d3_v5_fresh_blind_review_history_v5_session_2.jsonl`) was
independently re-walked via
`ebay_d3_v5_blind_review_server.reconstruct_effective_labels()` and produces
effective labels for all 417 rows — confirming the session's history alone
(not the manifest, not the materialized queue) accounts for every row.

## 5. Invalidated review session

**`v5_session_1`** — status `INVALIDATED_UI_NAVIGATION_RENDERING_DEFECT`,
`labels_eligible_for_certification: false`, recorded as `v5_session_2`'s
`predecessor_session_id`. Confirmed still invalidated and still ineligible;
the reconciliation refuses to run if either of those flips.

## 6. Reconciliation artifact

`backend/scripts/reconcile_ebay_d3_v5_final_freeze_provenance.py` — a
read-only tool, never imports or calls `ebay_d3_matcher_v5.classify_listing`.
`reconcile()` fails closed (raises `ReconciliationBlocked` with a typed
reason) unless all twelve checks from the task spec pass; `main()` writes
the resulting attestation to:

```
backend/artifacts/index_fair_value/ebay_d3_v5_final_freeze_reconciliation.json
```

Real attestation produced (read-only checks preceded the write; `main()` was
run exactly once against the real cohort):

```json
{
  "reconciliation_version": "ebay_d3_v5_final_freeze_reconciliation_v1",
  "cohort_fingerprint": "3e19667cba3d0e579378b7a8b802aba2c40f4668cf7699f63cb989792a329cdf",
  "final_label_fingerprint": "c0b2f18a025d81bacbb7c136a912e167e72105d362adfb8cabfe73dc6189591f",
  "valid_review_session_id": "v5_session_2",
  "invalidated_predecessor_session_id": "v5_session_1",
  "reviewer_id": "Donny",
  "reviewer_protocol": "SINGLE_REVIEWER_BLIND",
  "labels_complete": true,
  "matcher_predictions_consulted": false,
  "matcher_fingerprint": "93301e5da1cf8129896993f12cfec2b66c5c887d679cb6f0755785c884581c69",
  "reconciliation_reason": "final freeze predated review_session_id/finally_frozen provenance fields",
  "historical_manual_backfill_detected": true,
  "historical_manual_backfill_acknowledged": true,
  "no_label_cohort_or_matcher_mutation_performed": true,
  "row_count": 417,
  "attestation_fingerprint": "<sha256 of the attestation's own other fields>"
}
```

The artifact carries its own `attestation_fingerprint` (sha256 over every
other field) so the certifier can detect post-write tampering independent of
re-running the reconciliation logic.

## 7. Certifier precondition behavior

`certify_ebay_d3_v5_fresh_blind.py`'s `_validate_review_session()` now
accepts exactly one of two provenance sources:

- **Path A (canonical)**: `blind_manifest.final_human_freeze.review_session_id`
  present — used as before, no change to existing behavior for any future
  clean freeze.
- **Path B (reconciliation)**: when path A is absent, `_verify_reconciliation_attestation()`
  loads `ebay_d3_v5_final_freeze_reconciliation.json`, recomputes its
  self-fingerprint (rejects any tampering), **independently recomputes**
  the cohort and label fingerprints from the current real queue (never
  trusts the attestation's claimed values), cross-checks them against the
  blind manifest's own recorded fingerprints, verifies
  `matcher_predictions_consulted: false` and the recorded matcher
  fingerprint still matches the frozen one, and verifies the named session
  is not invalidated while its predecessor is.

A separate, equally load-bearing check (`finally_frozen_effective`) accepts
either the canonical `finally_frozen` manifest flag or a session-validated
reconciliation attestation, since the real freeze also predates that flag.

Any failure in path B blocks with the typed reason
`EBAY_D3_V5_CERTIFICATION_BLOCKED_FREEZE_PROVENANCE_INVALID`. No statistical
gate (`accepted_precision`, `wilson_lower`, `coverage`, `catastrophic`) was
touched — `apply_gates()` and its thresholds (0.99 / 0.98 / 0.80 / 0) are
byte-identical to E2.4.

Confirmed on the real cohort: `check_preconditions()` now returns
`overall_pass: true` with `provenance_source: "RECONCILIATION_ATTESTATION"`,
`reconciliation_attestation_fingerprint_matches: true`, and
`finally_frozen_effective: true` — **without** the hand-edited manifest
fields present. (The manifest edit was reverted; see Section 1.)

## 8. Tests

- `backend/tests/unit/scripts/test_reconcile_ebay_d3_v5_final_freeze_provenance.py`
  — **16 new tests**: valid reconciliation succeeds; cohort/label
  fingerprint mismatch blocks; wrong/mixed review session blocks;
  invalidated session cannot become authority; matcher-consulted flag
  blocks; matcher fingerprint mismatch blocks; incomplete labels block;
  forbidden matcher columns block; row-count mismatch blocks; predecessor-
  not-invalidated blocks; `main()` writes and returns the same attestation;
  reconciliation performs zero mutation of the queue, labels, or matcher
  (verified via a `classify_listing` call-count spy).
- `backend/tests/unit/scripts/test_certify_ebay_d3_v5_fresh_blind.py` — **9
  new tests** covering the certifier integration: a hand-backfilled-only
  manifest (no reconciliation file) is insufficient and blocks; a valid
  reconciliation satisfies the provenance precondition; a tampered
  attestation self-fingerprint blocks; a reconciliation disagreeing with the
  manifest's fingerprints blocks; a reconciliation pointing at an
  invalidated session blocks; a matcher-fingerprint-mismatched reconciliation
  blocks; gates are unchanged; the real matcher (`classify_listing`) is
  never invoked by any precondition-only check. **39 total pass** in that
  file (30 from E2.4 + 9 new).
- Also fixed, in the same pass: `test_main_produces_not_certified_when_a_gate_fails`
  in the E2.4 certifier test file never redirected
  `CERTIFICATION_OUTPUT_PATH` away from the real repo path — a genuine bug
  that had silently overwritten the real
  `ebay_d3_v5_fresh_blind_certification.json` with 2-row fixture data during
  an earlier test run. Fixed by adding it to `write_env()`'s monkeypatch
  set, added an explicit regression-guard test, and deleted the leaked fake
  file from the real repo path.
- Full `ebay`-scoped regression suite: **517 passed**, 0 failed.

## 9. Confirmation: real certification NOT run

Only `check_preconditions()` and `reconcile()`/`main()` (the reconciliation
script) were run against the real cohort — both are read-only with respect
to labels/cohort/matcher and neither calls
`ebay_d3_matcher_v5.classify_listing`. `certify_ebay_d3_v5_fresh_blind.main()`
(the function that would actually run the matcher against the 417-row human
gold and compute real precision/recall/Wilson/coverage/catastrophic metrics)
was **not invoked** in this task. The real V5 matcher remains unseen against
the human-labeled benchmark.

## 10. What remains unchanged

- The 417-row cohort CSV: byte-identical before and after this task.
- All human labels: untouched.
- `ebay_d3_matcher_v5.py`: not imported for classification, not modified.
- Certification gate thresholds: unchanged (0.99 / 0.98 / 0.80 / 0).
- `v5_session_1`'s invalidation record: unchanged, still
  `INVALIDATED_UI_NAVIGATION_RENDERING_DEFECT` /
  `labels_eligible_for_certification: false`.

EBAY_D3_V5_FINAL_FREEZE_PROVENANCE_RECONCILED
