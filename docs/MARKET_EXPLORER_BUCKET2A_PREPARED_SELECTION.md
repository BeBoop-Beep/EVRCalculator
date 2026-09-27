# Market Explorer Bucket 2A: prepared selection, error isolation, constituents

## Root causes (from source)
1. **Selection poisoning.** `MarketExplorerClient` put a clicked prepared key into
   `preparedActiveKeys` immediately and re-POSTed the WHOLE list on every change.
   A failed key stayed "active" in Browse/Rarity/Screens, was re-sent with every
   later request (one bad market failed every later comparison), and a failed
   refetch left removed markets' lines on the chart.
2. **Constituents.** `fetchPreparedConstituentPage` and the Next proxy existed but
   `backend/api/main.py` had no `/market/explorer/prepared-constituents` route and
   `market_explorer_prepared_directory.py` had no `read_prepared_constituents`
   (a unit test already imported it). The DB RPC
   `get_pokemon_market_explorer_prepared_constituents_v2` already existed in both
   migration trees (20260919225518). `buildPreparedSeries` carried no
   generation/identity and never set `queryFingerprint`, so every prepared
   market fell through to the generic "next market publication" message.

## Architecture: independent per-market fetch (option B)
Every field in a comparison row is computed per market (row, history, window
movements, count). Nothing needs a shared server comparison, so the client fetches
only the market being added, removal is local, and a failure touches only the
market that failed. Loaded histories are never refetched. `contextMarketKeys`
carries the other markets on the chart for the Index+ compare entitlement only;
the backend never reads them. No financial math changed and none moved to React.

Lifecycle (`frontend/lib/explore/marketExplorerPreparedLoader.mjs`, one instance
for Sets/Eras/Quick/Rarity/Sealed/Screens): IDLE -> LOADING -> LOADED | FAILED.
"Active" means LOADED; `pending` and `failed` are separate sets. Per-key request
tokens make stale/out-of-order/removed responses inert; each request has a 20s
bound (TIMEOUT); AbortError is never an error; failures are classified
(auth / entitlement / unavailable / timeout / invalid key / transient).

## Constituent authority per market type (dispatched inside the RPC by the
directory row's own `source_kind`, never by label)
| Market | Authority |
|---|---|
| Era / Quick (curated) / prepared rarity | `pokemon_market_explorer_query_cache` (+ `_constituents`), fingerprint = `prepared_series_key`, verified against `source_as_of` |
| Set | `get_pokemon_cards_daily_constituents(root set, source_as_of)`: the dated canonical Set roster |
| Sealed format | published `sealedSegments[segmentKey].currentConstituents` for the same `source_as_of`; refused unless complete |
Movement: cards only, via `enrich_card_constituent_page` (accepted V2 authority).
Sealed has no accepted movement authority and reports `movementAvailable: false`.
Generation safety: the RPC returns `GENERATION_MISMATCH` (HTTP 409) if the serving
generation changed; the UI reloads that market and re-pages from rank 0.

## Not applied / not verified
No migration was added. Live behaviour (RPC deployed and healthy, latencies, real
roster counts) was NOT verified by this change.
