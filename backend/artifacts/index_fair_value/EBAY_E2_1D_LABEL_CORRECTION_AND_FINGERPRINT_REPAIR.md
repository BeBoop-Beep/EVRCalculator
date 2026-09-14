# eBay E2.1D — Human Label Correction Audit + Fingerprint Integrity Repair

## 1. Root cause of the fingerprint mismatch (found, not assumed)

Read both implementations directly:

- **Review server's `freeze()`** (old): `sha256("\n".join(sorted(f"{row_id}:{field}:{value}" ...)))` — includes the field name in each line.
- **Certifier's `_label_fingerprint()`** (old): `sha256("\n".join(sorted(f"{row_id}:{value}" ...)))` — does **not** include the field name.

Two different serialization formats over the same underlying data produce two different hashes, by construction. Confirmed live against the real, already-frozen cohort:

```
manifest label_fingerprint   (from freeze):        5c5a017e8ccc5c69a5e1fd343a93c5e86988396b89de863820a9f36a5cdc97d8
check_preconditions recompute (before this fix):   4b035f9f91ad69a7512f8c6365c509fefb85ef6bbd49316f6c3a9081d5e6a6d0
overall_pass (before this fix):                    True   <-- the bug: computed but never compared
```

`check_preconditions()` computed the recomputed fingerprint into its `checks` dict but **never compared it against anything**, so the mismatch was silently invisible to the pass/fail decision. Both bugs (wrong formula, missing comparison) are now fixed together.

## 2. Fix: one canonical fingerprint function

