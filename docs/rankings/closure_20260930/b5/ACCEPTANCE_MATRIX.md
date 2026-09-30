# Bucket 5 acceptance matrix

| Requirement | Status | Evidence |
| --- | --- | --- |
| R16 remove duplicate chips | PASS | Both history selectors use `showChips=false`; obsolete capped chip row removed. |
| R17 single visible legend | PASS | One scroll/wrap legend contains every plotted identity, marker, name, and accessible removal. |
| R18 permanent Overall | PASS | No Overall remove control; final entity removal rebuilds authoritative Overall-only points and preserves chart/window. |
| R19 subdued strong Overall | PASS | Overall width 3, entity width 1.75, opacity 0.72. |
| R20 compact tooltip | PASS | Date once, Overall once, color/name/signed delta rows; no rank/cohort/repeated metric label. |
| R21 hovered-score order | PASS | Score descending, then stable name/ID; missing observations omitted, missing Overall yields unavailable delta. |
| R22 preserve history/selectors/windows | PASS | Existing range functions/search controls preserved; `connectNulls=false`; no interpolation or value changes. |
| Era preset above five | PASS | Preset path stores every Era Set; only manual path slices to five; existing request maximum is 22. |
| Stable identity colors | PASS | Hash-based color tests and shared series color usage. |
| Rapid/stale safety | PASS (source) | Effect cleanup ignores superseded promises; current selection is never restored from response state. |
| Request volume | PASS (source/model) | Local removal/re-add reuses loaded payload; additions/windows issue one bounded request; hover issues none. |
| Access boundary | PASS | Existing Index Plus guard and locked preview unchanged. |
| B1–B4 regressions | PASS | 32/32 focused contracts. |
| Production build/browser | BLOCKED | `FULL_BUILD_BLOCKED_MISSING_BACKEND_API_BASE_URL`; no URL invented. |

Verdict: `B5_CODE_READY_FOR_REVIEW`.
