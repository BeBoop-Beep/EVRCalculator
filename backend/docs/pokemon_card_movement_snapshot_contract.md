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
