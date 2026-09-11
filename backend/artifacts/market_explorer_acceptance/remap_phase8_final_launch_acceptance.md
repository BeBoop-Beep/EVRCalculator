# Market Explorer Remap — Phase 8 Final Launch Acceptance

## A. Starting SHA

`8dce4f5418eab0fe7e26e8b42911bc0db0fe53cc` on `develop`, equal to `origin/develop` at the start of work.

## B. Phase-8 sitewide search architecture

One public, bounded `GET /search?q=&limit=` backend contract composes the existing Phase-2 `search_pokemon_market_explorer_instruments_v2` leaf authority with the Phase-5 prepared directory. The browser uses one `/api/search` proxy. Prepared matching is deliberately application-layer and bounded to the 143-row directory; leaf typo, token, trigram, and relevance behavior remains owned by the canonical RPC.

## C. Result types and routes

| UI category | Authority | Destination |
|---|---|---|
| Sets | prepared directory | `/TCGs/Pokemon/Sets/{set-slug}` |
| Eras | prepared directory | `/Market/Explorer?prepared={marketKey}` |
| Cards | canonical V2 leaf RPC plus canonical-card identity lookup | `/TCGs/Pokemon/Sets/{setId}/Cards/{canonicalCardId}?variant={variantId}` |
| Sealed | canonical V2 leaf RPC | `/sealed-products/{instrumentId}` |
| Quick Markets | prepared directory | `/Market/Explorer?prepared={marketKey}` |

`prepared_rarity`, `prepared_format`, Screens, custom definitions, baskets, saved/private markets, and graded items are excluded. Enter without an explicitly selected suggestion retains `/priceCheck?query=...`.

## D. Search quality matrix

Live catalog checks passed for `mega dragonite`, `dragonite mega`, `dragnoite`, `dragnite`, `temporal forces gastly`, `gastly temporal forces`, `Pokemon GO Dragonite`, `elite trainer box`, `etb`, `pokemon center etb`, `booster bundle`, `Evolving Skies`, `evolving skies`, `evolvng skies`, `Scarlet Violet`, `Sword Shield`, `Temporal Forces`, reversed `Forces Temporal`, and `Established`. Mixed Set/leaf queries returned intuitive category mixtures without requiring every category. Controlled prepared typo matching was tightened after an early false-positive audit.

## E. Search performance and rate policy

Warm live end-to-end backend samples were 216–512 ms, with most at 230–390 ms; response payloads were bounded by the requested limit (a representative 20-result payload was 1,678 bytes). Responses expose diagnostic `leafSearchMs`, `preparedMatchMs`, and `totalMs`. Header debounce is 275 ms. A dedicated public-search policy permits 30 requests/10 seconds and 600/hour per network-derived pseudonymous identity, independent of Exact and Custom Builder limits. One first-use leaf RPC timeout was transient and did not reproduce.

## F. Basic acceptance

Anonymous and Basic Explore behavior remains available: prepared browsing/search, Set/Era/Quick selection, replacement semantics, chart modes/timeframes, and permitted market information. Compare invokes the Index+ upgrade boundary; Screens and both builders remain unavailable. A prepared deep link was corrected so it opens exactly one active market rather than retaining the default Raw Cards series.

## G. Index+ acceptance

Prepared multi-market comparison, Set/Era/Quick combinations, synchronized chart interaction, comparison analytics, Screens, and contextual rankings retain their accepted access. Custom and Exact execution remain Premium-only.

## H. Premium acceptance

Premium retains the full Index+ surface plus Filtered Custom Builder and Exact Basket V2. The 39-rarity option authority, OR-within/AND-across semantics, preflight behavior, 1–25 mixed Card/Sealed basket boundary, V1 editing compatibility, and prepared/custom comparison path were regression checked.

## I. Prepared-directory parity

Live authority contained 143 entries: 106 Sets, 17 Eras, 6 Quick Markets, 9 prepared rarity markets, and 5 prepared format markets. There were zero duplicate keys and zero missing Set-to-Era parents. The six Quick identities are Obtainable, Intermediate, Premium, New Releases, Established, and Global Top 10.

## J. Date and watermark coherence

All 133 history-capable prepared identities shared `comparison_as_of = 2026-09-08`. Comparison chart/table returns, drawdown, and relative performance continue to use comparison-authority data. No identity had a valid exact one-year baseline; 1Y therefore remains unavailable. Ten Sets remain browse-only and do not synthesize comparison indices.

## K. Screens and contextual rankings

Rarity Leaders, Sealed Format Leaders, Momentum Leaders (canonical 30D), Largest Drawdowns, and Set-context Top by Value/Risers/Fallers remain prepared analytical reads. Instrumentation found no custom build, preflight, cache creation, or lease acquisition from these paths.

## L. Custom Builder

Era/Set scope and Rarity/Pokémon/Price/Release Age filters retain exact OR-within-axis and AND-across-axis behavior. One-match preflights remain valid; true-empty results block builds; lag/unavailable states are not represented as zero.

## M. Exact Basket

