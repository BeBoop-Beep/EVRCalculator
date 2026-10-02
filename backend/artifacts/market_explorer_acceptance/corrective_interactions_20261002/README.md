# Market Explorer corrective interactions - 2026-10-02

Branch authority: `fix/market-explorer-corrective-interactions-20261002`, created sequentially from data-readpath SHA `9172ba171e04cf9325346562da8a63a4c6bfcef3`.

## Acceptance

- Existing Performance view restored without changing its projection or visualization.
- Raw and Total Sealed V2 parents expose Inspect from published composition capability, not labels or parent status.
- Active chip body focuses and inspects; repeating the focused chip clears focus. Visibility, Edit, and X remain isolated actions.
- The resolved inspection target prefetches page one. The generation-pinned cache survives detail close/reopen.
- The constituent movement selector uses intrinsic width. Measured trailing space after LT: 3 px at desktop and mobile widths.
- Short-history 1Y uses the first real observation and spans the plot from x=2 to x=98 in a 100-unit viewBox.
- Directory rows expose active membership with `aria-pressed` and active styling; selecting an active row removes it.

## Verification

- Focused component/contracts: 93 passed, 0 failed.
- Playwright: 2 passed, 0 failed at 1440x900 and 390x844 touch.
- Optimized production build: passed.

`measurements.json` contains the exact LT and 1Y geometry receipts. The PNG files are the desktop/mobile visual receipts for Raw focus, Sealed focus, X isolation, parent Inspect, LT fit, and 1Y plot width.

No merge or deployment was performed.
