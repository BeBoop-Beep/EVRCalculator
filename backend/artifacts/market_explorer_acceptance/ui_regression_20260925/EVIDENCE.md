# Market Explorer live UI regression - browser evidence (2026-09-25)

Branch `fix/market-explorer-live-ui-regression-20260925`, based on `origin/develop` f084d409 (PR #381 merge).
Specs: `frontend/e2e/market-explorer/*.playwright.spec.mjs` (fixture backend + helpers alongside). Raw numbers: `measurements.json`.

## Modes (what each proves)

| Mode | Frontend | Backend | Auth |
|---|---|---|---|
| LIVE-ANON (V1 fallback, real data) | Next dev, this branch | the user's real backend `:8001`, read-only anonymous GET/POST | anonymous only; no paid states |
| FIXTURE V1 | Next dev :3203 | `e2e/market-explorer/fixtureBackend.mjs` :8202 | `token=fixture-plus` cookie = FIXTURE identity |
| FIXTURE V2 (NOT LIVE - V2 serving generation is NULL in prod) | Next dev :3202 | same fixture module :8201 | fixture identities |

The fixture backend mirrors the real entitlement rules (>1 unique key across marketKeys+contextMarketKeys needs Index+; constituents need Index+). No token is minted; no real auth is bypassed.

## Reproduction on develop f084d409 (before the fix)

Anonymous, real backend, Fossil then Jungle (`repro-BASELINE-desktop-*.png`):

    POST /api/market/explorer/prepared {"marketKeys":["set:c868..."],"contextMarketKeys":[]}            -> 200
    POST /api/market/explorer/prepared {"marketKeys":["set:37e1..."],"contextMarketKeys":["set:c868..."]} -> 401

Page text then contained "Sign in" and rows read "+ Compare with Index+". After the fix (`repro-FIXED-*`): Jungle POST has `contextMarketKeys: []`, 200, no prompt.

Root cause: `begin(key,{replaceOthers:true})` in `marketExplorerPreparedLoader.mjs` still built `contextKeys` from the currently loaded market; the backend correctly counts two unique keys as a comparison.

## Measured: View / Hide Constituents & Comparison centre offset (px)

Horizontal centre of the button vs the chart workspace / details overlay (Playwright bounding boxes; tolerance 4px). The control was already centred in every viewport on this branch, so the reported mis-centring did NOT reproduce here (0.00-0.01px).

| Viewport | View vs chart pane | Hide vs details pane | Hide vs chart pane |
|---|---|---|---|
| 1440x900 | 0.01 | 0.00 | 0.00 |
| 1366x768 | 0.01 | 0.00 | 0.00 |
| 1920x1080 | 0.01 | 0.00 | 0.00 |
| 390 mobile | 0.01 | 0.00 | - |

Purple glow: computed `box-shadow` contains `rgba(139, 92, 246, .35)` on both buttons; close/reopen twice verified.

## Other measurements

- Switcher: Fossil page-1 constituent requests = 2 before switching, 2 after returning (cache hit; the 2 are the dev-mode double effect, unchanged by returning).
- Focus: focused line `hsl(340 70% 62%)` opacity 1; other lines `rgb(148,163,184)` opacity 0.5; magnifier is left of the label and opacity 0 until hover/focus, always visible on touch.
- Rarity (V2 fixture): GX/V -> build (truthful message), EX/VMAX/VSTAR -> blocked with reason, Rare Ultra/Rare Secret/Ultra Rare/Special Illustration Rare -> prepared (market added).

## Re-run

    FIXTURE_BACKEND_MODE=v2 FIXTURE_BACKEND_PORT=8201 node frontend/e2e/market-explorer/fixtureBackend.mjs
    FIXTURE_BACKEND_MODE=v1 FIXTURE_BACKEND_PORT=8202 node frontend/e2e/market-explorer/fixtureBackend.mjs
    (Next dev servers on :3202 -> 8201 and :3203 -> 8202, each with its own PERF_AUDIT_DIST_DIR; optional :3200 -> a real backend for EXPLORER_LIVE=1)
    cd frontend && EXPLORER_LIVE=1 npx playwright test -c e2e/market-explorer/playwright.config.mjs   # 28 passed

## Known remaining network noise (live-anonymous)

401 /api/auth/me (anonymous, expected); 503 /api/market/explorer/asset-options (real backend has no asset-options RPC yet: page tolerates it); 401 constituents (deliberate locked state, requested twice by the dev-mode double effect).

## Not proven

Buildable rarity execution (Rare Holo GX/V) needs the query endpoint the fixture does not model: the UI issues the call and shows a truthful message, the built market itself is not proven. Real Index+/Premium sessions and V2 live serving are unproven (fixture identities only).
