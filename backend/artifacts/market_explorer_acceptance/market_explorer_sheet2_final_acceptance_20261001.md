# Market Explorer Fix Sheet 2 — Final Integrated Acceptance

Date: 2026-10-01

Branch: `fix/market-explorer-sheet2-final-acceptance-20261001`

Parent: `66b7599e32fd269566f8322d3783a7940a1955bb`

Final SHA: see the final handoff. A commit cannot embed its own resulting hash.

## Final-pass changes

- `MarketActivityChart.jsx`: truthful inspection-date union, visible shared crosshair, Escape clearing, touch pan/scrub classification, and restrained dual-axis numeric ticks.
- `MarketActivityChart.test.jsx`: independent union, three tooltip evidence classes, crosshair/Escape, and coarse-pointer gesture coverage.
- `activity.playwright.spec.mjs`: crosshair/Escape checks and the required nine-viewport overflow matrix.
- This report and refreshed Activity fixture captures.

## Four interaction closures

| Gap | Result | Evidence |
|---|---|---|
| Inspection date union | PASS | Union contains real sales, supply, and finite focused-Index dates inside the visible range; it creates no dates and forward-fills nothing. |
| Visible shared crosshair | PASS | One calendar-positioned SVG guide spans the plot for pointer/keyboard inspection, including Index-only dates. |
| Escape clears inspection | PASS | Escape clears tooltip and crosshair without changing chart mode, market focus, or Inspecting target. |
| Touch scroll vs scrub | PASS | Established `TAP_MOVEMENT_THRESHOLD_PX` / `classifyPointerGesture` lifecycle reused with `touch-pan-y`; vertical intent remains native page scrolling, taps select, horizontal movement scrubs, and cancel drops gesture state. |

Numeric ticks were added because the prior chart named both axes but exposed no scale magnitudes. Three restrained ticks now label Activity count on the left and Market Index on the right; there is no third scale.

## Integrated issue matrix

| Area | Result | Evidence / limitation |
|---|---|---|
| Request bounds and last-good chart | PASS | Bucket 2 contracts remain green; lane bounds remain 3–8 seconds and Build remains 45 seconds. |
| Search overlays and hit testing | PASS | Bucket 3A regression contracts remain unchanged; targeted Chromium closure passed previously. |
| Direct Card/Sealed View | PASS | Bucket 2/3A transport and workspace tests retained. |
| Ordinary tooltip ordering and crossing | PASS | Existing chart ordering tests retained. |
| Focus and Inspecting separation | PASS | Workspace tests prove focus changes graph emphasis/target and Clear Focus retains inspection. |
| Constituent truthful counts/paging | PASS | Existing V2 authority tests retain Two-Pack 6, Emerald 3, Arceus 1, Raw 20,315, and Total Sealed 1,377 without padding. |
| Screens inline/close/retry/filter rank | PASS | Bucket 1/3A contracts and staged Screen ranking SQL unchanged. |
| Naming and shared 30D domain | PASS | Existing naming/domain contracts unchanged; no synthetic August 30 point added. |
| Activity entitlement and windows | PASS | Basic locked; exact-capability Card available; unsupported assets disabled; 7/30/90/180 mappings and 30D fallback are covered. |
| Activity focus A→B / unsupported focus | PASS | Request ownership/stale guards and controlled chart-mode tests pass. |
| Constituent Activity independence | PASS | Inspecting-owned capability, paging, drawer, and Listed Supply terminology tests pass. |
| Sparse semantics | PASS | Missing sales draws no bar, missing supply draws no marker, explicit zero remains numeric, and no supply line/interpolation exists. |
| Production performance observations | PARTIAL | Production-mode fixture server showed initial Explorer authority read 42 ms and subsequent reads 2–3 ms. Earlier live warm observations remain prepared ~138 ms, search ~147 ms, Screen ~80 ms, constituents ~161 ms, direct Card ~250 ms, direct Sealed ~125 ms. The full requested per-interaction browser timing breakdown was not reproducibly instrumented in this pass and is not claimed. |

## Tooltip acceptance

