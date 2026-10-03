# Rankings Final Corrective A — Runtime, Trend, and Chase

## Scope and starting point

- Branch: `fix/rankings-final-corrective-a-20261003`
- Fresh `origin/develop`: `d58b9853989a47f950e8e3bb87d7cdbdb2282033`
- Bucket A only. No migration was applied and no production state was changed.

## Two independent failure classes

Trend reaches `read_trend_history()`, which calls the service-role-only
`public.get_pokemon_rankings_trend_history_v1` RPC. The migration defining that
RPC is present in both source mirrors, but the independently audited live
database does not yet contain it in `pg_proc`. Until deployment applies that
migration, Trend is expected to show the controlled `Trend history is
temporarily unavailable.` state. It must not fabricate or calculate history in
the browser.

The Set/Era/Product/Card screenshot failures were a different runtime problem:
the frontend was running while its backend was unreachable, stale, or pointed
at the wrong URL. Card routes also allowed a non-JSON upstream body to reach a
client that blindly called `response.json()`, producing the visible HTML parser
error. All three Card proxies now return JSON for network and invalid-upstream
failures, preserve a real upstream status, forward Cookie and Authorization,
and set `Cache-Control: private, no-store` plus `Vary: Cookie, Authorization`.

## Correct local runtime

Run the FastAPI application from the repository environment at
`http://127.0.0.1:8000`, then run Next development with both
`BACKEND_API_BASE_URL=http://127.0.0.1:8000` and
`NEXT_PUBLIC_BACKEND_API_BASE_URL=http://127.0.0.1:8000`. The verified frontend
for this pass was `http://127.0.0.1:3002` because port 3000 was already occupied.
The `http://127.0.0.1:8001` value is only the established production-build
placeholder; it was never used as the development runtime backend.

Verified runtime responses:

- backend `/health`: 200 JSON
- backend public Rankings headlines: 200 JSON
- backend product catalogue: 200 JSON
- frontend Product Rankings proxy: 200 JSON
- protected scorecards, Card Collector, and Card facets without credentials:
  controlled 401 JSON
- Card proxy with backend intentionally unreachable: controlled 503 JSON,
  private/no-store, correct Vary header

## Overview and Trend UI

The Overview summary now displays Modeled Return from
`overview.openingEconomics.modeledReturnOnSpend`. This is the hierarchical
Opening Economics authority (`sum modeled card value / sum modeled
pack-equivalent cost`), not `packEconomics.expectedRetention`, which is a
different weighting. The observed local snapshot renders 38.7%.

The four Trend metric buttons are one shared `DarkSelect` control labeled
`Metric`. Changing it only updates `metricKey` and the chart projection; it is
not part of the history-fetch effect dependencies and makes no new request.
Sets/Eras, windows, selection behavior, focus, Clear All, Overall line, and
tooltip pinning are unchanged.

## Chase correction

The saturation came from treating already-scaled Benchmark Chase raw model
scores as inputs to `chase_accessibility_overall_score()`. Era presentation also
averaged normalized Set values despite canonical Era raw values being present.

Chase now uses the canonical raw value and the leader in the matching entity
cohort:

`public_100 = 100 * raw_model_value / cohort_leader_raw_model_value`

`display_10 = public_100 / 10`

Examples:

- Set: 73.50 → 10.0; 69.97 → 9.5; 27.13 → 3.7
- Era: 50.15 → 10.0; 40.58 → 8.1

Missing or non-positive leaders remain unavailable. Canonical rank and cohort
are passed through unchanged, and tiers still derive from canonical rank/cohort
semantics. Collector Appeal keeps its prior projection and equal-Set Era
aggregation unchanged.

## Trend migration review

Both migration mirrors define a stable, security-invoker, empty-search-path,
read-only function. Input is limited to 1–22 Set/Era entities and a bounded
date interval. Duplicate publication dates resolve deterministically by
`published_at desc, id desc`. Execute is revoked from public, anon, and
authenticated and granted only to service_role. There is no model execution or
write statement. The SQL was not modified or applied.

`TREND_RPC_SQL_UNCHANGED_AND_READY_TO_APPLY`

## Verification

- Backend focused/API/SQL suite: 55 passed.
- Frontend focused high-value suite: 82 tests, with the initial run exposing
  one new test-path typo; corrected rerun of the touched set: 22 passed.
- Production build: successful with 86 static pages; `/Rankings` First Load JS
  is 121 kB. Existing unrelated lint warnings remain.
- Browser artifacts: Overview/Modeled Return and Trend dropdown at desktop and
  mobile, plus a browser-rendered Card 503 JSON response. Deterministic backend
  fixtures prove non-flat Set/Era Chase. An authenticated browser storage state
  does not exist in this repository, so paid Set/Era/Trend screenshots were not
  fabricated; those paths are covered by service/API/contract tests.