Exact remains a standalone Premium tool, independent of Filtered Builder, accepting 1–25 asset-qualified Card/Sealed identities with one unit each and coherent `basketAsOf`. Unavailable is never `$0`; new builds remain V2; V1 read/edit compatibility and the shared cache lifecycle remain intact. Header search does not mutate or bypass Exact eligibility.

## N. Shared chart

`/Market` and `/Market/Explorer` retain the shared chart primitive: Performance rebases each visible series to its first finite observation, Index uses the canonical lifetime index, view-mode changes issue no market-data request, timeframe changes do not change membership, and tooltip/keyboard behavior remains intact.

## O. Information architecture

The Phase-7 hierarchy remains Explore (Sets/Eras/Quick Markets), Compare & Analyze (workspace, analytics, constituents, Screens/rankings), then Build Your Market (Filtered and Exact). Header discovery does not alter it.

## P. Auth and navigation

Search is intentionally public for anonymous, Basic, Index+, and Premium users. It neither consumes builder entitlement nor clears auth state. Existing navigation/session handling remains unchanged; only established 401/403 behavior can clear authenticated state.

## Q. Request and network audit

Browser instrumentation at all four target widths observed exactly one `/api/search` request after debounce. Abort and request-sequence guards prevent stale rendering. Prepared navigation, Screens, visual expansion, and Performance/Index switching generated no custom builds; the latter two generate no market-data request. Search remains navigation/discovery, never a basket mutation.

## R. Cache and lease audit

Read-only live audit before and after acceptance remained 71 cache rows: 61 ready, 8 failed, 2 stale, and 0 building. Search created no cache rows, orphaned builds, or leases.

## S. Migration mirror audit

`npx supabase migration list --linked` verified every Phase 2–6 Market Explorer migration in the live ledger. The corresponding files are present in both `backend/db/migrations/` and `supabase/migrations/` with identical content. No historical migration or live DDL was changed.

## T. Responsive QA

Chromium QA passed at 390, 768, 1280, and 1440 px, including populated search dropdown, long labels, keyboard selection, Escape, Enter fallback, and prepared navigation. Document scroll width equaled client width at every viewport. Evidence is in `phase8_screenshots/`.

## U. Accessibility QA

Header search uses combobox/listbox/option roles, active-descendant and expanded state, Arrow Up/Down, Enter, Escape, visible focus, route/outside dismissal, labeled status states, and at least 44 px result targets. Existing chart keyboard, dialog, upgrade-copy, pressed/selected, and tab-order contracts remain intact.

## V. Performance

No catalog is preloaded into the Header. Prepared matching is an in-memory pass over 143 canonical entries and measured below leaf RPC latency. Representative accepted Browse, three-market comparison, Screen, context ranking, options, preflight, and Exact-search paths showed no new request storm or user-visible Phase-8 regression.

## W. Test results

Focused backend acceptance: 105 passed (2 dependency warnings). Focused frontend Phase 1–8/search/header/chart/auth/Browse/Compare/Screens/Exact/preflight acceptance: 52 passed. The repository-wide frontend contract command also exposes older, unrelated source-text assertions (including obsolete Phase-1 composition/link-size expectations); these were not widened into product changes during the final defect-only phase.

## X. Production build

`npm run build` completed successfully on the final source state. Existing lint warnings outside the Phase-8 search surface remain non-blocking. A concurrent `npm ci` initially caused a transient missing `client-only` prerender failure; a clean dependency install and isolated rebuild passed.

## Y. Defects found and fixed

- Resolved card navigation through canonical card identity instead of treating a variant/instrument identity as the route card identity.
- Prevented broad prepared fuzzy matching from producing unrelated labels.
- Prevented prepared deep links from retaining the default Raw Cards market.
- Updated stale entitlement assertions to the accepted Premium builder contract.
- Made frozen migration hash verification line-ending portable without changing migrations.

## Z. Post-launch backlog only

- Monitor the single non-reproduced cold leaf-RPC timeout.
- If the API is horizontally scaled, move the existing process-local public-search limiter to the platform's shared rate-limit authority.
- Retire unrelated legacy source-text contract assertions in a separate, non-product cleanup.

## AA. Files changed

- `backend/api/main.py`
- `backend/api/paid_abuse_control.py`
- `backend/db/services/sitewide_search.py`
- `backend/tests/unit/api/test_paid_abuse_http.py`
- `backend/tests/unit/db/test_market_explorer_migration_source_sync.py`
- `backend/tests/unit/db/test_sitewide_search.py`
- `frontend/app/api/search/route.js`
- `frontend/app/Market/Explorer/page.js`
- `frontend/components/Header.js`
- `frontend/components/HeaderRuntimeSafety.contract.test.mjs`
- `frontend/components/Search/SitewideSearchBar.jsx`
- `frontend/components/Search/SitewideSearchBar.contract.test.mjs`
- `frontend/components/explore/MarketExplorerClient.jsx`
- `frontend/hooks/explore/useMarketExplorerSelection.js`
- `frontend/app/Market/Explorer/MarketExplorerPage.contract.test.mjs`
- `backend/artifacts/market_explorer_acceptance/phase8_screenshots/*`
- this report

## AB. Final commit SHA

The final implementation commit is recorded by the commit immediately containing this acceptance report (`git log -1 --format=%H`).
