# Market Explorer corrective data read path - 2026-10-02

## Authority and constraints

- Starting `origin/develop`: `d4e444ce7c87fe2ec6186529c2819c7cd58b641b`.
- Branch: `fix/market-explorer-corrective-data-readpath-20261002`.
- No SQL authority replacement, migration reapplication, production write, merge, or deployment is part of this pass.

## Root-cause matrix

| Layer | Finding | Correction |
|---|---|---|
| Supabase/PostgREST incident | The screenshot window coincided with database connection rejection, PostgREST `PGRST002` schema-cache 503s, and Warp timeout-manager kills. Current direct V2 reads are healthy, so the event is not evidence of a slow V2 SQL design. | Preserve V2 SQL and serving authority. Add stage receipts and one selective proxy retry for safe transient reads. |
| Prepared comparison | Browser and Next proxy both expired at 8,000 ms. A successful proxy response at 8,007 ms could lose to the outer abort. | Browser total is 14,000 ms; proxy total is 11,000 ms. The proxy's retry shares that one total deadline. |
| Prepared constituents | Proxy and client lacked a reliably separated, body-inclusive hierarchy. | Browser total is 14,000 ms; proxy total is 11,000 ms; response-body parsing is inside the browser bound. |
| Asset options | Browser and proxy calls were not independently bounded. Refresh failure discarded usable options. | Browser total is 9,000 ms; proxy total is 6,500 ms. Same-asset last-good data survives a transient refresh failure; it never crosses asset boundaries. |
| Catalog search | Browser had a 3,000 ms bound while the Next proxy had no independent total bound. | Browser total is 9,000 ms; proxy total is 6,500 ms. |
| Retry policy | Each route handled transient transport failures differently. | One shared proxy policy performs at most one retry for narrow transient 502/503 codes or a network reset. Auth, entitlement, validation, unknown-market, generation mismatch, and deterministic timeout responses are never retried. |
| Diagnostics | A slow V2 request identified only the top-level route. | Structured `market_explorer_v2_read` receipts now report `stage`, `elapsed_ms`, and `outcome` for serving pointer, directory, aliases, history, asset options, catalog search, constituent page, and movement enrichment. |

## Timing evidence

- Incident-era receipt: Next prepared proxy completed `200` in approximately **8,007 ms**, which reproduced the equal-deadline race.
- Current direct production evidence supplied for this pass: Prismatic V2 history **~21 ms / 154 rows**; sealed asset options **~14 ms**; project state `ACTIVE_HEALTHY`.
- Contract simulation: a prepared response at **8,007 ms** is below the **11,000 ms** proxy total and **14,000 ms** browser total.
- No timeout was raised to an unbounded 30/60-second value.

## Preserved invariants

- V2 remains authoritative once serving; no V1 fallback was added after cutover.
- Generation mismatch remains fail-closed and is not retried.
- No financial/index value is recomputed in the browser.
- No synthetic data or production mutation is introduced.
