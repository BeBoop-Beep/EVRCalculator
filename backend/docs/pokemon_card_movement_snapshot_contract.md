# Pokemon Card Movement Snapshot Contract

Cards, Market Movers, and Top Chase use the unchanged
`inclusive_calendar_dates_v1` calculation. Different surfaces may rank or omit
different cards, but an overlapping canonical card/window must agree on:

- `canonicalCardId`
- `cardVariantId`
- `conditionId`
- `currentPrice`
- `targetStartDate`, `startDate`, and `endDate`
- `changeAmount` and `changePercent`
- `fullWindowCoverage`
- `windowConvention`

Cards and Market Dashboard snapshot metadata includes
`movementContractVersion`, `windowConvention`, `movementAsOfDate`,
`generationId`, and `builtAt`. Top Chase persists the same metadata with its
stored 1D, 7D, and 30D `marketDeltaWindows`.

Top Chase only persists a short-window entry when it has two usable distinct
market dates and finite amount/percentage output. The dashboard snapshot meta
records per-window movement counts, missing canonical/selected-variant counts,
and partial-card counts. The frontend always derives the selected chart range
from capped history; a usable stored contract owns the displayed delta, while
a missing or malformed contract uses an explicit history fallback.

`marketMoversByWindow.<window>.all` is the complete eligible overall ranking,
ordered by absolute percentage, absolute amount, then canonical identity. The
slim Market Movers endpoint projects that persisted list directly and applies
`limit` to the overall list. Directional arrays remain separately preserved.
Snapshots without `all` are identified as legacy fallback responses.

Public Cards, Market Dashboard, and Top Chase responses expose
`meta.movementGeneration`, including both generation IDs, `matches`, and a
status. Development clients warn when `matches` is false. History-derived Top
Chase movement is allowed only when the backend explicitly marks both served
snapshot generations as legacy.

Use the coordinated builder for manual rebuilds:

```powershell
python backend/scripts/build_pokemon_set_market_snapshots.py --set-id <set-id-or-slug> --commit
```

The write is rejected with `PokemonSnapshotMovementParityError` if any
overlapping movement contract differs.
