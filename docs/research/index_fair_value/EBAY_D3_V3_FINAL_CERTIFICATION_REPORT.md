# eBay D3 v3 final independent certification

Frozen v3 predictions were unsealed once and scored against frozen human gold. The
precision cohort has 297 TP and 3 FP across 300 HIGH rows:
precision 99.0000%, Wilson 95% CI [97.1017%, 99.6593%].

The coverage cohort has 205 HIGH TP, 2 HIGH FP,
recall 82.9960%, and covers 55/70 cards (78.5714%).
Unique catastrophic HIGH errors: 5. Gates: {"catastrophic": false, "coverage": false, "precision": true, "wilson_lower": false}.
Final result: **FAIL** (`EBAY_IDENTITY_MATCHER_V3_NOT_VALIDATED`).

Authority is limited to HIGH-confidence active-listing identity filtering only when all
four gates pass. Active listings are offered supply/asking-price observations, not
completed sales. Asking-price authority, Fair Value, forecasting, recommendations, and
production pricing replacement are not validated here.
