# Market Explorer Bucket 2 — backend access and transport acceptance

Starting SHA: `075d4a2f1cf1d696ca498025d05b02e011da7967`
Branch: `fix/market-explorer-fixsheet-backend-20260930`

## Access architecture

The existing `/market/explorer/query` planner/cache route now has a strict
public canonical-rarity seam. The request is normalized before access checks.
Only the exact one-segment Cards/all/filters shape can enter the seam, and the
sole segment must be verified against current Cards asset-options with
`selectionAvailable=true` and eligibility `PREPARED` or
`CUSTOM_BUILD_AVAILABLE`. No client flag is consumed. Registry failure, unknown
keys, unavailable keys, or any extra filter axis fail closed into the ordinary
authenticated Premium Builder gate.

The seam intentionally reuses the existing stable fingerprint, prepared
equivalence registry, persistent query cache, canonical comparison watermark,
and response shape. Public canonical requests use the existing bounded public
read abuse policy. `/market/explorer/query/constituents` does not opt into the
public seam and remains paid/authenticated.

Generic single-axis, compound, Pokémon, ranked/chase, explicit-instrument,
arbitrary Sealed, price-band, and release-age queries remain Premium.

`/market/explorer/prepared-screen` is now public discovery, accepts only the
existing Screen registry and optional valid asset, and caps requests at 10.
Reading a Screen does not alter prepared comparison entitlement: one prepared
market stays public; two or more require authentication plus Index+; active
market limits remain three for Plus and ten for Premium.

## Movement transport

Prepared Cards and Sealed rows retain the canonical keys `1D`, `7D`, `30D`,
`3M`, `6M`, `1Y`, and `SinceTracking`. Sealed continues to use exactly one
`get_pokemon_market_explorer_sealed_constituent_movement_v2` call for at most
100 IDs and preserves `changeBaselines`. Query-built Cards markets publish the
same seven row `changes` keys plus shared `movementWindows`.

Live Steam Siege Elite Trainer Box proof at 2026-09-29 returned numeric zero
for 3M, `NULL` for 6M and 1Y, and a real SinceTracking baseline of 2026-05-20.
No route calculates movement or replaces missing values.

## Production read-only acceptance

- Sealed Types: 34/34 currently available prepared keys exist in the serving
  directory and return history. Booster Box, Multi-Product Bundle,
  Single-Pack Blister, Case, and Premium Collection all resolved.
- First Partner Pack and World Championship Deck remain unavailable with no
  prepared key.
- Global Top Performers returned ten mixed Cards/Sealed rows. Worst Performers
  also returned mixed assets. Momentum Leaders returned ten globally ranked
  rows (currently all Sealed), which is valid global ranking behavior.
- Cards asset-options identify ACE SPEC Rare and Amazing Rare as selectable
  `CUSTOM_BUILD_AVAILABLE`; nine rarities remain selectable `PREPARED` markets.
- No DB migration was needed for Bucket 2.

## Freshness

Completion status remains truthful: `STALE / CARD_DAILY_NOT_CURRENT`.
Canonical/raw is 2026-09-30; card daily, sealed daily, sealed metadata,
prepared V1, and serving V2 remain 2026-09-29; lag is one day; maintained
caches are 37/37 current. Backend access does not claim Sep 30 freshness.

## Verification

The focused API, access-policy, paid-boundary, abuse-control, movement, and
query-service regression suite passes: `253 passed`. The three emitted warnings
are dependency deprecations and do not represent test failures.

## Bucket 3 handoff

Use the prepared path whenever `preparedMarketAvailable=true`. For a selectable
canonical rarity whose eligibility is `CUSTOM_BUILD_AVAILABLE`, submit the
existing exact one-rarity query shape; it is now public. Screen reads require no
auth, but clicking a row should replace the single active market for Basic.
Do not use Screen results to bypass multi-market comparison entitlement. Display
`SinceTracking` as LT if desired while retaining the canonical transport key.
