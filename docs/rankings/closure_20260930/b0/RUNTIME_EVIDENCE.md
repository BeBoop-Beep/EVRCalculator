# Rankings Bucket 0 runtime evidence

## SOURCE_VERIFIED

- `RankingsLazyClient.jsx` gates Era and Set loads on `canViewRankingsIntelligence`; anonymous users receive local locked state and never call scorecards.
- `/tcgs/pokemon/rankings/scorecards` is Plus-gated and returns all four metrics. Removing its guard would expose protected fields.
- `read_scorecards` omits Set logo/symbol columns; `scorecardSetTarget` cannot recover them.
- `_BASE_OPENING_BREAKDOWN_FIELDS` is already the correct narrow public economics preview: identity, counts and average cost per pack.
- Product scores read the current absolute `overallRipScore` and pass it to `benchmark_presentation`, whose default reference is 5.0.
- Product Benchmark code defines a distinct 0–10 family-mean calibration at 5.0; it is not the absolute Full Market ranking value.
- `read_pack_economics` attaches family economics to family rows and only exact Best-Open fields to Product rows.
- Card queries apply filters after selecting global component rank columns; the global-rank semantic must remain unchanged.
- Card/session cache keys include auth identity/access mode and query lens. The Collector component keeps per-lens state; failures have text but no retry action.

## LOCAL_TEST_VERIFIED

Commands and results:

- `frontend\\node_modules\\.bin\\tsx.cmd --test ...` over 13 focused Rankings files: 51 tests, 50 passed, 1 failed. Failure is a stale source-regex expectation in `RankingsLazyClient.authDowngrade.contract.test.mjs`; current callbacks include additional correct auth/entitlement dependencies.
- `python -m pytest backend/tests/unit/db/services/test_rankings_redesign_contract_service.py backend/tests/unit/domain/access/test_index_plan_access.py -q`: 63 passed in 14.95s.
- `python -m pytest backend/tests/unit/db/services/test_product_family_rankings_service.py -q`: 25 passed in 1.32s.
- `python -m pytest backend/tests/benchmark_v1/test_authority.py backend/tests/benchmark_v1/test_publication.py -q`: 13 passed in 16.50s.
- `test_budget_product_ranking_service.py`: command window ended after eight progress dots; no suite result, therefore not a PASS.
- `npm.cmd run build`: successful isolated Next production build `.next-build-31956`; compile 4.1 minutes, 82/82 static pages generated. `/Rankings` route output: 132 B route size, 115 kB First Load JS. Existing lint warnings were emitted; no build failure.

## LIVE_DB_VERIFIED

All checks used the existing `service_read_client` and bounded SELECTs only. No writes, DDL, migrations, model runs or publication calls occurred.

- Global Benchmark: five header samples; latest published global header dated `2026-09-28`, 162 entities.
- Canonical Product Benchmark key/calibration: zero published header samples. This is an observed absence, not a permission failure.
- Product ranking pointer/header: one current V1 snapshot, dated `2026-09-29`, 138 eligible products, Full Market $1,300, V12 authority.
- Product rows: five bounded Full Market samples. Overall absolute scores ranged 48.622–53.073 in that sample; rank/cohort were present.
- Exact sealed identities: five bounded rows successfully joined by product ID.
- Best-Open: one pointer and five bounded exact Product rows; source date `2026-09-08`, with exact current price/status/threshold/gaps.
- Sets artwork coverage counts: 212 total; 174 non-null logos; 174 non-null symbols. Five non-null samples verified both URL fields.
- Scorecard service: 22 Set rows and 2 Era rows. Set row keys did not include artwork.
- Pack Economics service: 22 Sets, 128 families, 138 exact Product children. Exact Product keys were identity plus current price and Best-Open fields only.
- Opening snapshot pointer: market date `2026-09-29`.

## LIVE_DB_BLOCKED

No connection/permission block occurred. Four initial probes selected nonexistent columns (`overall_rip_version` on a pointer view, `method_version`, `product_family` on `sealed_products`, and `id` on the opening pointer) and returned PostgreSQL `42703`. They were corrected with bounded shape reads and are not counted as access failures or PASS results for those invalid queries.

## BROWSER_VERIFIED

An isolated production build was served at `127.0.0.1:3310`. Playwright 1.62.1 with installed Chromium was used after the optional `agent-browser` executable was found unavailable.

- Anonymous `/Rankings`: HTTP 200.
- Cold new context: TTFB 14.6ms, DOMContentLoaded 216.1ms, load 226.6ms, document transfer 19,901 bytes, decoded 89,049 bytes.
- Second new context against warm server/cache: TTFB 11.8ms, DOMContentLoaded 155.7ms, load 165.7ms, same document sizes.
- Anonymous browser made `/api/auth/me` only (6.5ms cold run; 8.1ms second run) during the captured flow.
- Anonymous Era and Set interactions rendered locked state, confirming the current defect against the approved public-access contract.
- Direct anonymous production-proxy checks returned 401: Set scorecards 58.8ms cold/5.4ms warm; Era scorecards 4.4/3.8ms; Product scores 5.0/3.4ms; Product economics 4.3/3.2ms; Card Collector Overall 5.5/4.1ms.

## BROWSER_BLOCKED

- Product Scores -> Economics cold/warm paid switching.
- Cards Overall/Pokémon/Trainer/Artist/Playability and rapid-switch behavior.
- Login -> Cards Overall without refresh and authenticated logout/access-loss.

Reason: no legitimate test login/session was supplied. No credential discovery or auth bypass was attempted. These are BLOCKED, not PASS.
