# EBAY_E2_3B — V5 Review Session Reset + Navigation/Undo Rendering Fix

## 1. Root cause

`ebay_d3_v5_blind_review_server.py`'s primary-review GET handler did not
track "the row currently on screen" as an explicit, addressable identity.
Instead, on every GET it re-derived a display index by scanning forward from
`cursor["index"] - 1` for the next *unlabeled* row (`next_unreviewed_index`).
Undo appended a reversal event and then relied on that same re-scan to land
the next page render somewhere plausible — but the scan has no reason to
land on the specific row that was just undone; it lands on whichever
unlabeled row the scan hits first. There was also no Previous/Next control
on the primary review page at all — Undo was the only navigation-adjacent
action — and no cache-control headers were sent, so a reload could serve a
browser-cached image for the previous index while the reviewed/remaining
counters (rendered as plain text, always fresh) updated correctly. Net
effect: the reviewer could watch the counters change on Undo while the
image on screen failed to reliably reflect the row those counters now
described, with no way to confirm which row a given label actually applied
to. This matches Donny's report exactly and is a genuine scientific-integrity
defect in the review UI, not a labeling error.

## 2. Old session invalidation record

Session id: `v5_session_1` (the original, un-identified history file).

```json
{
  "status": "INVALIDATED_UI_NAVIGATION_RENDERING_DEFECT",
  "history_path": "ebay_d3_v5_fresh_blind_review_history.jsonl",
  "row_action_count": 15523,
  "history_fingerprint": "ae3653e005205633c0889264a2d88f906761786b9579f1290f02bb91ec3b4d94",
  "invalidated_at": "2026-09-14T02:33:46.587186+00:00",
  "reason": "UI navigation/rendering defect: clicking Previous/Undo changed the reviewed counters without reliably updating the rendered listing image, so the reviewer could not guarantee the saved label corresponded to the displayed listing. Reviewer withdrew confidence in the session.",
  "reviewer": "Donny",
  "matcher_predictions_consulted": false,
  "labels_eligible_for_certification": false
}
```

The file `ebay_d3_v5_fresh_blind_review_history.jsonl` is **preserved
unchanged on disk** (verified byte-identical before/after invalidation in
`test_reset_session_preserves_and_invalidates_old_history`). It is
permanently excluded from effective-label reconstruction and from freeze:
`append_event()` refuses any further write targeting this session, and
`freeze_initial`/`freeze_final` both refuse to certify from any session
whose manifest status is `INVALIDATED_UI_NAVIGATION_RENDERING_DEFECT`
(typed blocker `EBAY_D3_V5_CERTIFICATION_BLOCKED_INVALID_REVIEW_SESSION`).

## 3. New review session

Session id: **`v5_session_2`**
History file: `backend/artifacts/index_fair_value/ebay_d3_v5_fresh_blind_review_history_v5_session_2.jsonl`
`active_review_session_id` in the manifest now points at `v5_session_2`.

Confirmed state immediately after reset (`--summary`):

```json
{
  "reviewed_rows": 0,
  "remaining_rows": 417,
  "total_rows": 417,
  "active_review_session_id": "v5_session_2",
  "active_review_session_invalidated": false
}
```

