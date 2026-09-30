# Bucket 4 acceptance matrix

| Requirement | Status | Evidence |
| --- | --- | --- |
| R06 control inside Product workspace | PASS | `AnalyticsTableShell.toolbarControl` hosts the keyboard-accessible Scores/Economics segmented control. |
| R07 public Product browsing | PASS | Public catalogue, names, stable alphabetic sorting, search, and family controls remain independent. |
| R09 ordinary locked cells | PASS | Public Scores/Economics tables retain locked metric cells and issue no paid read. |
| R27 persistent Overall/reference area | PASS | Reference strip is outside sorted rows and unaffected by query/family/sort. |
| R28 correct score semantics | PASS | Absolute V12 is explicit `0-100`; Benchmark is an explicit optional `0-10` authority. No conversion, clamp, or 5.0 fallback. |
| R29 clean Best-Open cell | PASS | Default cell contains one threshold plus info trigger; stacked gap/status copy removed. |
| R30 accessible exact-SKU popover | PASS (source/fixture) | Exact threshold/market/difference/direction/dates/status with button, click/touch, Enter/Space, Escape and focus restoration. Browser smoke blocked by configuration. |
| R31 authoritative MSRP only | PASS | No numeric MSRP; concise unavailable state. |
| R32 precise interpretation | PASS | Signed `market - threshold`; percentage uses market denominator; explicit above/below wording. |
| B1 regressions | PASS | Focused public-access contracts pass. API boundary runtime test is dependency-blocked. |
| B2 regressions | PASS | Benchmark `/10`, neutral metrics, Set artwork, and neutral toggles pass. |
| B3 regressions | PASS | Direct exact Products, distinct economics, unchanged aggregates, and canonical entertainment behavior pass. |
| Request behavior | PASS (fixture) | One cached authority request per mode; no per-row benchmark/Best-Open requests. |
| Live Product reference check | BLOCKED | `LIVE_PRODUCT_REFERENCE_VERIFICATION_BLOCKED`. |
| Full build/browser | BLOCKED | `FULL_BUILD_BLOCKED_MISSING_BACKEND_API_BASE_URL`. |

Verdict: `B4_CODE_READY_FOR_REVIEW`.
