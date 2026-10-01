# Bucket 2 acceptance matrix

| Requirement | Status | Evidence |
|---|---|---|
| R10 main benchmark score presentation | PASS (source/test) | `RankingsRipScoreBadge` retains benchmark-10 formatting and hides only its visible caption. |
| R11 decorative benchmark arrows removed | PASS (source/test) | Position indicator removed from Rankings score primitives. |
| R12 neutral component metrics | PASS (source/test) | Era and Set Financial/Collector/Chase use `RankingsNeutralMetric`; mobile accessible labels retained. |
| R13 Set artwork consistency | PASS (source/test) | Set Overall existing path plus paid scorecards, Pack desktop/mobile, and Overview Top Set use `SetIdentity` and bounded projections. |
| R14 Pack Economics presentation only | PASS (source/test) | Parent identity changed; hierarchy and economics values remain intact. |
| R15 Rankings sub-toggle treatment | PASS (source/test) | Rankings-only neutral variants and scoped Product-family CSS; focus-visible retained. |
| R38 Product score safety | PASS (source/test) | No conversion/clamp/publication; `B4_PENDING_PRODUCT_SCORE_REFERENCE`. |
| B1 public Era Overall | PASS (regression suite) | B1 public contract remains unchanged. |
| B1 public Set Overall | PASS (regression suite) | B1 public contract remains unchanged. |
| B1 narrow public Pack preview | PASS (regression suite) | Preview allowlist and gates unchanged. |
| B1 alphabetical Product catalogue | PASS (regression suite) | Catalogue code unchanged. |
| B1 paid-data protection | PASS (regression suite) | Paid endpoint/auth gates unchanged. |

Runtime/build results are recorded in the completion report. A blocked or deferred environment check is not promoted to PASS.
