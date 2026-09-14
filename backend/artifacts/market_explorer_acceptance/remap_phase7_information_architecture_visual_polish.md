# Market Explorer Remap Phase 7 — Information Architecture + Visual Polish

## Outcome

Phase 7 reorganizes the existing Market Explorer source into three explicit user-intent zones without changing market data, calculations, search contracts, cache behavior, or entitlement rules:

1. **Explore Markets** — the prepared Set, Era, and Quick Market directory.
2. **Compare & Analyze** — overview signals, Active Markets, the comparison chart, detail table, constituents, Screens, and context rankings.
3. **Build Your Market** — Custom Filtered Market and Exact Basket as sibling construction paths.

The product header now states: “Market Explorer” and “Explore. Compare. Build your own Pokémon markets.”

## Visual changes

- Added consistent numbered zone headers and restrained teal hierarchy cues.
- Made Compare & Analyze the primary research surface through border and depth treatment.
- Preserved the chart as the dominant visual object.
- Consolidated Performance / Index and timeframes into one desktop toolbar; mobile uses a wrapped layout with horizontally scrollable timeframe controls.
- Strengthened the shared Performance / Index segmented control to a 40px target, clearer selection fill, and keyboard focus treatment. `/Market` continues to use the same shared component.
- Demoted Clear Graph to a low-emphasis supporting action.
- Grouped Details, Constituents, Screens, and context ranking into a coherent inspection area.
- Removed the duplicate top-level Browse heading and lock icon noise from the Exact Basket call to action.

## Responsive browser QA

Real Chromium renders were captured at 390, 768, 1280, and 1440 CSS pixels against the local Next.js application backed by the local FastAPI service.

| Width | Zones | Chart toolbar | Horizontal overflow |
|---:|---|---|---|
| 390 | Explore → Compare → Build | stacked | none (`scrollWidth=clientWidth=390`) |
| 768 | Explore → Compare → Build | stacked | none (`scrollWidth=clientWidth=768`) |
| 1280 | Explore → Compare → Build | single row | none (`scrollWidth=clientWidth=1280`) |
| 1440 | Explore → Compare → Build | single row | none (`scrollWidth=clientWidth=1440`) |

Screenshots:

- `phase7_screenshots/explorer-390.png`
- `phase7_screenshots/explorer-768.png`
- `phase7_screenshots/explorer-1280.png`
- `phase7_screenshots/explorer-1440.png`

## Verification

- `npm run build` — passed. Existing repository lint warnings remain non-blocking.
- `npx tsx --test components/explore/MarketExplorerInformationArchitecture.contract.test.mjs` — passed.
- Playwright Chromium checks confirmed the three zone markers in canonical order, responsive toolbar direction, and zero page-level horizontal overflow at all four required widths.

## Scope guard

No backend, database, migration, materialized view, route contract, search, market formula, cache, or server-side entitlement source was changed in this phase.
