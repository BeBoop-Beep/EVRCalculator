# eBay E2.1B — D3-v4 Fresh-Blind Human Review UI + Label Freeze Tooling

## 1. Files changed

New:
- `backend/scripts/ebay_d3_v4_blind_review_server.py` — the dedicated V4 review server (loads/summarizes/serves/freezes; never imports the matcher's `classify_listing`).
- `backend/tests/unit/scripts/test_ebay_d3_v4_blind_review_server.py` — 21 tests.

Modified (narrow, justified fix, not a matcher/threshold change):
- `backend/scripts/certify_ebay_d3_v4_fresh_blind.py` — `_human_error_class()` only
  accepted its own original lowercase single-word values (`"lot"`, `"conflict"`,
  etc.). The task's required UI enum strings (`LOT_OR_BUNDLE`,
  `SEALED_OR_NON_CARD`, `INCONSISTENT`, `NOT_VISIBLE`, ...) did not match, which
  would have silently broken catastrophic-error classification once real
  labels arrive. Extended the acceptance sets to include both the original
  values and the UI's enum strings (case-insensitive), and fixed a latent bug
  where `NOT_VISIBLE`/blank language would have been wrongly flagged as
  `WRONG_LANGUAGE`. No gate, threshold, or matcher logic changed — confirmed
  by rerunning the existing 21 E2.2 certifier tests unchanged (still 21/21
  passing).

Not touched: `ebay_d3_matcher_v4.py`, `ebay_d3_matcher_v3.py`, any gate
threshold, the 420-row cohort file's row membership, or any historical D2/D3
gold artifact.

## 2. Exact launch command

```
python -m backend.scripts.ebay_d3_v4_blind_review_server --reviewer Donny
```

Optional: `--port 8765` (default).

## 3. Exact browser URL

```
http://127.0.0.1:8765
```
(opened automatically half a second after the server starts, matching the
existing `ebay_gold_review_server.py` convention.)

## 4. Exact summary command

```
python -m backend.scripts.ebay_d3_v4_blind_review_server --reviewer Donny --summary
```

Verified live against the real cohort in this session (read-only, no server
started, no matcher touched):
```json
{
  "frozen": false,
  "primary_label_counts": {},
  "remaining_rows": 420,
  "reviewed_rows": 0,
  "reviewer_id": "Donny",
  "total_rows": 420
}
```

## 5. Exact freeze command

```
python -m backend.scripts.ebay_d3_v4_blind_review_server --reviewer Donny --freeze
```

Refuses unless: exactly 420 rows exist, every row has all 8 label fields +
reviewer_id + timestamp populated (from the append-only history), no
forbidden matcher-derived column exists in the queue header, and the
recomputed cohort fingerprint still matches the one recorded in
`ebay_d3_v4_fresh_blind_manifest.json`. After a successful freeze it
automatically runs `certify_ebay_d3_v4_fresh_blind.check_preconditions()`
(fingerprint/completeness checks only — no listing is classified) and prints
the result, confirming the certifier now sees a ready state.

## 6. History artifact path

```
backend/artifacts/index_fair_value/ebay_d3_v4_fresh_blind_review_history.jsonl
```
Append-only; `label` and `undo` events only; undo never deletes a prior
event, it appends a new event referencing the target's `event_id`. Effective
state is reconstructed fresh from this file on every server request, so the
process is fully resumable after a stop/restart.

## 7. Confirmation the matcher was never invoked

- `ebay_d3_v4_blind_review_server.py` has **no module-level import** of
  `ebay_d3_matcher_v3`/`v4` (verified by AST inspection in
  `test_server_module_never_imports_or_calls_matcher_at_top_level`) and never
  calls `classify_listing` anywhere in its source (grepped directly).
- The one place it touches matcher code at all is the optional post-freeze
  call to `certify_ebay_d3_v4_fresh_blind.check_preconditions()`, which only
  calls `v4.rule_fingerprint()` (a static hash of config/patterns) — it does
  **not** call `classify_listing`.
- `test_freeze_and_summary_never_call_classify_listing` monkeypatches
  `ebay_d3_matcher_v4.classify_listing` with a call-counting spy and asserts
  the count is exactly 0 after a full label→freeze→summary cycle.
- A caught issue during development: `read_history()`/`append_event()`
  originally bound their file-path default arguments at function-definition
  time, which — if left in place — would have caused monkeypatched test paths
  to silently fall through to the **real** production history file. This was
  caught by the test suite itself (real artifact file grew during a test
  run), fixed (defaults now resolve the module-level path at call time, not
  def time), and the accidentally-created real file was deleted. Verified
  clean afterward: `labels_exist: false`, `0/420` labeled, no history file
  present outside test runs.

## 8. Tests / results

```
21 passed  -- test_ebay_d3_v4_blind_review_server.py (new, this task)
284 passed -- full backend/tests/unit/scripts -k "ebay or fair_value" (no regressions vs E1/E2/E2.1/E2.2)
```

Covers all 20 required areas: exact 420-row load, matcher-field-free HTML
rendering, no top-level matcher import, append-only event creation, resume
reconstruction, undo semantics (including the no-prior-label case),
all-required-fields capture, honest uncertain-value storage, incomplete-review
freeze refusal, cohort-fingerprint-mismatch freeze refusal, forbidden-column
freeze refusal, exact 420-row materialization, byte-for-byte preservation of
original listing columns, `labels_exist`/`labels_frozen` manifest updates,
label-fingerprint recording, no fabricated Reviewer B/adjudication, refused
post-freeze writes, the existing E2.2 certifier still refusing before freeze,
the existing E2.2 certifier's preconditions passing after a fixture freeze,
and zero `classify_listing` calls across the whole label→freeze→summary cycle.

## Status

The real 420-row cohort is unchanged (still 0/420 labeled, `labels_exist:
false`) — this task built and proved the tool, it did not perform the
labeling itself. Donny can now run the launch command above to begin
labeling; `--freeze` will refuse until all 420 rows are complete, and E2.2's
certifier can then be re-run.

**`EBAY_D3_V4_HUMAN_REVIEW_UI_READY`**
