# Market Explorer constituent windows — Bucket 1 acceptance

Date: 2026-09-30  
Production project: `zwxzxuuawalvwioadhmf`  
Starting `develop`: `61f364d2c6aba321ca77a3f21e977cc6cf5b20a9`

## Contract and implementation

The canonical transport keys are `1D`, `7D`, `30D`, `3M`, `6M`, `1Y`, and
`SinceTracking`. `LT` / `Since Tracking` are presentation labels only. Fixed
windows use true elapsed calendar targets (`as_of - N days`) and the newest
trustworthy observation on or before the target. `1D` uses the previous
observed point. `SinceTracking` uses the earliest trustworthy tracked day and
does not substitute release-date pricing. Every endpoint is USD, positive,
same-product, at or before the requested as-of day, and ties resolve by
`captured_at`, then observation `id`. Missing evidence is `NULL`; equal valid
endpoints are numeric zero.

Inspected authorities:

- `backend/domain/pokemon/constituent_movement.py`
- `backend/domain/pokemon/market_index.py` (`resolve_market_window_target` and
  `resolve_window_baselines`)
- `backend/db/services/market_explorer_constituent_movement.py`
- V2 card daily/interval tables and prepared/query-built service paths
- `sealed_product_price_observations`
- `get_pokemon_market_explorer_sealed_constituent_movement_v1(uuid[],date)`
- prepared constituent, surface freshness, asset-options, and Screen RPCs

V1 was preserved. It remains a four-window compatibility contract. The new
additive `get_pokemon_market_explorer_sealed_constituent_movement_v2(uuid[],date)`
is limited to 1–100 IDs, one as-of date, and one backend RPC per page. It adds
6M, 1Y, and SinceTracking dates and movements. Only `service_role` can execute
V1 or V2; `anon` and `authenticated` cannot. No index was added.

## Card path audit

The shared domain already computes all seven keys. Query-built card markets
(including canonical query-built Rarity) publish both row `changes` and
market-level `movementWindows`. Prepared Set/Era/Rarity pages are enriched from
V2 daily states with V2 interval fallback and also retain all seven keys.
There is no backend serialization strip.

Current accepted card history contains 169 published days, 2026-04-07 through
2026-09-29. Consequently 6M (target 2026-04-02) and 1Y are truthfully
unavailable on the sampled prepared pages. SinceTracking is supported by the
contract but is per-row `NULL` when that row lacks a real price on the market's
resolved first tracking date. The remaining consumer-side loss is explicit:
`frontend/lib/explore/marketExplorerConstituents.mjs` currently limits its
selector to `1D`, `7D`, `30D`, `3M`; the next UI bucket should expose the three
already canonical additional keys without calculating them in the browser.

## Sealed V1 gap and V2 result

V1 exposes only 1D/7D/30D/3M. V2 exposes end price plus baseline date and
movement for all seven windows. Fixed cutoffs match the canonical graph date
resolver. The endpoint is restricted to the requested market day, and all
baseline predicates prohibit future lookahead. The earliest-day LT lookup uses
the last deterministic observation on that earliest day.

At the current 2026-09-29 surface, sampled Sealed Set (Crown Zenith, 34 rows)
and Sealed Type (Elite Trainer Box, 79 rows) coverage was:

| Cohort | 6M | 1Y | SinceTracking |
|---|---:|---:|---:|
| Sealed Set | 0/34 | 0/34 | 34/34 |
| Sealed Type | 0/79 | 0/79 | 78/79 |

6M and 1Y are currently unavailable because production tracking begins after
their target dates; V2 returns `NULL` rather than relabeling shorter history.

## 3M zero audit

Method: pin the currently served generation and its 2026-09-29 page prices;
resolve the 90-day target to the latest accepted observation on or before
2026-07-01; sample no more than 100 rows per cohort; compare positive exact
instrument endpoints; then inspect every exact-zero row across the interval.

| Cohort | Sample | REAL_ZERO | MISSING_BASELINE | STALE_OR_CARRIED_STATE | DATA_DEFECT |
|---|---:|---:|---:|---:|---:|
| Ancient Origins Set | 100 | 2 | 0 | 0 | 0 |
| modern Cards Set (Phantasmal Flames) | 100 | 5 | 0 | 0 | 0 |
| vintage Cards Set (Fossil — 1st Edition) | 62 | 1 | 0 | 0 | 0 |
| prepared Rarity (Rare Ultra) | 100 | 1 | 7 | 2 | 0 |
| Sealed Set (Crown Zenith) | 34 | 0 | 0 | 0 | 0 |
| Sealed Type (Elite Trainer Box) | 79 | 1 | 3 | 0 | 0 |
| **Total** | **475** | **10** | **10** | **2** | **0** |

Representative confirmed REAL_ZERO rows include Dangerous Energy
(`$0.25 → $0.25`, 86 dated states, 4 distinct prices inside the span), Inkay
(`$0.11 → $0.11`, 86 dated states, 10 distinct prices), and Steam Siege Elite
Trainer Box (`$1800 → $1800`, 88 dated TCGPlayer observations).

The two explicit carried-state reviews are Rare Ultra Entei-EX (`$320`) and
White Kyurem-EX (`$509.97`). Each has one unchanged open V2 price interval
spanning the full requested period, so these were not certified as REAL_ZERO.
They were also not changed automatically. No missing baseline was observed
being coerced to zero, so the false-zero count is zero. No identity, date,
currency, or condition DATA_DEFECT was found.

## Performance and bounds

Warm-cache `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` on production:

| IDs | execution | shared hits | reads | temp I/O |
|---:|---:|---:|---:|---:|
| 1 | 5.805 ms | 929 | 0 | 0 |
| 25 | 34.034 ms | 13,791 | 0 | 0 |
| 100 | 114.155 ms | 56,286 | 0 | 0 |

The 101-ID rejection was exercised and returned
`SEALED_MOVEMENT_REQUIRES_1_TO_100_IDS_AND_AS_OF`. The existing
`sealed_product_price_observations_product_date_id_idx` served the bounded
lookups. Supabase performance/security advisors did not flag the new function.

## Sealed Types, Screens, and freshness

Asset options remain truthful: 36 types total, 34 `PREPARED_CANDIDATE`, 34
with real prepared keys, 34 available, and two unavailable. First Partner Pack
and World Championship Deck each have zero current priced products and remain
unavailable. The DB is not the cause of general Sealed Type unclickability.

The global omitted-asset Screen RPC returned ten rows, mixed Cards and Sealed,
with a hard maximum of ten. The observed `Locked` state is an application
access issue, not missing Screen data; Screen DB semantics were not changed.

Final freshness remains truthfully `STALE / CARD_DAILY_NOT_CURRENT`:
canonical/raw 2026-09-30; card daily, sealed daily, sealed metadata, prepared V1,
and surface V2 2026-09-29; lag one day; maintained caches 37/37 current. The
existing guarded publisher was invoked for Sep 30 and failed closed because
the prepared generation is still Sep 29. No Sep 30 stamp was applied to Sep 29
data.

## Backend handoff contract

Each sealed row now carries `changes` and `changeBaselines` for exactly:
`1D`, `7D`, `30D`, `3M`, `6M`, `1Y`, `SinceTracking`. Values are numbers or
`null`; consumers must never derive or zero-fill them. Cards use the same
`changes` keys and additionally publish shared `movementWindows`. The next
bucket may display `SinceTracking` as `LT`, but must send/read the canonical
`SinceTracking` key.