`certify_ebay_d3_v4_fresh_blind.compute_label_fingerprint(rows)` is now the **single** implementation (field-name-included format, i.e. the review server's original, more collision-resistant formula). `ebay_d3_v4_blind_review_server.py` no longer has its own inline hash — it imports and calls this exact function (`_canonical_label_fingerprint()` is a one-line delegator, not a second implementation). The old `_label_fingerprint` name is kept only as an alias to the canonical function, for any external caller still using it.

## 3. Fix: certifier now fails closed on fingerprint mismatch

`check_preconditions()` now reads `manifest["final_label_fingerprint"]` (the new canonical key), recomputes the same fingerprint from the current queue rows, and **blocks** with `EBAY_D3_V4_CERTIFICATION_BLOCKED_LABEL_FINGERPRINT_MISMATCH` if they differ — or with `EBAY_D3_V4_CERTIFICATION_BLOCKED_LABELS_NOT_FROZEN` if `final_label_fingerprint` isn't present at all (which is the current real state — the legacy `label_fingerprint` key from a first-pass-only freeze is reported for provenance but is **never** trusted for the pass/fail decision, since it was produced by the old buggy formula). Verified live: `overall_pass` is now correctly `False` against the real (first-pass-only) manifest.

## 4. Root cause of the Undo bug (found, not assumed)

The "Undo Previous" button's JS captured `rowId` from the row **currently displayed** (`const rowId = ...` inside `page()`). After saving a label, the page auto-advances to the next unreviewed row. Clicking "Undo Previous" on that new page therefore sent the **new, not-yet-labeled** row's id to `/undo` — a per-row undo lookup for a row with no label found nothing, and did nothing. The reviewer's actual last action was never touched. This matches the reported symptom exactly ("did not work reliably").

**Fix**: added `build_undo_last_label_event()` (and its correction-audit counterpart, `build_undo_last_correction_event()`), which undoes the single most recently recorded, not-yet-undone event in the **entire** history file, independent of which row the page happens to be showing. The `/undo` endpoint and its JS no longer send a `row_id` at all. Reproduced and fixed; see tests in §9.

## 5. Files changed

- `backend/scripts/certify_ebay_d3_v4_fresh_blind.py` — canonical fingerprint function + fail-closed comparison (no gate/threshold change).
- `backend/scripts/ebay_d3_v4_blind_review_server.py` — undo-bug fix, full correction-audit subsystem (`--audit-yes-labels`), two-stage freeze (`freeze_initial`/`freeze_final`), canonical-fingerprint adoption.
- `backend/tests/unit/scripts/test_ebay_d3_v4_blind_review_server.py` — 31 new tests (71 total in file).
- `backend/tests/unit/scripts/test_ebay_d3_v4_remediation.py` — one stale assertion fixed (it asserted the real manifest's `labels_exist` was still `False`, which is no longer true now that real labeling has genuinely happened; replaced with the actual structural invariant it meant to test).
- `backend/artifacts/index_fair_value/EBAY_E2_1D_LABEL_CORRECTION_AND_FINGERPRINT_REPAIR.md` (this report).

**Not touched**: `ebay_d3_matcher_v4.py`, `v3.py`, any certification gate/threshold, the 420-row cohort's membership, or the real first-pass history file's content.

## 6. Correction-audit design

- **Queue**: `build_correction_queue()` selects **exactly** the rows whose current effective first-pass label (read from the already-materialized queue CSV) is `YES` — no matcher output is read or referenced anywhere in this function (verified by AST inspection in tests). Order is a deterministic shuffle from a fixed, recorded seed (`CORRECTION_ORDER_SEED = 1337`) — selection is untouched by the shuffle.
- **UI**: `--audit-yes-labels` serves a dedicated page (KEEP YES / CHANGE TO NO / UNCERTAIN, keyboard shortcuts K/C/U) showing only target-card and listing fields — no matcher status, score, or reason of any kind.
- **History**: a **separate** append-only file, `ebay_d3_v4_fresh_blind_correction_history.jsonl`, using `"correction"`/`"undo_correction"` actions. The original `ebay_d3_v4_fresh_blind_review_history.jsonl` is never opened for writing during the correction audit and is verified byte-identical before/after in tests.
- **CHANGE TO NO** reuses the exact existing `NO_REASONS` taxonomy (no redundant new dropdowns).
- **Final freeze** (`freeze_final`) requires every current-YES row to have a correction decision (refuses with `EBAY_D3_V4_REVIEW_BLOCKED_CORRECTION_AUDIT_INCOMPLETE` otherwise), then materializes: `KEEP_YES` → unchanged YES fields, `CHANGE_TO_NO` → the reason's derived NO fields, `UNCERTAIN` → the uncertain schema. Rows that were `NO` in the first pass are carried forward **byte-identical** — never touched by the correction pass.

## 7. Manifest provenance (three stages, none silently overwritten)

`freeze_initial()` (unchanged conceptually, now also writes):
```json
"initial_human_freeze": {"label_fingerprint": "...", "freeze_timestamp": "...", "reviewer_id": "Donny"}
```
`freeze_final()` additionally writes:
```json
"correction_audit": {"performed": true, "corrected_row_count": 252, "yes_row_count": 252,
                      "correction_order_seed": 1337, "correction_history_fingerprint": "...",
                      "decision_counts": {"KEEP_YES": N, "CHANGE_TO_NO": N, "UNCERTAIN": N}},
"final_human_freeze": {"label_fingerprint": "...", "freeze_timestamp": "...", "reviewer_id": "Donny"},
"final_label_fingerprint": "...",
"matcher_predictions_consulted": false,
"certification_not_yet_run": true
```
The legacy top-level `label_fingerprint`/`freeze_timestamp` keys from the first pass are **preserved**, not deleted or overwritten — `initial_human_freeze` is synthesized from them if a manifest predates this fix, so no prior freeze is ever silently erased.

## 8. Real cohort status (read-only checks performed this session)

The 420-row cohort's **real, already-completed first pass** (252 YES / 168 NO / 0 UNCERTAIN, reviewer Donny, `SINGLE_REVIEWER_BLIND`) is confirmed intact and untouched by this session — verified directly against the files on disk before and after all code changes. `--summary` against the real cohort now correctly reports a 252-row correction queue with 0 corrections done yet. `check_preconditions()` against the real manifest correctly returns `overall_pass: False` / `EBAY_D3_V4_CERTIFICATION_BLOCKED_LABELS_NOT_FROZEN` (no `final_label_fingerprint` exists yet — correct, since the correction audit hasn't run).

**Incident during test development, caught and fixed**: two of this session's own test fixtures initially failed to monkeypatch the new `CORRECTION_HISTORY_PATH` constant, causing a duplicate of the earlier default-path pollution bug — synthetic test events were briefly written to the real `ebay_d3_v4_fresh_blind_correction_history.jsonl` on disk. Caught immediately by a failing test count mismatch (842 events instead of 2), the real file was deleted (it contained only fabricated test data, never real review content), and the fixture was corrected. Verified clean afterward: file absent, real manifest/queue byte-identical to before.

## 9. Tests / results

```
71 passed  -- test_ebay_d3_v4_blind_review_server.py (40 existing + 31 new)
21 passed  -- test_certify_ebay_d3_v4_fresh_blind.py (unchanged, still green)
334 passed -- full backend/tests/unit/scripts -k "ebay or fair_value" (1 stale assertion fixed, no other regressions)
```

New tests cover (per the 20 required areas): exact correction-queue membership, no matcher-based selection (AST-verified), KEEP_YES / CHANGE_TO_NO / UNCERTAIN derivation, NO-reason mapping onto the existing taxonomy, append-only correction history isolated from first-pass history, undo-correction semantics, restart/resume persistence, first-pass history byte-equality before/after correction, initial-freeze provenance surviving the final freeze, correctly-materialized final labels (including NO-rows passed through untouched), one canonical fingerprint function (direct equality check against the certifier's), freezer/certifier fingerprint agreement, fingerprint-mismatch blocking, a direct regression test for "two different fingerprints can no longer coexist with `overall_pass=True`", cohort-fingerprint invariance, matcher-fingerprint invariance, zero `classify_listing` calls across the whole correction→freeze→summary cycle, zero `compute_certification_metrics` calls, and the original undo-bug reproduction (label → undo → reconstruct → relabel → simulated restart → verify persistence, with nothing ever deleted from history).

## 10. Confirmation

No D3-v3 or D3-v4 prediction was computed or exposed anywhere in this task. No certification metric (precision, recall, coverage, catastrophic count) was calculated. No matcher rule or threshold was changed. No certification gate was changed. The cohort's 420-row membership and its `cohort_fingerprint` are unchanged and re-verified equal in every test and in the live check.

## Next command for Donny

The correction-audit tool is ready and the real 252-row queue is confirmed correct. To perform the human-only correction pass over the suspected misclicks:

```
python -m backend.scripts.ebay_d3_v4_blind_review_server --reviewer Donny --audit-yes-labels
```

Undo now correctly reverts your most recent action regardless of which row is on screen. Check progress any time with:

```
python -m backend.scripts.ebay_d3_v4_blind_review_server --reviewer Donny --summary
```

Once all 252 rows have a decision (`KEEP_YES` for the ones that were genuinely YES is fine and expected for most of them — only the ~10 suspected misclicks need to change), run the final freeze:

```
python -m backend.scripts.ebay_d3_v4_blind_review_server --reviewer Donny --freeze
```

This will automatically run only the fingerprint/completeness precondition check afterward (never the matcher) and report whether the cohort is now certification-ready.

## Final decision

**`EBAY_D3_V4_HUMAN_LABEL_CORRECTION_AUDIT_READY`**
