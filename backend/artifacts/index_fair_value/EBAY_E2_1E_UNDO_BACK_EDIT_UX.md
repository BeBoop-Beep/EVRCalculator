# eBay E2.1E — Reliable Undo + Back/Edit Human Labels

## Summary of changes

1. **Undo** — unchanged from E2.1D's fix (global "undo my last action," never derived from the currently-displayed row), now wired into every mode including the two new ones, and confirmed to navigate the UI to the affected row after undoing.
2. **Previous / Back** — new. Both `--audit-yes-labels` and the new `--review-existing` mode support free bidirectional navigation (`← Previous (B)` / `Next (N)`) through the row list without creating any event. Cursor position is a pure in-memory pointer; navigating never appends to history.
3. **Edit / Relabel any previously reviewed row** — new. `/correction` and `/review_existing` already accepted an explicit `row_id`, so relabeling an arbitrary previously-decided row was structurally possible; this task adds the UI path (Previous → shows current decision → submit a new decision) and confirms state reconstruction always uses the latest non-undone event, with the original event preserved untouched.
4. **`--review-existing`** — new mode. Walks **all 420 rows** (not just the 252 former-YES rows) using their **current effective label** (correction override if one exists, else the frozen first-pass value), fully blind, showing `CURRENT HUMAN LABEL` / `CURRENT HUMAN NO REASON` and offering `KEEP` / `CHANGE TO YES` / `CHANGE TO NO` / `CHANGE TO UNCERTAIN`. It writes into the **same** correction-history stream as `--audit-yes-labels` (extended with three new decision values: `KEEP_CURRENT`, `CHANGE_TO_YES`, `CHANGE_TO_UNCERTAIN`) rather than inventing a third history file — `freeze_final()` already resolves `corrections.get(row_id)` for every row, so review-existing edits on originally-NO rows flow through to the final freeze with no changes needed there.

## Design notes

- **Decision set extended, not replaced.** `CORRECTION_DECISIONS` grew from `(KEEP_YES, CHANGE_TO_NO, UNCERTAIN)` to also include `KEEP_CURRENT, CHANGE_TO_YES, CHANGE_TO_UNCERTAIN`. The 274 real correction events already recorded by Donny (`KEEP_YES`/`CHANGE_TO_NO`) remain valid and are interpreted identically — nothing about their meaning changed.
- **`current_effective_fields(row, corrections)`** is the one function that answers "what is this row's label right now" for any row — correction override if present, else the materialized first-pass CSV value. Used by `--review-existing` and available for `KEEP_CURRENT`.
- **Cursor navigation was previously broken for this purpose**: the old `_run_correction_audit` recomputed the cursor to "next uncorrected" on *every* GET, which would have silently overridden any manual Previous/Next click on the next page load. Fixed by only auto-seeking once (on startup) and letting explicit `/previous_correction` / `/next_correction` / decision-submit / undo each set the cursor deliberately.
- **Progress counters unaffected by relabeling**: `correction_summary()`'s `corrected_rows`/`remaining_rows` count *rows with any effective decision*, so relabeling an already-decided row changes its content, never the counts (verified in tests).

## Files changed

- `backend/scripts/certify_ebay_d3_v4_fresh_blind.py` — unchanged from E2.1D in this task (no further edits needed here; confirmed no certification gate/threshold touched).
- `backend/scripts/ebay_d3_v4_blind_review_server.py` — extended decision set, `current_effective_fields()`, `_clamped_index()`/`_position_of()` navigation helpers, rewritten `_run_correction_audit` (Previous/Next/relabel/undo-jumps-to-row), new `_run_review_existing` + `review_existing_page()` + `review_existing_complete_page()`, new `--review-existing` CLI flag, `correction_page()` now shows the row's current decision when revisited.
- `backend/tests/unit/scripts/test_ebay_d3_v4_blind_review_server.py` — 14 new tests (85 total in file); one pre-existing test adjusted (`original_effective_label` field removed since it's no longer universally true once review-existing can edit any row — replaced with a `decision` check, which was the actual thing being verified).

**Not touched**: `ebay_d3_matcher_v4.py`, `v3.py`, any certification gate/threshold, the 420-row cohort's membership/fingerprint.

## Real cohort status (read-only checks, before and after)

Donny's actual correction-audit work is confirmed intact throughout: 252/252 corrected (247 `KEEP_YES`, 5 `CHANGE_TO_NO`), `finally_frozen: false`, 274 lines in the real correction-history file (more than 252 due to legitimate relabels/undos already in Donny's session — append-only, nothing lost). No test in this session wrote to the real files (fixtures correctly isolate `HISTORY_PATH`/`CORRECTION_HISTORY_PATH`/`QUEUE_PATH`/`MANIFEST_PATH`, learned from the prior two turns' pollution incidents).

## Tests / results

```
85 passed  -- test_ebay_d3_v4_blind_review_server.py (71 existing + 14 new)
348 passed -- full backend/tests/unit/scripts -k "ebay or fair_value" (no regressions)
```

Covers all 20 required areas: label→undo→restore, restart persistence, Previous returning to the same row, YES→NO relabel with the original event preserved, undo-of-relabel restoring the prior decision, NO→YES relabel (via the extended review-existing decisions), `current_effective_fields` reflecting corrections, Back/Next creating zero events, progress counters staying correct through a relabel, freeze consuming the *latest* effective state (a relabel made after an initial KEEP_YES correctly wins), the final fingerprint matching the certifier's canonical function, zero matcher imports/invocations across the new navigation/review-existing code (AST-verified), zero certification execution, and the review-existing page rendering with no matcher-derived fields.

## Exact commands

**Normal review** (closed on the real cohort — first pass is already frozen):
```
python -m backend.scripts.ebay_d3_v4_blind_review_server --reviewer Donny
```

**Correction audit** (the 252-row former-YES cleanup — already complete, 252/252):
```
python -m backend.scripts.ebay_d3_v4_blind_review_server --reviewer Donny --audit-yes-labels
```

**Review-existing cleanup** (new — one final optional pass over all 420 current effective labels, with reliable Previous/Next/Undo/relabel):
```
python -m backend.scripts.ebay_d3_v4_blind_review_server --reviewer Donny --review-existing
```

**Summary** (accurate at any point, never touches the matcher):
```
python -m backend.scripts.ebay_d3_v4_blind_review_server --reviewer Donny --summary
```

**Final freeze** (only after Donny is satisfied with the effective state; auto-dispatches to the final/post-correction freeze since the first pass is already frozen; runs only the fingerprint/completeness precondition check afterward, never the matcher):
```
python -m backend.scripts.ebay_d3_v4_blind_review_server --reviewer Donny --freeze
```

## Final decision

**`EBAY_D3_V4_HUMAN_REVIEW_CORRECTION_UX_READY`**
