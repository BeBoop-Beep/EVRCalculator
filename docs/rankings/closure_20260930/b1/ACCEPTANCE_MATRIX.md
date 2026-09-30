# Bucket 1 acceptance matrix

| Requirement | Result | Evidence |
|---|---|---|
| R01/R02 public Era Overall score/rank | PASS | Narrow public headline endpoint; live response: 2 Era rows. |
| R03/R04 public Set Overall score/rank | PASS | Narrow public headline endpoint; live response: 22 Set rows. |
| R05 paid component metrics protected | PASS | Public response forbidden-field scan: 0 hits; paid scorecards still gate before DB work. |
| R06 Era economics preview preserved | PASS | Existing public opening-economics path unchanged. |
| R07 narrow Set Pack Economics preview | PASS | Live response: 22 Sets; only identity/artwork, two counts, average cost, and date. |
| R08 independent public Product catalogue | PASS | Live response: 1,774 direct `sealed_products` rows after pagination; no ranking authority read. |
| R09 public Product locked analytics | PASS | Production-build Playwright smoke rendered alphabetical rows and ordinary locked cells in Scores and Economics. |
| R39 logout/downgrade cache safety | PASS | Paid Product and Set component state is cleared on entitlement loss; session cache is identity-scoped; contract tests pass. |
| Set artwork | PASS | Live Set headline and preview responses: 22/22 rows have logo or symbol; scorecard target adapter forwards both fields. |
| No ranked/top-N public Product ordering | PASS | Server and anonymous UI sort name A–Z with ID tie-break; response has no rank/score/economics fields. |
| Production build | PASS, with environment note | `npm.cmd run build`; optimized build completed, 85/85 static pages generated; only pre-existing warnings. A later repeat after the artwork adapter change was blocked because the shared `node_modules/next` installation was concurrently removed/locked (`MODULE_NOT_FOUND`, then `ENOTEMPTY`/`EPERM`). The adapter is covered by the final 64/64 frontend run. |
| Browser smoke | PASS (fixture runtime) | Production server plus Playwright fallback: Era, Set, Pack preview, alphabetical Products, and locked Product cells passed. |
| Live DB runtime | PASS | Authorized local service-read connection returned 22 Sets, 2 Eras, 22 pack previews, and 1,774 Products. |

Focused automated results: backend 30/30; frontend 64/64.
