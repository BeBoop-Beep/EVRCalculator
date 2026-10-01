# Bucket 4 acceptance matrix

| Area | Result | Evidence |
|---|---|---|
| Relational paid authority | Implemented | `product_rankings_v2_service.py` |
| Old Product snapshot dependency | Removed from paid endpoints | `_rankings_product_v2` has no lens/snapshot call |
| Chase scalar and labels | Implemented | canonical helper; `Chase` / `Collector Appeal` |
| Exact Recover Cost | Implemented | exact SKU + source-run composite key |
| Adaptive precision | Implemented | shared `formatRecoverCost`; tiny-positive tests |
| Paid pagination | Implemented | default 25, maximum 100, metadata and UI |
| Public pagination | Implemented | identity-only requested page |
| Page-first enrichment | Implemented for normal Product ordering | one simulation and one Best-Open batch |
| Entitlement boundary | Preserved | gate precedes authority access |
| B1/B2/B3 files | Unchanged | no changes to tier, Set/Era, Pack, or history features |

Browser capture against controlled fixtures was not available in this local
run; production build and automated contracts are recorded separately.
