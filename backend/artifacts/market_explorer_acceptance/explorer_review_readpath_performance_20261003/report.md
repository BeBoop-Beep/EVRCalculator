# Explorer review read-path performance acceptance — 2026-10-03

## Verdict

PASS for the corrective branch. Ten repeated Rankings → Explorer cycles passed in both warmed Next development and optimized local production modes with Raw and Total Sealed retained, no prepared timeout banner, no unexpected 5xx, and no console error. No production write, migration, deployment, or SQL authority change was performed.

## Root cause and architecture findings

- The observed multi-second local delay is Next development compilation, not the V2 database reads. A cold development receipt recorded `/Rankings` at 57.087 s while compiling modules; the first Explorer compilation in the earlier cold receipt was 16.985 s. Once warm, the Explorer server stages were tens of milliseconds.
- Raw and Total Sealed are scheduled concurrently with independent prepared-loader adds. They are not serialized.
- The server render reads overview, prepared directory, and auth concurrently. It does not fetch Raw/Sealed histories, so hydration does not repeat a server history request.
- Combining Raw and Sealed into one public comparison request would change existing comparison-entitlement semantics; this pass therefore preserves the two concurrent requests.
- A generation-valid loaded series remains in the loader during refresh. A transient refresh failure records an error but does not discard the last-good baseline.

## Timing receipts

| Layer / mode | Minimum | Average | Maximum | Notes |
|---|---:|---:|---:|---|
| Next dev cold `/Rankings` | — | — | 57,087 ms | compilation-dominated |
| Warm dev Rankings → Explorer/chart ready, 10 cycles | 467.3 ms | 737.8 ms | 927.3 ms | 2 active baseline series every cycle |
| Warm dev prepared proxy POST | 54.1 ms | 70.2 ms | 141.4 ms | browser-observed |
| Optimized local production Rankings → Explorer/chart ready, 10 cycles | 388.6 ms | 906.5 ms | 1,277.5 ms | 2 active baseline series every cycle |
| Optimized local production prepared proxy POST | 5.4 ms | 9.2 ms | 15.6 ms | browser-observed |
| Warm proxy upstream/backend prepared read | 2 ms | 3–5 ms | 7 ms | structured server log samples |
| Supplied production DB Raw + Sealed V2 history | — | ~3 ms | — | 334 rows; pre-existing measurement |
| Supplied production DB Prismatic catalog search | — | ~12 ms | — | pre-existing measurement |
| Supplied production DB exact Dragonite search | — | ~121 ms | — | pre-existing measurement |

Exact item first-result measurements include the 225 ms debounce. Development: Dragonite 266.3 ms, Dragonite ex 265.8 ms, Umbreon 259.1 ms, Evolving Skies 265.8 ms, booster bundle 267.5 ms. Optimized production: 248.3 ms, 252.4 ms, 251.5 ms, 236.5 ms, and 240.3 ms respectively. These browser receipts use the deterministic local backend fixture; the production DB figures above are reported separately and were not conflated with fixture latency.

Screens remained fast and were not changed. Development Top Sealed / Worst Sealed / Rarity / Sealed Format: 68.9 / 137.3 / 50.4 / 47.7 ms. Optimized production: 56.4 / 142.6 / 48.0 / 49.1 ms.

## Corrective behavior

- Exact-item search now uses a 225 ms debounce, AbortController propagation, stale-response token, explicit 9 s browser bound over a 6.5 s proxy bound, one safe proxy retry for approved transient 502/503/network failures, and a one-minute query+scope session cache. Ranking remains backend-owned.
- Query-built constituent paging now uses the bounded transport, abort propagation, and structured AUTH / ENTITLEMENT / TIMEOUT / UNAVAILABLE errors. Paging errors are held by the constituents hook and cannot remove an active market or chart series.
- Exact baskets close only after confirmed success. A failed five-item (three Cards + two Products) build retains the modal and all selections. Duplicate outcomes remain open and do not create a second market.

## Evidence files

- `dev-timings.json`
- `production-timings.json`
- `dev-readpath.png`
- `production-readpath.png`

Both browser runs recorded zero unexpected 5xx, zero unexpected request failures, zero console errors, zero prepared timeout banners, and two or more active series throughout all ten cycles. Navigation-triggered `net::ERR_ABORTED` background reads are recorded separately as expected cancellation, not transport failure.