- Complete date: exact sales, listing offers, listed copies, and exact Index are shown.
- Index-only date: all three Activity facts say `Not observed`; the real Index is shown.
- Activity-without-exact-Index date: Activity facts are shown and Index is `—`.
- Only the focused market is represented.

## Responsive browser matrix

Production-build Chromium fixture acceptance passed at 1728×1000, 1440×900, 1280×720, 1024×768, 834×1194, 768×1024, 412×915, 390×844, and 844×390. Assertions covered zero document-level horizontal overflow, Activity visibility, keyboard inspection, tooltip, crosshair, and Escape. The existing responsive/product contracts cover the controls drawer, action/nav clearance, centered constituent toggle, and inline Screens. The optional `agent-browser` executable was unavailable; repository Playwright supplied the browser evidence.

## Tests and build

- New/focused Activity + Explorer frontend: **70 passed, 0 failed**.
- Backend Activity/API/domain: **185 passed, 0 failed**, 3 dependency warnings.
- Bucket 1 migration contract + V2 surface: **39 passed, 0 failed**, 2 dependency warnings.
- Broad Explorer frontend aggregate: **372 passed, 13 unrelated legacy/source-contract failures, 34 intentional skips**. This is not represented as repository-wide green.
- Playwright final Activity matrix: **2 passed, 0 failed** across nine viewports.
- Optimized Next production build: PASS; existing unrelated lint warnings remain non-fatal.
- Backend implementation was not changed; focused Python suites compile/import through pytest.

## Staged migration proof

The exact migration remains staged only: `20260930230000_market_explorer_surface_canonical_movement_v1.sql`. Its byte/content contract and V2 surface suite pass locally. The earlier isolated PostgreSQL 16 proof compiled and executed all three functions and demonstrated populated Card Quick/Rarity 30D, preserved null 1Y, non-empty Rarity Leaders, Card Momentum participation, global Top/Worst rank semantics, and no Graded fabrication. The disposable database from that proof was not retained, so a fresh database execution was not repeated here; this remains a release-gate verification rather than a production claim. Production migration writes: none.

## Live production freshness (read-only)

At final read:

- status: `STALE`
- reason: `CARD_DAILY_NOT_CURRENT`
- canonical accepted date: `2026-09-30`
- surface V2 / prepared Explorer date: `2026-09-29`
- surface lag: 1 day
- maintained caches: 37/37 ready and current

The independent daily watchdog also reports the October 1 authority set is not coherent yet: accepted quality remains September 30 while card/sealed current and Set Value have advanced to October 1. No date was relabelled and no publication was run.

## Data-quality backlog

Umbreon ex `3b62356c-ea20-43cd-a161-24cd6b1ed35e` retains its canonical TCGPlayer NM observations: May 28–30 at $1 and July 19 at $500. Index 50,000 remains faithful to authority and is not hidden or rewritten. Upstream pricing-quality review remains open.

## Eventual release order

1. Review and merge the approved code stack.
2. Apply the reviewed Bucket 1 migration in the controlled database release window.
3. Run one bounded normal candidate publication under the existing lease.
4. Validate all 15 Card Quick/Rarity 30D repairs, null 1Y behavior, Rarity Leaders, Momentum, and globally ranked Top/Worst filters.
5. Atomically promote only the validated surface generation.
6. Deploy the compatible backend/frontend application revision. The staged RPC signatures are backward-compatible with the merged application; promotion must not precede migration validation.
7. Run production browser smoke for search, direct View, Screens, focus, constituents, Activity, touch, and responsive layouts.
8. Recheck Explorer freshness, maintained caches, daily Sentinel/watchdog state, and authority-date coherence.

## Blockers and safety

- **Release blocker:** live Explorer surface is stale on September 29 with `CARD_DAILY_NOT_CURRENT`.
- **Release blocker:** Bucket 1 migration is staged, not reviewed/applied/validated against a new candidate.
- **Acceptance limitation:** a new disposable PostgreSQL execution and the complete per-lane production-browser timing study were not repeated in this pass.
- Production writes: **none**.
- Paid provider credits consumed: **none**.
- Merge/deployment/migration/publication: **none**.

Recommendation: the interaction code is merge-ready after review, but release/promotion is blocked until the staged migration and bounded candidate sequence pass and freshness becomes coherent without relabelling data.
