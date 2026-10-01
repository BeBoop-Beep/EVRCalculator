# Rankings Follow-up B3 - Financial RIP History Interaction Contract

Scope: the Financial RIP Over Time chart on the Rankings Overview. Nothing else changes (Product, Cards, unified Era/Set tables, Pack Economics, tier formulas, models, publications).

## Preserved (B5/B7)
Overall Financial RIP is permanent; entity colours are stable; no interpolation (`connectNulls=false`); tooltip delta = same-date entity minus same-date Overall; rows sorted by hovered value, descending; Era presets may exceed the manual 5-Set limit; API ceiling 22; Overall-only mode stays visible and a range change in Overall-only mode still requests the active range.

## Clear All
- Compact red-tinted pill (`border-red-400/45 bg-red-500/[.09] text-red-300`), accessible name **"Clear all Financial RIP series"**, in the legend row at the far right (outside the legend's scroll area, so it stays reachable with 16 keys and on mobile).
- Removes every user-selected series of the **current mode** (Sets or Eras) and the Era preset; clears focus and any pinned tooltip.
- Does **not** remove Overall, the chart, the axes, the active range, or the ability to show Overall in the tooltip. No request is made. Disabled when already Overall-only.
- The Set/Era selector reports 0 selected. Defaults are seeded exactly once; an empty selection is never auto-refilled (the old "empty -> first 3" effect is gone).
- **Transport anchor:** with no selected series a range change still needs an authorised request. The request carries one invisible anchor entity (last loaded entity, else the first cohort entity - only once defaults have been seeded). The anchor is never plotted or listed; only the request uses it (`financialRipRequestEntities`).

## Legend key = focus control + remove control
`[ ● Name ][ × ]` is two real buttons: the key body (`aria-pressed`, "Focus <Name> on Financial RIP chart") and the x ("Remove <Name> from Financial RIP chart"). Both >= 36 px. Overall's key is a non-interactive span and can never be removed or hidden.
- Click/tap body: persistent focus. Click/tap the focused body again: back to the all-series view. Another body moves focus.
- x removes the series; if it was focused (or hovered) focus is cleared.
- The legend wraps; with a large selection it scrolls inside `max-h-36` (every key stays reachable, nothing truncated at 5). No second chip row.

## Focus behaviour (display only)
Focus never changes the selected ids and never causes a request.
- Focused series: full opacity, normal width, dots; drawn last (on top).
- Overall: unchanged (`strokeOpacity 0.72`, width 3).
- Other selected series: stay selected and in the legend, stroke opacity 0.14, no dots, no active dot.
- **Desktop hover:** pointer-only (`pointerType === "mouse"`). Hovering a key temporarily focuses it (wins over persistent focus); leaving restores the persistent focus, or the all-series view. Hover on touch/pen is ignored, and nothing requires hover.

## Tooltip
- Normal: date once, Overall once, every selected comparable row (value-descending).
- Focused (persistent or hover): date once, Overall once, **only the focused entity**.
- Hovering/moving the tooltip never changes focus; no network request on tooltip movement.
- Layout: date + Overall stay fixed; the entity list is the scroll region (`overflow-y:auto; overscroll-behavior:contain; touch-action:pan-y`), the whole tooltip bounded by `max-h-[min(18rem,55vh)]` (fits the 20/24/28 rem chart and the viewport).
- **Why wheel did not work:** Recharts' tooltip is `pointer-events: none` (so it cannot chase the cursor), so wheel events never reached it. Fix without making the chart interactive: a non-passive `wheel` listener on the plot forwards wheel/trackpad deltas to the *hover* tooltip's scroll region when it overflows; when the region is at its top/bottom (or the tooltip is not overflowing) the page scrolls normally; wheel inside a tooltip scroll region is left to native scrolling.
- **Pinned tooltip (touch, precise scrolling, keyboard):** click/tap the chart to pin the values for that date as an interactive panel (`pointer-events` normal, focusable `role=region`, native wheel / touch-pan / arrow-key scrolling, close button, `Escape`, tap the same date to unpin). The hover tooltip is suppressed while pinned. Range, mode or selection changes unpin.

## Data / cache behaviour
See `PERFORMANCE_REPORT.md`. Summary: history reads go through the existing Rankings session cache (identity = access identity + publication), keyed by type, range and sorted entity ids; a completed wider response for the same type/range serves narrower selections locally; the default view is prewarmed by the parent for entitled users; one optional idle prefetch of the whole <=22-Set cohort for the same range (skipped under save-data). Ranges, entity types, identities and publications are never mixed. Older responses cannot overwrite newer state (effect cleanup + per-range cache entries).

## Access
History stays Index Plus. Anonymous/Base see the locked preview; no history request, prewarm or prefetch is made for them. The chart is keyed by the session-cache identity (state resets on any access/publication change) and a response that resolves after a downgrade is dropped.

## Styling
Sets/Eras and the 30D/3M/6M/1Y/ALL controls keep the B1 green selected surface with white text. Clear All is a dark-red transparent pill, not a solid destructive button.