No labels, corrections, or matcher predictions carried over. The 417-row
blind cohort itself is reused unchanged (no matcher predictions were ever
exposed to the reviewer, so the cohort's blindness is untouched).

## 4. Navigation architecture fix

- The primary review page now renders from an explicit server-side
  `cursor["index"]` that is **only ever** changed by: an explicit
  Previous/Next click, an explicit `?row=<benchmark_row_id>` navigation, a
  label submission (auto-advances to the next unreviewed row), or an Undo
  (jumps directly to the row that was undone). It is never recomputed by
  scanning "the next unlabeled row" on a plain page reload.
- `POSITION` (current row's place in the fixed 417-row order) and
  `REVIEWED` (count of rows with an effective label) are rendered as two
  separate, clearly labeled counters. Previous/Next mutate `POSITION` only
  and append zero history events (verified by
  `test_e21e_back_and_next_navigation_create_no_events`-style coverage and
  the new `test_page_has_previous_and_next_controls_distinct_from_undo`).
- Every render displays `BENCHMARK ROW`, `LISTING ITEM ID`, `TARGET`, and
  `LISTING` for the row the cursor currently points to, all sourced from the
  same `rows[cursor["index"]]` object in one atomic render — they cannot
  drift apart.
- Label submissions are validated server-side: `/label` compares the
  submitted `row_id` against `rows[cursor["index"]]["benchmark_row_id"]`
  and rejects the POST (HTTP 409) on any mismatch, rather than trusting the
  client silently.

## 5. Image stale-render fix

- The `<img>` element now carries `id="rowimg-<benchmark_row_id>"`,
  `data-row-id="<benchmark_row_id>"`, and a cache-busting `?_row=<benchmark_row_id>`
  (or `&_row=...`) query parameter appended to the frozen `image_url` — the
  underlying `image_url` field in the cohort CSV is never modified, only the
  rendered `<img src>` gets the harmless suffix.
- A human-visible `IMAGE ROW: <benchmark_row_id>` marker is printed directly
  under the image so the reviewer can visually cross-check the image against
  the row identity block above it.
- All HTTP responses from the review server (primary review, correction
  audit, review-existing) now send
  `Cache-Control: no-store, no-cache, must-revalidate` and `Pragma: no-cache`.

## 6. Undo behavior

`/undo` still finds the single most recently recorded, non-undone label
event across the **active session's** history (global last-action
semantics, unchanged from the earlier E2.1D fix), but now additionally:

1. Appends the undo/reversal event (append-only, nothing deleted).
2. Looks up that event's `benchmark_row_id` in the fixed row order and sets
   `cursor["index"]` to it directly — no re-scan.
3. Sets a one-shot confirmation message, `UNDID LABEL FOR <benchmark_row_id>`,
   consumed by the very next GET and rendered prominently on the page.

Covered by `test_page_shows_undo_confirmation_message_when_provided` and the
existing E2.1D undo-semantics suite (`test_undo_bug_reproduction_global_last_event_semantics`,
`test_undo_targets_most_recent_row_not_currently_displayed_row`), all still
passing against the session-scoped history path.

## 7. Test results

- `backend/tests/unit/scripts/test_ebay_d3_v5_blind_review_server.py`:
  **99 passed** (85 pre-existing + 14 new E2.3B tests covering session
  invalidation/preservation, refusal to double-invalidate or invalidate
  post-freeze, refusal to write to an invalidated session, freeze refusing
  an invalidated active session, freeze recording `review_session_id`,
  cohort-fingerprint invariance across reset, and the new page-rendering
  identity/position/image-binding/Undo-message assertions).
- Full `backend/tests/unit/scripts` eBay-prefixed suite: **462 passed**, no
  regressions in the V4 server, matcher, or certifier tests (this change
  touches only `ebay_d3_v5_blind_review_server.py` and its own test file).

No browser (Playwright) was available in this execution environment, so the
mandated end-to-end fixture test and the real-cohort click-through smoke
were run as **in-process, read-only functional equivalents** instead:

- The exact `cursor["index"]` state machine used by `_run_primary_review`
  was exercised directly against the real 417-row cohort for the sequence
  row1 → next → next → previous → previous → next, and at every step
  position, `benchmark_row_id`, `listing_item_id`, `listing_title`, and
  `image_url` were asserted to move together and to be exactly reversible:

  ```
  row1            POS 1  D5-0000  v1|188873902261|0  ...s-l225.jpg (EMkAAeSwpyFql6aS)
  row2 (next)     POS 2  D5-0001  v1|287468659950|0  ...s-l225.jpg (5-0AAeSwAzZqcnHK)
  row3 (next)     POS 3  D5-0002  v1|820117207018|0  ...s-l225.jpg (tS0AAeSwh4BqpPcG)
  prev -> row2    POS 2  D5-0001  v1|287468659950|0  ...s-l225.jpg (5-0AAeSwAzZqcnHK)
  prev -> row1    POS 1  D5-0000  v1|188873902261|0  ...s-l225.jpg (EMkAAeSwpyFql6aS)
  next -> row2    POS 2  D5-0001  v1|287468659950|0  ...s-l225.jpg (5-0AAeSwAzZqcnHK)
  ```

  No labels were submitted; this was purely a read-only navigation trace.
  No matcher output was read, computed, or exposed at any point.
- A genuine browser/Playwright pass against the running local server (per
  the spec's mandatory 3–5 row fixture and real-cohort smoke) is still
  recommended before the next live human-review sitting, since it is the
  only way to observe the actual rendered DOM/image element in a browser
  rather than the server-side state machine that drives it. This report
  does not claim that step as done.

## 8. Cohort / matcher fingerprint invariance

- `cohort_fingerprint` in the manifest: unchanged by the reset —
  `3e19667cba3d0e579378b7a8b802aba2c40f4668cf7699f63cb989792a329cdf`
  (verified identical before/after in `test_matcher_and_cohort_fingerprint_unchanged_by_reset`
  and confirmed in the real `--reset-session` run output above).
- `ebay_d3_matcher_v5.py`: not imported, not modified, not run.
- No `matcher_version`/`confidence`/`score`/etc. field was added to the
  queue CSV or ever displayed to the reviewer (`assert_no_forbidden_columns`
  unchanged and still enforced on every `--freeze`/serve entrypoint).

## 9. Exact commands

Launch the NEW session for live human review:

```
python -m backend.scripts.ebay_d3_v5_blind_review_server --reviewer Donny
```
(the server auto-detects `active_review_session_id` = `v5_session_2` from
the manifest and serves/writes only that session's history file)

Summary (session-aware; shows both the invalidated and active session
records plus 0/417 or in-progress counts):

```
python -m backend.scripts.ebay_d3_v5_blind_review_server --reviewer Donny --summary
```

Freeze, once 417/417 are reviewed in `v5_session_2` (refuses if the active
session is ever marked invalidated, or if row count/cohort fingerprint
mismatch):

```
python -m backend.scripts.ebay_d3_v5_blind_review_server --reviewer Donny --freeze
```

(Note: `--reset-session` was already run once, producing `v5_session_2`, as
recorded in Section 3. Do not run it again — it refuses a second
invalidation, and refuses entirely once `--freeze` has happened.)

## 10. Do-not-do confirmation

- V4 and V5 matcher: not run, not imported.
- No certification metrics computed; no v5 certifier exists yet (unchanged
  from before this task, out of scope here as instructed).
- No current V5 human labels from `v5_session_1` were retained as valid,
  frozen, or exposed to certification.
- The 417-row cohort CSV was not modified (still unfrozen,
  `exact_match_yes_no_uncertain` columns blank for all 417 rows).
- No eBay listings were recaptured; no matcher rules/thresholds/gates were
  touched; no matcher output was exposed; no pricing was published.

EBAY_D3_V5_FRESH_HUMAN_REVIEW_SESSION_READY_FROM_ZERO
